from common import cc_name_of, oz_in_name_of, oz_out_name_of, unique_str
from fake_type import IntType
from to_cc import to_cc

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
# 'Constant' type

class ConstantStatementsCreator(StatementsCreator):
    def pre(self):
        return "%s = %s;" % (self.cc_prefix, self._context)

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
# 'ListOut' type

class ListOutStatementsCreator(OutStatementsCreator):
    def __init__(self):
        super().__init__()
        self._cc_array_length_name = unique_str()

    def pre(self):
        return super().pre() + """
            int %(u)s;
            auto %(cc)s = &%(u)s;
        """ % {
            'cc': cc_name_of(self._context),
            'u': self._cc_array_length_name
        }

    def post(self):
        return """
            %(oz)s = buildDynamicList(vm, *(%(cc)s), *(%(cc)s) + %(u)s);
        """ % {
            'oz': self.oz_out_prefix,
            'cc': self.cc_name,
            'u': self._cc_array_length_name
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


