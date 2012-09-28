#!/usr/bin/env python3

import os
import sys
import re
from os.path import join
from clang.cindex import TranslationUnit, Config, CursorKind
from constants import *
from builders import *
from common import *
from ccformat import CCFormatter

Config.set_compatibility_check(False)

def write_datatype(types_decl_hh, types_hh, struct_name):
    """
    Create a Mozart/Oz DataType, given the name of an incomplete C structure.
    The generated DataType will then be based on a C pointer of that structure.
    The data type will contain a ``value()`` method to return the pointer to the
    structure. The name of the DataType is ``D_(name of C structure)``.
    """

    params = {'s': struct_name}

    types_decl_hh.write("""
        namespace m2g3 {
            class D_%(s)s;
        }

        namespace mozart {
            using m2g3::D_%(s)s;

            #ifndef MOZART_GENERATOR
            #include "D_%(s)s-implem-decl.hh"
            #endif
        }

        namespace m2g3 {
            class D_%(s)s : public ::mozart::DataType<D_%(s)s>, ::mozart::StoredAs<%(s)s*> {
            public:
                typedef ::mozart::SelfType<D_%(s)s>::Self Self;

                D_%(s)s(%(s)s* value) : _value(value) {}

                static void create(%(s)s*& self, ::mozart::VM vm, %(s)s* value) { self = value; }
                static inline void create(%(s)s*& self, ::mozart::VM vm, ::mozart::GR gr, Self from);

                %(s)s* value() const { return _value; }

            private:
                %(s)s* _value;
            };
        }

        namespace mozart {

            using m2g3::D_%(s)s;

            #ifndef MOZART_GENERATOR
            #include "D_%(s)s-implem-decl-after.hh"
            #endif

        }
    """ % params)

    types_hh.write("""
        namespace mozart {
            using m2g3::D_%(s)s;
            #include "D_%(s)s-implem.hh"
        }

        namespace m2g3 {
            void D_%(s)s::create(%(s)s*& self, ::mozart::VM vm, ::mozart::GR gr, Self from) {
                self = from.get().value();
            }
        }
    """ % params)

def is_blacklisted(name):
    return any(regex.match(name) for regex in BLACKLISTED)

#-------------------------------------------------------------------------------

class Translator:
    """
    This class exists mainly just to hold the files.
    """

    def __init__(self, module):
        self._module = module
        self._cc = CCFormatter()
        self._hh = CCFormatter()
        self._types_hh = CCFormatter()
        self._types_decl_hh = CCFormatter()

    def __enter__(self):
        return self

    def __exit__(self, p, q, r):
        ext_and_formatters = [
            (CC_EXT, self._cc),
            (HH_EXT, self._hh),
            (TYPES_HH_EXT, self._types_hh),
            (TYPES_DECL_HH_EXT, self._types_decl_hh),
        ]

        for ext, formatter in ext_and_formatters:
            with open(join(SRC, self._module + ext), 'w') as f:
                f.writelines(formatter.lines)

        return False

    def _write_header(self):
        """
        Print the C++ headers to all files.
        """
        format_params = {
            'guard': 'M2G3_MODULE_' + self._module.upper() + "_" + unique_str(),
            'mod': self._module,
            'hh-file': self._module,
            'hh-ext': HH_EXT,
            'types-decl-hh-ext': TYPES_DECL_HH_EXT,
            'types-hh-ext': TYPES_HH_EXT,
        }

        self._hh.write("""
            #ifndef %(guard)s
            #define %(guard)s

            #include <mozart.hh>

            namespace m2g3 {

                using namespace mozart;
                using namespace mozart::builtins;

                struct M_%(mod)s : Module {
                    M_%(mod)s() : Module("%(mod)s") {}
        """ % format_params)

        self._cc.write("""
            #include <unordered_map>
            #include <vector>
            #include <type_traits>
            #include "%(hh-file)s%(hh-ext)s"
            #include "%(mod)s%(types-hh-ext)s"

            namespace m2g3 {

                using namespace mozart;
                using namespace mozart::builtins;
        """ % format_params)

        self._types_decl_hh.write("""
            #ifndef %(guard)s_DATATYPES_DECL
            #define %(guard)s_DATATYPES_DECL

            #include "../c-files/%(mod)s.c"
            #include <mozart.hh>
        """ % format_params)

        self._types_hh.write("""
            #ifndef %(guard)s_DATATYPES
            #define %(guard)s_DATATYPES

            #include "%(mod)s%(types-decl-hh-ext)s"
        """ % format_params)


    def _write_footer(self):
        """
        Print the C++ footers to all files.
        """

        self._hh.write("""
            };
            }
            #endif
        """)

        self._cc.write("}")
        self._types_decl_hh.write("#endif")
        self._types_hh.write("#endif")

    def _write_type(self, type_node):
        """
        Print a single type.
        """
        if is_blacklisted(name_of(type_node)):
            return

        write_builder(self._cc, type_node)

        if type_node.kind == CursorKind.STRUCT_DECL and not is_concrete(type_node):
            write_datatype(self._types_decl_hh, self._types_hh, name_of(type_node))

    def _write_function(self, function):
        """
        Print a single function.
        """
        source_func_name = name_of(function)
        function_creators = get_cc_function_definition(function, source_func_name)

        params = {
            'target': strip_prefix_and_camelize(source_func_name),
            'args': get_cc_arg_proto(function_creators, source_func_name),
            'mod': self._module,
        }

        self._hh.write("""
            struct P_%(target)s : Builtin<P_%(target)s> {
                P_%(target)s() : Builtin("%(target)s") {}
                void operator()(VM vm%(args)s);
            };
        """ % params)

        self._cc.write("""
            void M_%(mod)s::P_%(target)s::operator()(VM vm%(args)s) {
        """ % params)

        write_cc_function_definition(self._cc, function_creators, source_func_name)

        self._cc.write("}")

    def _collect_nodes(self):
        types = []
        functions = []

        tu = TranslationUnit.from_source(join(C_FILES, self._module + C_EXT))
        for node in tu.cursor.get_children():
            kind = node.kind
            if kind == CursorKind.FUNCTION_DECL:
                if not is_blacklisted(name_of(node)):
                    functions.append(node)
            elif kind in {CursorKind.STRUCT_DECL, CursorKind.ENUM_DECL}:
                types.append(node)

        return (types, functions)


    def write(self):
        """
        Print everything into the files.
        """
        (types, functions) = self._collect_nodes()

        self._write_header()

        write_common_builders_pre(self._cc)
        for type_node in types:
            self._write_type(type_node)
        write_common_builders_post(self._cc)

        for function in functions:
            self._write_function(function)

        self._write_footer()

def main(module):
    with Translator(module) as tr:
        tr.write()

if __name__ == '__main__':
    if len(sys.argv) <= 1:
        print("Usage: ./translator.py [module-name]")
    else:
        main(sys.argv[1])

