from common import INTEGER_KINDS, name_of, is_concrete
from itertools import product
from clang.cindex import TypeKind
from collections import namedtuple
from arguments import *

FieldInfo = namedtuple('FieldInfo', ['field', 'atom', 'builder', 'unbuilder'])

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

    new_builder = 'buildDynamicList(vm, cc.{0}, cc.{0} + cc.{1})'.format(array_field_name, field_name)

    del fields[field_name]
    fields[array_field_name] = fields[array_field_name]._replace(builder=new_builder, unbuilder="")

    return True

def array_in_arg_fixer(arg_name, argument, arguments):
    if type(argument) != InArgument:
        return False
    if not _check_is_array(arg_name, argument, arguments, lambda c: c._type):
        return False

    array_arg_name = arg_name[4:]
    array_argument = arguments[array_arg_name].copy_as_type(ListInArgument)
    array_argument._context = arg_name
    arguments[array_arg_name] = array_argument
    arguments[arg_name] = argument.copy_as_type(SkipArgument)

    return True

def array_out_arg_fixer(arg_name, argument, arguments):
    if type(argument) != InArgument:
        return False
    if not _check_is_array_name(arg_name, arguments):
        return False

    array_name = arg_name[4:]
    array_argument = arguments[array_name]

    if argument._type.kind != TypeKind.POINTER:
        return False
    if argument._type.get_pointee().kind not in INTEGER_KINDS:
        return False
    if array_argument._type.kind != TypeKind.POINTER:
        return False
    if array_argument._type.get_pointee().kind != TypeKind.POINTER:
        return False

    array_argument = array_argument.copy_as_type(ListOutArgument)
    array_argument._context = arg_name
    arguments[array_name] = array_argument
    arguments[arg_name] = argument.copy_as_type(SkipArgument)

    return True

#-------------------------------------------------------------------------------
#
## Assume 'const structure*' is an in-argument taking an ordinary structure.

def pointer_in_arg_fixer(arg_name, argument, arguments):
    if type(argument) != InArgument:
        return False

    if argument._type.kind != TypeKind.POINTER:
        return False

    pointee = argument._type.get_pointee().get_canonical()
    if pointee.kind != TypeKind.RECORD or not pointee.is_const_qualified():
        return False

    struct = pointee.get_declaration()
    if not is_concrete(struct):
        return False

    arguments[arg_name] = argument.copy_as_type(PointerInArgument)
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

__all__ = ['fixup_fields', 'fixup_args', 'FieldInfo']
