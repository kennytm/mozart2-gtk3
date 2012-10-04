from collections import OrderedDict
from clang.cindex import TypeKind, CursorKind
from common import *
from fixers import fixup_args
from fake_type import PointerOf
from to_cc import to_cc
from arguments import In, Out

def _decode_argument(args_dict, arg_name, default, typ, constants):
    arg_tuple = None
    try:
        arg_tuple = args_dict[arg_name]
    except KeyError:
        if arg_name == 'return':
            type_name = to_cc(typ.get_pointee())
            arg_tuple = constants.SPECIAL_ARGUMENTS_FOR_RETURN_TYPES.get(type_name)
        if arg_tuple is None:
            type_name = to_cc(typ)
            arg_tuple = constants.SPECIAL_ARGUMENTS_FOR_TYPES.get(type_name, default)

    if isinstance(arg_tuple, type):
        inout = arg_tuple
        context = None
    else:
        (inout, context) = arg_tuple

    arg = inout()
    arg._context = context
    arg._name = arg_name
    arg._type = typ
    return arg


def _get_arguments(func_cursor, c_func_name, constants):
    args_dict = find_from_regex_map(constants.SPECIAL_ARGUMENTS, c_func_name, {})

    for arg in func_cursor.get_children():
        if arg.kind != CursorKind.PARM_DECL:
            continue

        arg_name = name_of(arg)
        yield _decode_argument(args_dict, arg_name, In, arg.type, constants)


    return_type = func_cursor.result_type.get_canonical()
    if return_type.kind != TypeKind.VOID:
        yield _decode_argument(args_dict, 'return', Out, PointerOf(return_type), constants)



class OzFunction:
    def __init__(self, function, oz_function_name, constants):
        c_func_name = name_of(function)
        self._source_function_name = c_func_name
        self.oz_function_name = oz_function_name

        try:
            (arg_proto, func_def) = constants.SPECIAL_FUNCTIONS[c_func_name]
            self._arg_proto = arg_proto
            self._func_def = func_def

        except KeyError:
            pre_fixup_args = _get_arguments(function, c_func_name, constants)
            pre_fixup_args_odict = OrderedDict((c._name, c) for c in pre_fixup_args)

            fixup_args(pre_fixup_args_odict, constants)

            self._args = pre_fixup_args_odict.values()
            self._arg_proto = None
            self._func_def = None

            self._pre_setup = find_from_regex_map(constants.FUNCTION_PRE_SETUP, c_func_name, '')
            self._post_setup = find_from_regex_map(constants.FUNCTION_POST_SETUP, c_func_name, '')
            self._pre_teardown = find_from_regex_map(constants.FUNCTION_PRE_TEARDOWN, c_func_name, '')
            self._post_teardown = find_from_regex_map(constants.FUNCTION_POST_TEARDOWN, c_func_name, '')

    def get_arg_proto(self):
        if self._arg_proto is None:
            content = []
            for arg in self._args:
                inout = arg.get_oz_inout()
                if inout in {'In', 'InOut'}:
                    content.append(', In ')
                    content.append(arg.oz_in_name)
                if inout in {'Out', 'InOut'}:
                    content.append(', Out ')
                    content.append(arg.oz_out_name)
            self._arg_proto = ''.join(content)

        return self._arg_proto

    def write_to(self, target):
        if self._func_def is not None:
            target.write(self._func_def)
            return

        target.write(self._pre_setup)

        for arg in self._args:
            arg._with_declaration = True
            arg.pre(target)

        target.write(self._post_setup)

        call_args = (a.cc_name for a in self._args if a._name != 'return')
        call_statement = self._source_function_name + '(' + ', '.join(call_args) + ');'
        if any(a._name == 'return' for a in self._args):
            call_statement = '*' + CC_NAME_OF_RETURN + ' = ' + call_statement
        target.write(call_statement)

        target.write(self._pre_teardown)

        for arg in self._args:
            arg._with_declaration = False
            arg.post(target)

        target.write(self._post_teardown)

