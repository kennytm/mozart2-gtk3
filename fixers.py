from common import INTEGER_KINDS, name_of
from itertools import product
from clang.cindex import TypeKind
from collections import namedtuple
from creators import *
from constants import OPAQUE_STRUCTS

FieldInfo = namedtuple('FieldInfo', ['field', 'atom', 'builder', 'unbuilder'])

def is_concrete(struct_decl):
    return struct_decl.is_definition() and name_of(struct_decl) not in OPAQUE_STRUCTS

#-------------------------------------------------------------------------------
#
## Assume members of name 'num_???' with a pointer of name '???' forms an array.

def _check_is_array_name(obj_name, objs):
    if not obj_name.startswith('num_'):
        return False
    array_obj_name = obj_name[4:]
    if array_obj_name not in objs:
        return False
    return True


def _check_is_array(obj_name, obj, objs, type_of_obj_retriever):
    if not _check_is_array_name(obj_name, objs):
        return False

    num_type = type_of_obj_retriever(obj)
    array_type = type_of_obj_retriever(objs[obj_name[4:]])

    if array_type.kind != TypeKind.POINTER:
        return False
    if num_type.kind not in INTEGER_KINDS:
        return False

    return True


def array_field_fixer(field_name, num_field_info, fields):
    if not _check_is_array(field_name, num_field_info, fields, lambda info: info.field.type):
        return False

    array_field_name = field_name[4:]

    new_builder = 'buildDynamicList(vm, cc.%(a)s, cc.%(a)s + cc.%(n)s)' % {'a': array_field_name, 'n': field_name}

    del fields[field_name]
    fields[array_field_name] = fields[array_field_name]._replace(builder=new_builder, unbuilder="")

    return True

def array_in_arg_fixer(arg_name, creator, creators):
    if type(creator) != InStatementsCreator:
        return False
    if not _check_is_array(arg_name, creator, creators, lambda c: c._type):
        return False

    array_arg_name = arg_name[4:]
    array_creator = creators[array_arg_name].copy_as_type(ListInStatementsCreator)
    array_creator._context = arg_name
    creators[array_arg_name] = array_creator
    creators[arg_name] = creator.copy_as_type(SkipStatementsCreator)

    return True

def array_out_arg_fixer(arg_name, creator, creators):
    if type(creator) != InStatementsCreator:
        return False
    if not _check_is_array_name(arg_name, creators):
        return False

    array_name = arg_name[4:]
    array_creator = creators[array_name]

    if creator._type.kind != TypeKind.POINTER:
        return False
    if creator._type.get_pointee().kind not in INTEGER_KINDS:
        return False
    if array_creator._type.kind != TypeKind.POINTER:
        return False
    if array_creator._type.get_pointee().kind != TypeKind.POINTER:
        return False

    array_creator = array_creator.copy_as_type(ListOutStatementsCreator)
    array_creator._context = arg_name
    creators[array_name] = array_creator
    creators[arg_name] = creator.copy_as_type(SkipStatementsCreator)

    return True

#-------------------------------------------------------------------------------
#
## Assume 'const structure*' is an in-argument taking an ordinary structure.

def pointer_in_arg_fixer(arg_name, creator, creators):
    if type(creator) != InStatementsCreator:
        return False

    if creator._type.kind != TypeKind.POINTER:
        return False

    pointee = creator._type.get_pointee().get_canonical()
    if pointee.kind != TypeKind.RECORD or not pointee.is_const_qualified():
        return False

    struct = pointee.get_declaration()
    if not is_concrete(struct):
        return False

    creators[arg_name] = creator.copy_as_type(PointerInStatementsCreator)
    return True

#-------------------------------------------------------------------------------

def fixup(fixers):
    def f(obj_dict):
        while True:
            for fixer, (obj_name, obj) in product(fixers, list(obj_dict.items())):
                if fixer(obj_name, obj, obj_dict):
                    break   # loop from the beginning again.
            else:
                break   # break the infinite loop, since there's nothing left to fix.
    return f

fixup_fields = fixup([array_field_fixer])
fixup_args = fixup([pointer_in_arg_fixer, array_in_arg_fixer, array_out_arg_fixer])

__all__ = ['fixup_fields', 'fixup_args', 'FieldInfo', 'is_concrete']
