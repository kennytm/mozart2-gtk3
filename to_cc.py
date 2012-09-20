# Convert a clang Type to a C++ declaration.

from collections import Callable
from clang.cindex import TypeKind, CursorKind

# A convertor should perform have the signature:
#
#   convertor(Type) -> (pre, mid, post)
#
# where a C++ declaration will be structured as
#
#   <pre> <mid>name<post>;

def convert_complex(typ):
    (pre, mid, post) = convert(typ.element_type)
    mid = '_Complex ' + mid
    return (pre, mid, post)

def convert_pointer(pointer_char):
    def do(typ):
        pointee = typ.get_pointee()
        if pointee.kind == TypeKind.UNEXPOSED:
            pointee = pointee.get_canonical()

        (pre, mid, post) = convert(pointee)
        if pointee.kind in {TypeKind.CONSTANTARRAY, TypeKind.FUNCTIONPROTO}:
            return (pre, mid + '(' + pointer_char, ')' + post)
        else:
            return (pre, mid + pointer_char, post)
    return do

def convert_array(typ):
    (pre, mid, post) = convert(typ.element_type)
    return (pre, mid, '[' + str(typ.element_count) + ']' + post)

RECORD_KEYWORD = {
    CursorKind.STRUCT_DECL: 'struct',
    CursorKind.UNION_DECL: 'union',
    CursorKind.ENUM_DECL: 'enum',
}

def convert_canonical(typ):
    decl = typ.get_declaration()
    struct_name = decl.displayname.decode('utf-8')
    if struct_name:
        sb = [struct_name]
    else:
        sb = [RECORD_KEYWORD[decl.kind], ' { ']
        for node in decl.get_children():
            name = node.spelling.decode('utf-8')
            sb.append(to_cc(node.type, name))
            sb.append('; ')
        sb.append('}')
    return (''.join(sb), '', '')

def convert_function(typ):
    # BUG: ty.get_result() doesn't return an array for an array return type.
    (pre, mid, post) = convert(typ.get_result())

    new_post = '(' + ', '.join(map(to_cc, typ.argument_types()))
    if typ.is_function_variadic():
        new_post += ', ...'
    new_post += ')'

    return (pre, mid, new_post + post)

def convert_keyword(keyword):
    def do(typ):
        return (keyword, '', '')
    return do

KIND_MAP = {
    TypeKind.VOID: convert_keyword('void'),
    TypeKind.BOOL: convert_keyword('bool'),
    TypeKind.INT: convert_keyword('int'),
    TypeKind.CHAR_U: convert_keyword('char'),
    TypeKind.UCHAR: convert_keyword('unsigned char'),
    TypeKind.CHAR16: convert_keyword('char16_t'),
    TypeKind.CHAR32: convert_keyword('char32_t'),
    TypeKind.USHORT: convert_keyword('unsigned short'),
    TypeKind.UINT: convert_keyword('unsigned'),
    TypeKind.ULONG: convert_keyword('unsigned long'),
    TypeKind.ULONGLONG: convert_keyword('unsigned long long'),
    TypeKind.UINT128: convert_keyword('uint128_t'),
    TypeKind.CHAR_S: convert_keyword('char'),
    TypeKind.SCHAR: convert_keyword('signed char'),
    TypeKind.WCHAR: convert_keyword('wchar_t'),
    TypeKind.SHORT: convert_keyword('short'),
    TypeKind.INT: convert_keyword('int'),
    TypeKind.LONG: convert_keyword('long'),
    TypeKind.LONGLONG: convert_keyword('long long'),
    TypeKind.INT128: convert_keyword('int128_t'),
    TypeKind.FLOAT: convert_keyword('float'),
    TypeKind.DOUBLE: convert_keyword('double'),
    TypeKind.LONGDOUBLE: convert_keyword('long double'),
    TypeKind.NULLPTR: convert_keyword('nullptr_t'),
    TypeKind.OBJCID: convert_keyword('id'),
    TypeKind.OBJCCLASS: convert_keyword('Class'),
    TypeKind.OBJCSEL: convert_keyword('SEL'),

    TypeKind.TYPEDEF: convert_canonical,

    TypeKind.POINTER: convert_pointer('*'),
    TypeKind.OBJCOBJECTPOINTER: convert_pointer('*'),
    TypeKind.BLOCKPOINTER: convert_pointer('^'),
    TypeKind.LVALUEREFERENCE: convert_pointer('&'),
    TypeKind.RVALUEREFERENCE: convert_pointer('&&'),

    TypeKind.COMPLEX: convert_complex,
    TypeKind.CONSTANTARRAY: convert_array,
    TypeKind.UNEXPOSED: convert_canonical,

    TypeKind.FUNCTIONPROTO: convert_function,
    TypeKind.RECORD: convert_canonical,
    TypeKind.OBJCINTERFACE: convert_canonical,
    TypeKind.ENUM: convert_canonical,
}

def convert(typ):
    (pre, mid, post) = KIND_MAP[typ.kind](typ)

    if typ.is_const_qualified():
        mid += 'const '
    if typ.is_volatile_qualified():
        mid += 'volatile '
    if typ.is_restrict_qualified():
        mid += 'restrict '

    return (pre, mid, post)


def to_cc(typ, name=''):
    (pre, mid, post) = convert(typ)
    return (pre + ' ' + mid + name + post).rstrip()

__all__ = ['to_cc']

