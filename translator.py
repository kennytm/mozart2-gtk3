#!/usr/bin/env python3

import os
import sys
import re
from os.path import join
from clang.cindex import TranslationUnit, Config, CursorKind
from constants import *
from builders import *
from common import *

Config.set_compatibility_check(False)

def create_datatype(struct_name):
    """
    Create a Mozart/Oz DataType, given the name of an incomplete C structure.
    The generated DataType will then be based on a C pointer of that structure.
    The data type will contain a ``value()`` method to return the pointer to the
    structure. The name of the DataType is ``D_(name of C structure)``.
    """

    params = {'s': struct_name}

    return ("""
        namespace m2g3
        {
            class D_%(s)s;
        }

        namespace mozart
        {
            using m2g3::D_%(s)s;

            #ifndef MOZART_GENERATOR
            #include "D_%(s)s-implem-decl.hh"
            #endif
        }

        namespace m2g3
        {
            class D_%(s)s : public ::mozart::DataType<D_%(s)s>, ::mozart::StoredAs<%(s)s*>
            {
            public:
                typedef ::mozart::SelfType<D_%(s)s>::Self Self;

                D_%(s)s(%(s)s* value) : _value(value) {}

                static void create(%(s)s*& self, ::mozart::VM vm, %(s)s* value) {self = value; }
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
    """ % params, """
        namespace mozart {
            using m2g3::D_%(s)s;
            #include "D_%(s)s-implem.hh"
        }

        namespace m2g3 {
            void D_%(s)s::create(%(s)s*& self, ::mozart::VM vm, ::mozart::GR gr, Self from)
            {
                self = from->_value;
            }
        }
    """ % params)

def is_blacklisted(name):
    return any(regex.match(name) for regex in BLACKLISTED)

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
            'types-decl-hh-ext': TYPES_DECL_HH_EXT,
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
            #include <unordered_map>
            #include <vector>
            #include <type_traits>
            #include "%(hh-file)s%(hh-ext)s"
            #include "%(mod)s%(types-decl-hh-ext)s"

            %(common-header)s

        """ % format_params)

        self._cc_file.writelines(common_unbuild_functions())

        self._types_decl_hh_file.write("""
            #ifndef %(guard)s_DATATYPES_DECL
            #define %(guard)s_DATATYPES_DECL

            #include "../c-files/%(mod)s.c"
            #include <mozart.hh>
        """ % format_params)

        self._types_hh_file.write("""
            #ifndef %(guard)s_DATATYPES
            #define %(guard)s_DATATYPES

            #include "%(mod)s%(types-decl-hh-ext)s"
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
            #endif
        """)

        self._types_hh_file.write("""
            }

            #endif
        """)

    def _print_type(self, type_node):
        """
        Print a single type.
        """
        if is_blacklisted(name_of(type_node)):
            return

        self._cc_file.write(builder(type_node))

        if type_node.kind == CursorKind.STRUCT_DECL and not is_concrete(type_node):
            (decl_hh, hh) = create_datatype(name_of(type_node))
            self._types_decl_hh_file.writelines(decl_hh)
            self._types_hh_file.write(hh)

    def _print_function(self, function):
        """
        Print a single function.
        """
        source_func_name = name_of(function)
        try:
            (arg_proto, cc_statements) = get_cc_function_definition(function, source_func_name)
        except NotImplementedError as e:
            print('Note: Current function = ' + source_func_name, file=sys.stderr)
            raise

        params = {
            'target': strip_prefix_and_camelize(source_func_name),
            'args': arg_proto,
            'mod': self._module,
        }

        self._hh_file.write("""
                struct P_%(target)s : Builtin<P_%(target)s>
                {
                    P_%(target)s() : Builtin("%(target)s") {}
                    void operator()(VM vm%(args)s);
                };
        """ % params)

        self._cc_file.write("""
            void M_%(mod)s::P_%(target)s::operator()(VM vm%(args)s)
            {
        """ % params)
        for statement in cc_statements:
            self._cc_file.write('\n')
            self._cc_file.write(statement)
        self._cc_file.write("}\n")

    def print(self):
        """
        Print everything into the files.
        """
        self._print_header()

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

        for type_node in types:
            self._print_type(type_node)
        for function in functions:
            self._print_function(function)

        self._print_footer()

def main(module):
    with Translator(module) as tr:
        tr.print()

if __name__ == '__main__':
    if len(sys.argv) <= 1:
        print("Usage: ./translator.py [module-name]")
    else:
        main(sys.argv[1])

