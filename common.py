import re
from clang.cindex import CursorKind, TypeKind, Cursor
from collections import defaultdict

C_FILES = 'c-files'
C_EXT = '.c'
SRC = 'src'
CC_EXT = '.cc'
HH_EXT = '.hh'
OUT_EXT = '.out'

TYPES_HH_EXT = '-types.hh'
TYPES_DECL_HH_EXT = '-types-decl.hh'
MODULES_HH_EXT = '-modules.hh'
BUILDERS_HH_EXT = '-builders.hh'
BUILTINS_HH_EXT = 'builtins.hh'
BUILTINS_CC_EXT = 'builtins.cc'

#-------------------------------------------------------------------------------

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

camelsplitrx = re.compile('[-_]')
def camelize(s):
    arr = camelsplitrx.split(s)
    return arr[0].lower() + ''.join(p.capitalize() for p in arr[1:])

def strip_prefix_and_camelize(s):
    """
    Remove the prefix of a string, and change it to CamelCase, e.g.::

        >>> strip_prefix_and_camelize("cairo_push_group_with_content")
        pushGroupWithContent

    If the string has only one word, that word will be returned, e.g.::

        >>> strip_prefix_and_camelize("cairo")
        cairo
    """
    first_underscore = s.find('_', 1)
    if first_underscore == -1:
        if s.startswith('_'):
            s = s[1:]
        return s.lower()
    else:
        return camelize(s[first_underscore+1:])


def strip_common_prefix_and_camelize(lst):
    """
    Remove the common prefix of a list of strings, and change it to CamelCase,
    e.g.::

        >>> strip_common_prefix_and_camelize(["CAIRO_OPERATOR_DEST_OVER",
        ...                                   "CAIRO_OPERATOR_DEST_ATOP",
        ...                                   "CAIRO_OPERATOR_DIFFERENCE"])
        ['destOver', 'destAtop', 'difference']

    """
    min_str = min(lst)
    max_str = max(lst)
    strip_start = len(min_str)

    for i, c in enumerate(min_str):
        if c != max_str[i]:
            break
        if c == '_':
            strip_start = i+1

    return (camelize(s[strip_start:]) for s in lst)

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

def name_of(node):
    spelling = node.spelling.decode('utf-8')
    if spelling:
        return spelling

    typedef_node = Cursor.from_location(node.translation_unit, node.extent.end)
    if typedef_node.kind == CursorKind.TYPEDEF_DECL:
        return name_of(typedef_node)
    else:
        return ''

def is_concrete(struct_decl):
    return struct_decl.is_definition()

#-------------------------------------------------------------------------------

def cc_name_of(name):
    return '_x_cc_' + name

def oz_in_name_of(name):
    return '_x_in_' + name

def oz_out_name_of(name):
    return '_x_out_' + name

CC_NAME_OF_RETURN = cc_name_of('return')

#-------------------------------------------------------------------------------

def group_by(iterable, keyfunc):
    """
    Group the content of an iterable by some key. Returns a dictionary of lists
    of these objects.
    """
    res = defaultdict(list)
    for obj in iterable:
        res[keyfunc(obj)].append(obj)
    return res

