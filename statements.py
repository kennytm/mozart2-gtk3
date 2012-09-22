from constants import *
from common import *
from fake_type import PointerOf
from to_cc import to_cc
from itertools import chain

class StatementsCreator:
    @property
    def cc_name(self):
        return self._cc_name

    @cc_name.setter
    def cc_name(self, name):
        self._cc_name = name
        self._cc_prefix = 'auto ' + name if self._with_declaration else name

    @property
    def oz_name(self):
        return self._oz_name

    @oz_name.setter
    def oz_name(self, name):
        self._oz_name = name
        self._oz_prefix = 'auto ' + name if self._with_declaration else name

    @property
    def with_declaration(self):
        return self._with_declaration

    @with_declaration.setter
    def with_declaration(self, with_decl):
        self._with_declaration = with_decl
        if not with_decl:
            self._oz_prefix = self._oz_name
            self._cc_prefix = self._cc_name
        else:
            self._oz_prefix = 'auto ' + self._oz_name
            self._cc_prefix = 'auto ' + self._cc_name

    def __copy__(self):
        new_copy = type(self)()
        new_copy._type = self._type
        new_copy._cc_name = self._cc_name
        new_copy._oz_name = self._oz_name
        new_copy._with_declaration = self._with_declaration
        new_copy._context = self._context
        new_copy._cc_prefix = self._cc_prefix
        new_copy._oz_prefix = self._oz_prefix
        return new_copy

    @property
    def oz_inout(self):
        return None

    def pre(self):
        cc_complete_name = unique_str()
        cc_decl = to_cc(self._type.get_pointee(), cc_complete_name)
        return "%s; %s = &%s;" % (cc_decl, self._cc_prefix, cc_complete_name)

    def post(self):
        return ""

#-------------------------------------------------------------------------------
# "Out" type.

class OutStatementsCreator(StatementsCreator):
    @property
    def oz_inout(self):
        return 'Out'

    def post(self):
        return self._oz_prefix + ' = build(vm, ' + self._cc_name + ');'

#-------------------------------------------------------------------------------
# "In" type.

class InStatementsCreator(StatementsCreator):
    @property
    def oz_inout(self):
        return 'In'

    def pre(self):
        expr = 'unbuild(vm, ' + self._oz_name + ', ' + self._cc_name + ');'
        if self._with_declaration:
            expr = to_cc(self._type, self._cc_name) + ';\n' + expr
        return expr

#-------------------------------------------------------------------------------
# 'NodeOut' type

class NodeOutStatementsCreator(StatementsCreator):
    @property
    def oz_inout(self):
        return 'Out'

    def post(self):
        return """
            auto %(u)s = static_cast<std::pair<ProtectedNode, VM>*>(*(%(cc)s));
            %(oz)s = UnstableNode(vm, *%(u)s->first);
        """ % {'oz':self._oz_prefix, 'cc':self._cc_name, 'u':unique_str()}

#-------------------------------------------------------------------------------
# 'NodeIn' type

class NodeInStatementsCreator(InStatementsCreator):
    @property
    def oz_inout(self):
        return 'In'

    def pre(self):
        return """
            %s = new std::pair<ProtectedNode, VM>(ozProtect(vm, %s), vm);
        """ % (self._cc_prefix, self._oz_name)

#-------------------------------------------------------------------------------
# 'NodeDeleter' type

class NodeDeleterStatementsCreator(InStatementsCreator):
    @property
    def oz_inout(self):
        return None

    def pre(self):
        args = self._type.get_canonical().get_pointee().argument_types()
        lambda_args = ', '.join(to_cc(subtype, name='x_lambda_'+str(i))
                                for i, subtype in enumerate(args))
        return """
            %(p)s = [](%(l)s) {
                auto %(u)s = static_cast<std::pair<ProtectedNode, VM>*>(x_lambda_%(n)s);
                ozUnprotect(%(u)s->second, %(u)s->first);
                delete %(u)s;
            };
        """ % {'p':self._cc_prefix, 'l':lambda_args, 'u':unique_str(), 'n':self._context}

#-------------------------------------------------------------------------------

def get_statement_creators(func_cursor, c_func_name):
    inouts = SPECIAL_INOUTS.get(c_func_name, {})
    globals_dict = globals()

    def decode_inout(arg_name, default, real_arg_name, typ):
        inout_tuple = default
        try:
            inout_tuple = inouts[arg_name]
        except KeyError:
            if typ.kind == TypeKind.TYPEDEF:
                type_name = name_of(typ.get_declaration())
                inout_tuple = SPECIAL_INOUTS_FOR_TYPES.get(type_name, default)

        if isinstance(inout_tuple, str):
            inout = inout_tuple
            context = None
        else:
            (inout, context) = inout_tuple

        creator = globals_dict[inout + 'StatementsCreator']()
        creator._context = context
        creator._oz_name = real_arg_name
        creator._cc_name = 'x_cc_' + real_arg_name
        creator._type = typ
        return creator

    for arg in func_cursor.get_children():
        if arg.kind != CursorKind.PARM_DECL:
            continue

        arg_name = name_of(arg)
        yield decode_inout(arg_name, 'In', arg_name, arg.type)


    return_type = func_cursor.result_type.get_canonical()
    if return_type.kind != TypeKind.VOID:
        yield decode_inout('return', 'Out', '_x_oz_return', PointerOf(return_type))


def get_cc_function_definition(func_cursor, c_func_name):
    """
    Get the C++ function definition from a clang function Cursor. The result is
    a 2-tuple, with the first being a C++ code of the signature of the Oz
    built-in procedure (e.g. ``, In arg1, Out arg2``), and the second being a
    list of C++ statements of the built-in procedure.
    """

    creators = list(get_statement_creators(func_cursor, c_func_name))

    cc_statements = []

    try:
        cc_statements.append(FUNCTION_SETUP[c_func_name])
    except KeyError:
        pass

    for creator in creators:
        creator.with_declaration = True
        cc_statements.append(creator.pre())

    call_args = (creator.cc_name for creator in creators
                                 if creator.oz_name != '_x_oz_return')
    call_statement = c_func_name + '(' + ', '.join(call_args) + ');'
    if func_cursor.result_type.get_canonical().kind != TypeKind.VOID:
        call_statement = '*_x_cc__x_oz_return = ' + call_statement
    cc_statements.append(call_statement)

    for creator in creators:
        creator.with_declaration = False
        cc_statements.append(creator.post())

    arg_proto = ''.join(', ' + creator.oz_inout + ' ' + creator.oz_name
                        for creator in creators
                        if creator.oz_inout is not None and creator.oz_name != 'return')

    try:
        cc_statements.append(FUNCTION_TEARDOWN[c_func_name])
    except KeyError:
        pass

    return (arg_proto, cc_statements)

__all__ = ['get_cc_function_definition']

