from constants import *
from common import *
from fake_type import PointerOf, IntType
from to_cc import to_cc
from itertools import chain

class StatementsCreator:
    def _make_prefix(self, name):
        return 'auto ' + name if self._with_declaration else name

    @property
    def cc_name(self):
        return cc_name_of(self._name)

    @property
    def cc_prefix(self):
        return self._make_prefix(self.cc_name)

    @property
    def oz_in_name(self):
        return oz_in_name_of(self._name)

    @property
    def oz_in_prefix(self):
        return self._make_prefix(self.oz_in_name)

    @property
    def oz_out_name(self):
        return oz_out_name_of(self._name)

    @property
    def oz_out_prefix(self):
        return self._make_prefix(self.oz_out_name)

    def __copy__(self):
        new_copy = type(self)()
        new_copy._type = self._type
        new_copy._name = self._name
        new_copy._with_declaration = self._with_declaration
        new_copy._context = self._context
        return new_copy

    @staticmethod
    def get_oz_inout():
        return None

    def pre(self):
        cc_complete_name = unique_str()
        cc_decl = to_cc(self._type.get_pointee(), cc_complete_name)
        return "%s; %s = &%s;" % (cc_decl, self.cc_prefix, cc_complete_name)

    def post(self):
        return ""

#-------------------------------------------------------------------------------
# "Out" type.

class OutStatementsCreator(StatementsCreator):
    @staticmethod
    def get_oz_inout():
        return 'Out'

    def post(self):
        return self.oz_out_prefix + ' = build(vm, *' + self.cc_name + ');'

#-------------------------------------------------------------------------------
# "In" type.

class InStatementsCreator(StatementsCreator):
    @staticmethod
    def get_oz_inout():
        return 'In'

    def pre(self):
        expr = 'unbuild(vm, ' + self.oz_in_name + ', ' + self.cc_name + ');'
        if self._with_declaration:
            expr = to_cc(self._type, self.cc_name) + ';\n' + expr
        return expr

#-------------------------------------------------------------------------------
# "InOut" type.

class InOutStatementsCreator(OutStatementsCreator):
    @staticmethod
    def get_oz_inout():
        return 'InOut'

    def pre(self):
        in_creator = InStatementsCreator()
        in_creator._type = self._type.get_pointee()
        in_creator._name = unique_str()
        in_creator._with_declaration = True
        in_creator._context = self._context

        return """
            auto& %(uoz)s = %(oz)s;
            %(pre)s
            %(cc)s = &%(ucc)s;
        """ % {
            'pre': in_creator.pre(),
            'cc': self.cc_prefix,
            'ucc': in_creator.cc_name,
            'uoz': in_creator.oz_in_name,
            'oz': self.oz_in_name,
        }

#-------------------------------------------------------------------------------
# 'NodeOut' type

class NodeOutStatementsCreator(OutStatementsCreator):
    def post(self):
        return """
            auto %(u)s = static_cast<std::pair<ProtectedNode, VM>*>(*(%(cc)s));
            if (%(u)s != nullptr)
                %(oz)s = UnstableNode(vm, *%(u)s->first);
            else
                %(oz)s = build(vm, unit);
        """ % {'oz':self.oz_out_prefix, 'cc':self.cc_name, 'u':unique_str()}

#-------------------------------------------------------------------------------
# 'NodeIn' type

class NodeInStatementsCreator(InStatementsCreator):
    def pre(self):
        return """
            %s = new std::pair<ProtectedNode, VM>(ozProtect(vm, %s), vm);
        """ % (self.cc_prefix, self.oz_in_name)

#-------------------------------------------------------------------------------
# 'NodeDeleter' type

class NodeDeleterStatementsCreator(StatementsCreator):
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
        """ % {'p':self.cc_prefix, 'l':lambda_args, 'u':unique_str(), 'n':self._context}

#-------------------------------------------------------------------------------
# 'AddressIn' type

class AddressInStatementsCreator(InStatementsCreator):
    def pre(self):
        return """
            %s = reinterpret_cast<%s>(IntegerValue(%s).intValue(vm));
        """ % (self.cc_prefix, to_cc(self._type), self.oz_in_name)

#-------------------------------------------------------------------------------
# 'Skip' type

class SkipStatementsCreator(StatementsCreator):
    def pre(self):
        return ""

#-------------------------------------------------------------------------------
# 'ListIn' type

class ListInStatementsCreator(InStatementsCreator):
    def pre(self):
        list_length_creator = SkipStatementsCreator()
        list_length_creator._type = IntType()
        list_length_creator._name = self._context
        list_length_creator._with_declaration = True

        return """
            std::vector<std::remove_cv<%(t)s>::type> %(u)s;
            ozListForEach(vm, %(oz)s, [vm, &%(u)s](RichNode node) {
                std::remove_cv<%(t)s>::type content;
                unbuild(vm, node, content);
                %(u)s.push_back(std::move(content));
            }, MOZART_STR("%(t)s"));
            %(cc)s = %(u)s.data();
            %(len)s = %(u)s.size();
        """ % {
            'u': unique_str(),
            't': to_cc(self._type.get_pointee()),
            'oz': self.oz_in_name,
            'cc': self.cc_prefix,
            'len': list_length_creator.cc_prefix,
        }

#-------------------------------------------------------------------------------
# 'PointerIn' type

class PointerInStatementsCreator(InStatementsCreator):
    def pre(self):
        return """
            std::remove_cv<%(t)s>::type %(u)s;
            unbuild(vm, %(oz)s, %(u)s);
            %(cc)s = &%(u)s;
        """ % {
            't': to_cc(self._type.get_pointee()),
            'u': unique_str(),
            'cc': self.cc_prefix,
            'oz': self.oz_in_name,
        }

#-------------------------------------------------------------------------------

def get_statement_creators(func_cursor, c_func_name):
    inouts = SPECIAL_INOUTS.get(c_func_name, {})
    globals_dict = globals()

    def decode_inout(arg_name, default, typ):
        inout_tuple = default
        try:
            inout_tuple = inouts[arg_name]
        except KeyError:
            type_name = to_cc(typ)
            inout_tuple = SPECIAL_INOUTS_FOR_TYPES.get(type_name, default)

        if isinstance(inout_tuple, str):
            inout = inout_tuple
            context = None
        else:
            (inout, context) = inout_tuple

        creator = globals_dict[inout + 'StatementsCreator']()
        creator._context = context
        creator._name = arg_name
        creator._type = typ
        return creator

    for arg in func_cursor.get_children():
        if arg.kind != CursorKind.PARM_DECL:
            continue

        arg_name = name_of(arg)
        yield decode_inout(arg_name, 'In', arg.type)


    return_type = func_cursor.result_type.get_canonical()
    if return_type.kind != TypeKind.VOID:
        yield decode_inout('return', 'Out', PointerOf(return_type))


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
        creator._with_declaration = True
        cc_statements.append(creator.pre())

    call_args = (creator.cc_name for creator in creators if creator._name != 'return')
    call_statement = c_func_name + '(' + ', '.join(call_args) + ');'
    if func_cursor.result_type.get_canonical().kind != TypeKind.VOID:
        call_statement = '*' + CC_NAME_OF_RETURN + ' = ' + call_statement
    cc_statements.append(call_statement)

    for creator in creators:
        creator._with_declaration = False
        cc_statements.append(creator.post())

    arg_proto = []
    for creator in creators:
        inout = creator.get_oz_inout()
        if inout in {'In', 'InOut'}:
            arg_proto.append(', In ' + creator.oz_in_name)
        if inout in {'Out', 'InOut'}:
            arg_proto.append(', Out ' + creator.oz_out_name)

    try:
        cc_statements.append(FUNCTION_TEARDOWN[c_func_name])
    except KeyError:
        pass

    return (''.join(arg_proto), cc_statements)

__all__ = ['get_cc_function_definition', 'CC_NAME_OF_RETURN',
           'cc_name_of', 'oz_in_name_of', 'oz_out_name_of']

