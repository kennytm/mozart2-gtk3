from clang.cindex import CursorKind, TypeKind

C_FILES = 'c-files'
C_EXT = '.c'
SRC = 'src'
CC_EXT = '.cc'
HH_EXT = '.hh'
TYPES_HH_EXT = '-types.hh'
TYPES_DECL_HH_EXT = '-types-decl.hh'

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

    If the string has only one word, that word will be returned, e.g.::

        >>> strip_prefix_and_camelize("cairo")
        cairo
    """
    arr = s.split('_')
    if not arr[0]:
        arr = arr[1:]
    if len(arr) == 1:
        return arr[0]
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


