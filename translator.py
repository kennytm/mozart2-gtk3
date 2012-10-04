#!/usr/bin/env python3

import re
import sys
from os import makedirs
from os.path import join, basename, splitext
from importlib import import_module
from clang.cindex import Config, TranslationUnit, CursorKind
from common import *
from builders import BuildersWriter
from module import ModuleHeaderWriter, ModuleWriter
from datatype import DataTypeDeclWriter, DataTypeWriter
from ozfunc import OzFunction

Config.set_compatibility_check(False)

#def is_blacklisted(name):
#    return any(regex.match(name) for regex in BLACKLISTED)

#-------------------------------------------------------------------------------

def collect_nodes(basename, constants):
    types = []
    functions = []

    tu = TranslationUnit.from_source(join(C_FILES, basename + C_EXT))
    for node in tu.cursor.get_children():
        name = name_of(node)
        if any(regex.match(name) for regex in constants.BLACKLISTED):
            continue

        source_file = node.location.file
        if source_file:
            source_filename = source_file.name.decode('utf-8')
            if not any(regex.match(source_filename) for regex in constants.HEADER_WHITELIST):
                continue

        kind = node.kind
        if kind == CursorKind.FUNCTION_DECL:
            functions.append(node)
        elif kind in {CursorKind.STRUCT_DECL, CursorKind.ENUM_DECL}:
            types.append(node)

    return (types, functions)


def get_mod_name(cursor):
    filename = cursor.location.file.name.decode('utf-8')
    return camelize(splitext(basename(filename))[0])


def translate(basename):
    constants = import_module('constants')
    (types, functions) = collect_nodes(basename, constants)
    grouped_functions = group_by(functions, get_mod_name)

    makedirs(join(SRC, basename + OUT_EXT), exist_ok=True)

    with BuildersWriter(basename, constants) as bf, \
            DataTypeDeclWriter(basename) as dtd, DataTypeWriter(basename) as dt:
        for type_decl in types:
            bf.write_type(type_decl)
            if type_decl.kind == CursorKind.STRUCT_DECL and not is_concrete(type_decl):
                struct_name = name_of(type_decl)
                dtd.write_datatype(struct_name)
                dt.write_datatype(struct_name)

    with ModuleHeaderWriter(basename) as mh, ModuleWriter(basename) as m:
        for modname, functions in grouped_functions.items():
            ozfunc_names = strip_common_prefix_and_camelize(list(map(name_of, functions)))
            with mh.write_module(modname):
                for function, ozfunc_name in zip(functions, ozfunc_names):
                    ozfunc = OzFunction(function, ozfunc_name, constants)
                    mh.write_function(ozfunc)
                    m.write_function(modname, ozfunc)


if __name__ == '__main__':
    if len(sys.argv) <= 1:
        print("Usage: ./translator.py [module-name]")
    else:
        translate(sys.argv[1])

