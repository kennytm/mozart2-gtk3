from common import INTEGER_KINDS
from itertools import product
from clang.cindex import TypeKind
from collections import namedtuple

FieldInfo = namedtuple('FieldInfo', ['field', 'atom', 'builder', 'unbuilder'])

#-------------------------------------------------------------------------------

def array_field_fixer(field_name, fields):
    if not field_name.startswith('num_'):
        return False

    array_field_name = field_name[4:]
    if array_field_name not in fields:
        return False

    num_field = fields[field_name].field
    (array_field, array_atom_name, _, _) = fields[array_field_name]

    if array_field.type.kind != TypeKind.POINTER:
        return False
    if num_field.type.kind not in INTEGER_KINDS:
        return False

    new_builder = 'buildDynamicList(vm, cc.%(a)s, cc.%(a)s + cc.%(n)s)' % {'a': array_field_name, 'n': field_name}

    del fields[field_name]
    fields[array_field_name] = FieldInfo(array_field, array_atom_name, new_builder, "")

    return True

#-------------------------------------------------------------------------------

def fixup(fixers):
    def f(obj_dict):
        while True:
            for fixer, obj_name in product(fixers, list(obj_dict)):
                if fixer(obj_name, obj_dict):
                    break   # loop from the beginning again.
            else:
                break   # break the infinite loop, since there's nothing left to fix.
    return f

fixup_fields = fixup([array_field_fixer])
fixup_args = fixup([])

__all__ = ['fixup_fields', 'fixup_args', 'FieldInfo']
