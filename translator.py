#!/usr/bin/env python3

import os
import sys
import re
from os.path import join
from clang.cindex import TranslationUnit, Config, CursorKind, TypeKind

C_FILES = 'c-files'
C_EXT = '.c'
SRC = 'src'
CC_EXT = '.cc'
HH_EXT = '.hh'

Config.set_compatibility_check(False)

INTEGER_KINDS = {
    TypeKind.INT, TypeKind.CHAR_U, TypeKind.UCHAR, TypeKind.CHAR16,
    TypeKind.CHAR32, TypeKind.USHORT, TypeKind.UINT,TypeKind.ULONG,
    TypeKind.ULONGLONG, TypeKind.UINT128, TypeKind.CHAR_S, TypeKind.SCHAR,
    TypeKind.WCHAR, TypeKind.SHORT, TypeKind.INT, TypeKind.LONG,
    TypeKind.LONGLONG, TypeKind.INT128
}

FLOAT_KINDS = {TypeKind.FLOAT, TypeKind.DOUBLE, TypeKind.LONGDOUBLE}

_unique_str_counter = 0
def unique_str():
    global _unique_str_counter
    _unique_str_counter += 1
    return 'xx_temp_' + str(_unique_str_counter)

def capitalize(s):
    return s[0].upper() + s[1:]

def strip_prefix_and_camelize(s):
    arr = s.split('_')
    if not arr[0]:
        arr = arr[1:]
    return arr[1] + ''.join(p.capitalize() for p in arr[2:])

def is_c_string(typ):
    if typ.kind != TypeKind.POINTER:
        return False
    pointee = typ.get_pointee()
    return pointee.kind in {TypeKind.CHAR_U, TypeKind.CHAR_S} and \
           pointee.is_const_qualified()

def is_primitive_type(typ):
    kind = typ.kind
    return kind == TypeKind.BOOL or kind in INTEGER_KINDS or kind in FLOAT_KINDS

def create_encode_statements(typ, source_name, target_name):
    "Create the statements encoding a C value into an Oz UnstableNode."

    if is_primitive_type(typ):
        return ["auto %s = build(vm, %s);" % (target_name, source_name)]

    elif is_c_string(typ):
        return ["""
            auto %(s)s = toUTF<nchar>(makeLString(%(i)s));
            auto %(t)s = String::build(vm, newLString(vm, %(s)s));
        """ % {'s': unique_str(), 'i': source_name, 't': target_name}]

    elif typ.kind == TypeKind.RECORD:
        statements = []
        targets = []
        names = []
        struct_decl = typ.get_declaration()
        for decl in struct_decl.get_children():
            subtype = decl.type
            name = decl.spelling.decode('utf-8')
            names.append(name)
            target = unique_str()
            targets.append(target)
            statements.append(create_encode_statement(subtype, source_name + "." + name, target))

        statements.append("""
            auto %s = buildRecord(vm,
                buildArity(vm, MOZART_STR("%s"), MOZART_STR("%s")),
                std::move(%s)
            );
        """ % (
            target_name,
            strip_prefix_and_camelize(struct_decl.spelling.decode('utf-8')),
            '"), MOZART_STR("'.join(names),
            '), std::move('.join(targets)
        ))

        return statements

    else:
        raise NotImplementedError('Not implemented to convert %s to %s with TypeKind %s' %
                                  (source_name, target_name, typ.kind.spelling.decode('utf-8')))

def create_decode_statements(typ, source_name, target_name):
    "Create the statements decoding an Oz RichNode into a pre-declared C value."

    if is_c_string(typ):
        return ["""
            auto %(uniq)s = vsToString<char>(vm, %(src)s);
            %(tgt)s = %(uniq)s.c_str();
        """ % {'tgt': target_name, 'src': source_name, 'uniq': unique_str()}]

    elif is_primitive_type(typ):
        kind = typ.kind
        if kind == TypeKind.BOOL:
            interface = "BoolValue"
            method = "boolValue"
        elif kind in INTEGER_KINDS:
            interface = "IntegerValue"
            method = "intValue"
        elif kind in FLOAT_KINDS:
            interface = "FloatValue"
            method = "floatValue"

        return ["%s = %s(%s).%s(vm);" % (target_name, interface, source_name, method)]

    elif typ.kind == TypeKind.RECORD:
        temp_interface_name = unique_str()
        statements = ["Dottable " + temp_interface_name + "(" + source_name + ");"]
        struct_decl = typ.get_declaration()
        for decl in struct_decl.get_children():
            subtype = decl.type
            name = decl.spelling.decode('utf-8')
            src = unique_str()
            statements.append("""
                auto %s = %s.dot(vm, build(vm, MOZART_STR("%s")));
            """ % (src, temp_interface_name, name))
            statements.append(create_decode_statement(subtype, src, target_name + '.' + name))

        return statements

    else:
        raise NotImplementedError('Not implemented to convert %s to %s with TypeKind %s' %
                                  (source_name, target_name, typ.kind.spelling.decode('utf-8')))

def get_arg_spec(function, func_name):
    cc_statements = []
    arg_names = []
    arg_inouts = []
    res_names = []

    func_type = function.type
    for arg_type in func_type.argument_types():
        arg_name = unique_str()
        res_name = unique_str()
        cc_statements.extend(create_decode_statements(arg_type.get_canonical(), arg_name, res_name))
        arg_names.append(arg_name)
        arg_inouts.append('In')
        res_names.append(res_name)

    ret_type = function.result_type.get_canonical()
    cc_statements.append("%s(%s);" % (func_name, ', '.join(res_names)))
    if ret_type.kind != TypeKind.VOID:
        res_name = unique_str()
        return_name = unique_str()
        cc_statements[-1] = "auto %s = %s" % (res_name, cc_statements[-1]);
        cc_statements.extend(create_encode_statements(ret_type, res_name, return_name))
        arg_names.append(return_name)
        arg_inouts.append('Out')

    arg_proto = ''.join(', ' + p + ' ' + q for p, q in zip(arg_inouts, arg_names))

    return (arg_proto, cc_statements)



class Translator:
    def __init__(self, module):
        self._module = module
        self._cc_file = open(join(SRC, module + CC_EXT), 'w')
        self._hh_file = open(join(SRC, module + HH_EXT), 'w')
        self._incomplete_structs = set()

    def __enter__(self):
        self._cc_file.__enter__()
        self._hh_file.__enter__()
        return self

    def __exit__(self, p, q, r):
        if self._hh_file.__exit__(p, q, r):
            p = q = r = None
        return self._cc_file.__exit__(p, q, r)

    def _print_header(self):
        format_params = {
            'guard': 'M2G3_MODULE_' + self._module.upper() + "_" + unique_str(),
            'mod': self._module,
            'hh-file': self._module,
            'hh-ext': HH_EXT
        }

        self._hh_file.write("""
            #ifndef %(guard)s
            #define %(guard)s

            #include <mozart.hh>

            namespace m2g3 {

            using namespace mozart;
            using namespace mozart::builtins;

            struct M_%(mod)s : Module
            {
                M_%(mod)s() : Module("%(mod)s") {}
        """ % format_params)

        self._cc_file.write("""
            #include "%(hh-file)s%(hh-ext)s"

            namespace m2g3 {
        """ % format_params)

    def _print_footer(self):
        self._hh_file.write("""
            };

            }

            #endif
        """)

        self._cc_file.write("""
            }
        """)

    def _print_function(self, function):
        source_func_name = function.spelling.decode('utf-8')
        (arg_proto, cc_statements) = get_arg_spec(function, source_func_name)

        params = {
            'target': strip_prefix_and_camelize(source_func_name),
            'args': arg_proto,
            'mod': self._module,
        }

        self._hh_file.write("""
                struct P_%(target)s : Builtin<P_%(target)s>
                {
                    P_%(target)s() : Builtin("%(target)s") {}
                    void operator()(VM vm%(args)s) const;
                };
        """ % params)

        self._cc_file.write("""
            void M_%(mod)s::P_%(target)s::operator()(VM vm%(args)s) const
            {
        """ % params)
        for statement in cc_statements:
            self._cc_file.write('\n')
            self._cc_file.write(statement)
        self._cc_file.write("}\n")

    def print(self):
        self._print_header()

        tu = TranslationUnit.from_source(join(C_FILES, self._module + C_EXT))
        for node in tu.cursor.get_children():
            kind = node.kind
            if kind == CursorKind.FUNCTION_DECL:
                self._print_function(node)

        self._print_footer()

def main(module):
    with Translator(module) as tr:
        tr.print()

if __name__ == '__main__':
    if len(sys.argv) <= 1:
        print("Usage: ./translator.py [module-name]")
    else:
        main(sys.argv[1])

