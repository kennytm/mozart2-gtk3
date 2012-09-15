#!/usr/bin/env python3

import os
import sys
import re
from os.path import join
from clang.cindex import TranslationUnit, Config, CursorKind, TypeKind
from constants import *

C_FILES = 'c-files'
C_EXT = '.c'
SRC = 'src'
CC_EXT = '.cc'
HH_EXT = '.hh'
TYPES_HH_EXT = '-types.hh'
TYPES_DECL_HH_EXT = '-types-decl.hh'

Config.set_compatibility_check(False)

INTEGER_KINDS = {
    TypeKind.INT, TypeKind.CHAR_U, TypeKind.UCHAR, TypeKind.CHAR16,
    TypeKind.CHAR32, TypeKind.USHORT, TypeKind.UINT,TypeKind.ULONG,
    TypeKind.ULONGLONG, TypeKind.UINT128, TypeKind.CHAR_S, TypeKind.SCHAR,
    TypeKind.WCHAR, TypeKind.SHORT, TypeKind.INT, TypeKind.LONG,
    TypeKind.LONGLONG, TypeKind.INT128
}

FLOAT_KINDS = {TypeKind.FLOAT, TypeKind.DOUBLE, TypeKind.LONGDOUBLE}

#-------------------------------------------------------------------------------

_unique_str_counter = 0
def unique_str():
    """
    Obtain a globally-unique identifier.
    """
    global _unique_str_counter
    _unique_str_counter += 1
    return '_x_' + str(_unique_str_counter)


def capitalize(s):
    """
    Captialize a string without causing the other characters to become
    lowercase.
    """
    return s[0].upper() + s[1:]

def strip_prefix_and_camelize(s):
    """
    Remove the prefix of a string, and change it to CamelCase, e.g.::

        >>> strip_prefix_and_camelize("cairo_push_group_with_content")
        pushGroupWithContent
    """
    arr = s.split('_')
    if not arr[0]:
        arr = arr[1:]
    return arr[1] + ''.join(p.capitalize() for p in arr[2:])

#-------------------------------------------------------------------------------

def is_c_string(typ):
    """
    Check whether a clang Type is a C string, i.e. ``const char*``.
    """
    if typ.kind != TypeKind.POINTER:
        return False
    pointee = typ.get_pointee()
    return pointee.kind in {TypeKind.CHAR_U, TypeKind.CHAR_S} and \
           pointee.is_const_qualified()

def is_primitive_type(typ):
    """
    Check whether a clang Type is a primitive type directly representable in Oz,
    i.e. boolean, integers or floats.
    """
    kind = typ.kind
    return kind == TypeKind.BOOL or kind in INTEGER_KINDS or kind in FLOAT_KINDS

#-------------------------------------------------------------------------------

def create_no_statements(typ, name_1, name_2, with_declaration):
    return []

def create_out_statements_post(typ, cc_name, oz_name, with_declaration):
    """
    Create a list of C++ declarations and statements encoding a C value into an
    Oz UnstableNode.
    """
    prefix = 'auto ' + oz_name if with_declaration else oz_name

    if is_primitive_type(typ):
        return [prefix + " = build(vm, " + cc_name + ");"]

    elif is_c_string(typ):
        prefix = 'auto ' if with_declaration else ''
        return [prefix + " = String::build(vm, newLString(vm, toUTF<nchar>(makeLString(" + cc_name + ");"]

    elif typ.kind == TypeKind.RECORD:
        cc_statements = []
        temp_oz_names = []
        field_names = []

        struct_decl = typ.get_declaration()
        record_name = strip_prefix_and_camelize(struct_decl.spelling.decode('utf-8'))

        for decl in struct_decl.get_children():
            subtype = decl.type
            field_name = decl.spelling.decode('utf-8')
            field_names.append(field_name)
            temp_oz_name = unique_str()
            temp_oz_names.append(temp_oz_name)
            cc_statements.extend(create_out_statements_post(subtype,
                                                            cc_name + "." + field_name,
                                                            temp_oz_name,
                                                            with_declaration=True))

        field_names_concat = '"), MOZART_STR("'.join(field_names)
        temp_oz_names_concat = '), std::move('.join(temp_oz_names)

        cc_statements.append("""
            %s = buildRecord(vm,
                buildArity(vm, MOZART_STR("%s"), MOZART_STR("%s")),
                std::move(%s)
            );
        """ % (prefix, record_name, field_names_concat, temp_oz_names_concat))

        return cc_statements

    else:
        return [';']
        raise NotImplementedError('Not implemented to convert %s to %s with TypeKind %s' %
                                  (cc_name, oz_name, typ.kind.spelling.decode('utf-8')))

def create_in_statements_pre(typ, oz_name, cc_name, with_declaration):
    """
    Create a list of C++ statements decoding an Oz RichNode into a C value. The
    target variable must already been declared.
    """
    prefix = 'auto ' + cc_name if with_declaration else cc_name

    if is_c_string(typ):
        return ["""
            auto %(unique)s = vsToString<char>(vm, %(oz)s);
            %(cc)s = %(uniq)s.c_str();
        """ % {'cc': prefix, 'oz': oz_name, 'unique': unique_str()}]

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

        return ['%s = %s(%s).%s(vm)' % (prefix, interface, oz_name, method)]

    elif typ.kind == TypeKind.RECORD:
        temp_interface_name = unique_str()
        struct_decl = typ.get_declaration()

        cc_statements = ["Dottable %s(%s);" % (temp_interface_name, oz_name)]
        if with_declaration:
            cc_statements.append(struct_decl.spelling.decode('utf-8') + ' ' + cc_name + ';')

        for decl in struct_decl.get_children():
            subtype = decl.type
            field_name = decl.spelling.decode('utf-8')
            temp_oz_field_name = unique_str()
            cc_statements.append("""
                auto %s = %s.dot(vm, build(vm, MOZART_STR("%s")));
            """ % (temp_oz_field_name, temp_interface_name, field_name))
            cc_statements.extend(create_in_statements_pre(subtype,
                                                          temp_oz_field_name,
                                                          cc_name + '.' + field_name,
                                                          with_declaration=False))
        return cc_statements

    else:
        return [';']
        raise NotImplementedError('Not implemented to convert %s to %s with TypeKind %s' %
                                  (source_name, target_name, typ.kind.spelling.decode('utf-8')))

STATEMENTS_CREATORS = {
    'in': (create_in_statements_pre, create_no_statements, 'In'),
    'out': (create_no_statements, create_out_statements_post, 'Out'),
}

def get_arg_spec(func_cursor, c_func_name):
    inouts = SPECIAL_INOUTS.get(c_func_name, {})

    for arg in func_cursor.get_children():
        if arg.kind != CursorKind.PARM_DECL:
            continue
        arg_name = arg.spelling.decode('utf-8')
        inout = inouts.get(arg_name, 'in')
        (stc_pre, stc_post, oz_inout) = STATEMENTS_CREATORS[inout]
        yield (arg.type.get_canonical(), arg_name, stc_pre, stc_post, oz_inout)

    return_type = func_cursor.result_type.get_canonical()
    if return_type.kind != TypeKind.VOID:
        (stc_pre, stc_post, oz_inout) = STATEMENTS_CREATORS['out']
        yield (return_type, '_x_oz_return', stc_pre, stc_post, oz_inout)


def get_cc_function_definition(func_cursor, c_func_name):
    """
    Get the C++ function definition from a clang function Cursor. The result is
    a 2-tuple, with the first being a C++ code of the signature of the Oz
    built-in procedure (e.g. ``, In arg1, Out arg2``), and the second being a
    list of C++ statements of the built-in procedure.
    """

    arg_specs = list(get_arg_spec(func_cursor, c_func_name))

    cc_names = []
    cc_statements = []

    for typ, oz_name, stc_pre, _, _ in arg_specs:
        cc_name = '_x_cc_' + oz_name
        if oz_name != '_x_oz_return':
            cc_names.append(cc_name)
        if stc_pre is not None:
            cc_statements.extend(stc_pre(typ, oz_name, cc_name, with_declaration=True))

    call_statement = c_func_name + '(' + ', '.join(cc_names) + ');'
    if func_cursor.result_type.get_canonical().kind != TypeKind.VOID:
        call_statement = 'auto _x_cc__x_oz_return = ' + call_statement
    cc_statements.append(call_statement)

    for typ, oz_name, _, stc_post, _ in arg_specs:
        cc_name = '_x_cc_' + oz_name
        if stc_post is not None:
            cc_statements.extend(stc_post(typ, cc_name, oz_name, with_declaration=False))

    arg_proto = ''.join(', ' + p + ' ' + q for _, q, _, _, p in arg_specs)

    return (arg_proto, cc_statements)

def create_datatype(struct_name, is_pointer):
    """
    Create a Mozart/Oz DataType, given a C structure name. The DataType will be
    created like this:

    1. If the structure is incomplete, the parameter ``is_pointer`` should be
       set to True. The generated DataType will then be based on a C pointer of
       that structure.
    2. Otherwise, ``is_pointer`` should be False, and the DataType will contain
       the whole structure by value.

    In both cases, the data type will contain a ``value()`` method to return the
    pointer to the structure. The name of the DataType is
    ``D_(name of C structure)``.
    """

    params = {'s': struct_name}

    statements = ["""
        class D_%(s)s;

        #ifndef MOZART_GENERATOR
        #include "D_%(s)s-implem-decl.hh"
        #endif
    """ % params, None, """
        #ifndef MOZART_GENERATOR
        #include "%(s)s-implem-decl-after.hh"
        #endif
    """ % params]

    if is_pointer:
        statements[1] = """
            class D_%(s)s : public DataType<D_%(s)s>, StoredAs<%(s)s*>
            {
            public:
                typedef SelfType<D_%(s)s>::Self Self;

                D_%(s)s(%(s)s* value) : _value(value) {}

                static void create(%(s)s*& self, VM vm, %(s)s* value) { self = value; }
                static void create(%(s)s*& self, VM vm, GR gr, Self from) { self = from->_value; }

                %(s)s* value() const { return _value; }

            private:
                %(s)s* _value;
            };
        """ % params

    else:
        statements[1] = """
            class D_%(s)s : public DataType<D_%(s)s>
            {
            public:
                typedef SelfType<D_%(s)s>::Self Self;

                D_%(s)s(VM vm, const %(s)s& value) : _value(value) {}
                D_%(s)s(VM vm, GR gr, Self from) : _value(from->_value) {}

                const %(s)s* value() const { return &_value; }

            private:
                %(s)s _value;
            };
        """ % params

    return statements

#-------------------------------------------------------------------------------

class Translator:
    """
    This class exists mainly just to hold the states.
    """

    def __init__(self, module):
        self._module = module
        self._cc_file = open(join(SRC, module + CC_EXT), 'w')
        self._hh_file = open(join(SRC, module + HH_EXT), 'w')
        self._types_hh_file = open(join(SRC, module + TYPES_HH_EXT), 'w')
        self._types_decl_hh_file = open(join(SRC, module + TYPES_DECL_HH_EXT), 'w')
        self._structs = {}

    def _all_files(self):
        return [self._cc_file, self._hh_file,
                self._types_decl_hh_file, self._types_hh_file]

    def __enter__(self):
        for f in self._all_files():
            f.__enter__()
        return self

    def __exit__(self, p, q, r):
        handled = False
        for f in reversed(self._all_files()):
            handled = f.__exit__(p, q, r)
            if handled:
                p = q = r = None
        return handled

    def _print_header(self):
        """
        Print the C++ headers to all files.
        """
        format_params = {
            'guard': 'M2G3_MODULE_' + self._module.upper() + "_" + unique_str(),
            'mod': self._module,
            'hh-file': self._module,
            'hh-ext': HH_EXT,
            'common-header': """
                #include <mozart.hh>

                namespace m2g3 {

                using namespace mozart;
                using namespace mozart::builtins;
            """
        }

        self._hh_file.write("""
            #ifndef %(guard)s
            #define %(guard)s

            %(common-header)s

            struct M_%(mod)s : Module
            {
                M_%(mod)s() : Module("%(mod)s") {}
        """ % format_params)

        self._cc_file.write("""
            #include "%(hh-file)s%(hh-ext)s"

            namespace m2g3 {
        """ % format_params)

        self._types_decl_hh_file.write("""
            #ifndef %(guard)s_DATATYPES_DECL
            #define %(guard)s_DATATYPES_DECL

            %(common-header)s
        """ % format_params)

        self._types_hh_file.write("""
            #ifndef %(guard)s_DATATYPES
            #define %(guard)s_DATATYPES

            %(common-header)s
        """ % format_params)


    def _print_footer(self):
        """
        Print the C++ footers to all files.
        """
        self._hh_file.write("""
            };

            }

            #endif
        """)

        self._cc_file.write("""
            }
        """)

        self._types_decl_hh_file.write("""
            }

            #endif
        """)

        self._types_hh_file.write("""
            }

            #endif
        """)

    def _print_function(self, function):
        """
        Print a single function.
        """
        source_func_name = function.spelling.decode('utf-8')
        (arg_proto, cc_statements) = get_cc_function_definition(function, source_func_name)

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

    def _collect_structure(self, typedef):
        """
        Collection the structures cursors.
        """
        type_name = typedef.spelling.decode('utf-8')
        underlying_type = typedef.underlying_typedef_type
        if underlying_type.kind != TypeKind.UNEXPOSED:
            return
        if underlying_type.get_canonical().kind != TypeKind.RECORD:
            return
        if type_name in BLACKLISTED_TYPEDEFS:
            return
        is_complete = underlying_type.get_declaration().is_definition()
        if is_complete or type_name not in self._structs:
            self._structs[type_name] = is_complete

    def _print_structures(self):
        """
        Print all structures as DataTypes.
        """
        for struct_name, is_complete in self._structs.items():
            data_type = create_datatype(struct_name, not is_complete)
            self._types_decl_hh_file.writelines(data_type)
            self._types_hh_file.write('#include "D_%s-implem.hh"\n' % struct_name)

    def print(self):
        """
        Print everything into the files.
        """
        self._print_header()

        tu = TranslationUnit.from_source(join(C_FILES, self._module + C_EXT))
        for node in tu.cursor.get_children():
            kind = node.kind
            if kind == CursorKind.FUNCTION_DECL:
                self._print_function(node)
            elif kind == CursorKind.TYPEDEF_DECL:
                self._collect_structure(node)

        self._print_structures()
        self._print_footer()

def main(module):
    with Translator(module) as tr:
        tr.print()

if __name__ == '__main__':
    if len(sys.argv) <= 1:
        print("Usage: ./translator.py [module-name]")
    else:
        main(sys.argv[1])

