#!/usr/bin/env python3

import os
import sys
import re
from os.path import join
from clang.cindex import TranslationUnit, Config, CursorKind

C_FILES = 'c-files'
C_EXT = '.c'
SRC = 'src'
CC_EXT = '.cc'
HH_EXT = '.hh'

Config.set_compatibility_check(False)

def capitalize(s):
    return s[0].upper() + s[1:]

def strip_prefix_and_camelize(s):
    return ''.join(p.upper() for p in s.split('_')[1:])

class Translator:
    def __init__(self, module):
        self._module = module
        self._cc_file = open(join(SRC, module + CC_EXT), 'w')
        self._hh_file = open(join(SRC, module + HH_EXT), 'w')

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
            'guard': 'M2G3_MODULE_' + self._module.upper(),
            'mod': capitalize(self._module),
            'hh-file': self._module,
            'hh-ext': HH_EXT
        }

        self._hh_file.write("""
            #ifndef %(guard)s
            #define %(guard)s

            #include <mozart.hh>

            namespace m2g3 {

            struct Mod%(mod)s : Module
            {
                Mod%(mod)s() : Module("%(mod)s") {}
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

    def print(self):
        self._print_header()

        tu = TranslationUnit.from_source(join(C_FILES, self._module + C_EXT))
        for node in tu.cursor.get_children():
            kind = node.kind

        self._print_footer()

def main(module):
    with Translator(module) as tr:
        tr.print()

if __name__ == '__main__':
    if len(sys.argv) <= 1:
        print("Usage: ./translator.py [module-name]")
    else:
        main(sys.argv[1])

