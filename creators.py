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
        return self.copy_as_type(type(self))

    def copy_as_type(self, new_type):
        assert issubclass(new_type, StatementsCreator)
        new_copy = new_type()
        new_copy._type = self._type
        new_copy._name = self._name
        new_copy._with_declaration = self._with_declaration
        new_copy._context = self._context
        return new_copy

    @staticmethod
    def get_oz_inout():
        return None

    def pre(self, formatter):
        cc_complete_name = unique_str()
        cc_decl = to_cc(self._type.get_pointee(), cc_complete_name)
        formatter.write(cc_decl + ' {};')
        formatter.write(self.cc_prefix + ' = &' + cc_complete_name + ';')

    def post(self, formatter):
        pass

    def __init__(self):
        self._with_declaration = False
        self._context = None

#-------------------------------------------------------------------------------
# "Out" type.

class OutStatementsCreator(StatementsCreator):
    @staticmethod
    def get_oz_inout():
        return 'Out'

    def post(self, formatter):
        formatter.write(self.oz_out_prefix + ' = build(vm, *' + self.cc_name + ');')

#-------------------------------------------------------------------------------
# "In" type.

class InStatementsCreator(StatementsCreator):
    @staticmethod
    def get_oz_inout():
        return 'In'

    def pre(self, formatter):
        if self._with_declaration:
            formatter.write(to_cc(self._type, self.cc_name) + ';')
        formatter.write('unbuild(vm, ' + self.oz_in_name + ', ' + self.cc_name + ');')

#-------------------------------------------------------------------------------
# "InOut" type.

class InOutStatementsCreator(OutStatementsCreator):
    @staticmethod
    def get_oz_inout():
        return 'InOut'

    def pre(self, formatter):
        in_creator = InStatementsCreator()
        in_creator._type = self._type.get_pointee()
        in_creator._name = unique_str()
        in_creator._with_declaration = True
        in_creator._context = self._context

        formatter.write('auto &' + in_creator.oz_in_name + ' = ' + self.oz_in_name + ';')
        in_creator.pre(formatter)
        formatter.write(self.cc_prefix + ' = &' + in_creator.cc_name + ';')

#-------------------------------------------------------------------------------
# 'NodeOut' type

class NodeOutStatementsCreator(OutStatementsCreator):
    def post(self, formatter):
        formatter.write(self.oz_out_prefix + ' = unwrapNode(*(' + self.cc_name + '));')

#-------------------------------------------------------------------------------
# 'NodeIn' type

class NodeInStatementsCreator(InStatementsCreator):
    def pre(self, formatter):
        formatter.write(self.cc_prefix + ' = wrapNode(vm, ' + self.oz_in_name + ');')

#-------------------------------------------------------------------------------
# 'NodeDeleter' type

class NodeDeleterStatementsCreator(StatementsCreator):
    def pre(self, formatter):
        args = self._type.get_canonical().get_pointee().argument_types()
        lambda_args = ', '.join(to_cc(subtype, name='x_lambda_'+str(i))
                                for i, subtype in enumerate(args))
        formatter.write("""
            %s = [](%s) { deleteWrappedNode(x_lambda_%s); };
        """ % (self.cc_prefix, lambda_args, self._context))

#-------------------------------------------------------------------------------
# 'AddressIn' type

class AddressInStatementsCreator(InStatementsCreator):
    def pre(self, formatter):
        formatter.write("""
            %s = reinterpret_cast<%s>(IntegerValue(%s).intValue(vm));
        """ % (self.cc_prefix, to_cc(self._type), self.oz_in_name))

#-------------------------------------------------------------------------------
# 'Skip' type

class SkipStatementsCreator(StatementsCreator):
    def pre(self, formatter):
        pass

#-------------------------------------------------------------------------------
# 'Constant' type

class ConstantStatementsCreator(StatementsCreator):
    def pre(self, formatter):
        formatter.write(self.cc_prefix + ' = ' + self._context + ';')

#-------------------------------------------------------------------------------
# 'ListIn' type

class ListInStatementsCreator(InStatementsCreator):
    def pre(self, formatter):
        formatter.write("""
            std::vector<std::remove_cv<%(t)s>::type> %(u)s;
            ozListForEach(vm, %(oz)s, [vm, &%(u)s](UnstableNode& node) {
                std::remove_cv<%(t)s>::type content;
                unbuild(vm, node, content);
                %(u)s.push_back(std::move(content));
            }, MOZART_STR("%(t)s"));
            %(cc)s = %(u)s.data();
            auto %(len)s = %(u)s.size();
        """ % {
            'u': unique_str(),
            't': to_cc(self._type.get_pointee()),
            'oz': self.oz_in_name,
            'cc': self.cc_prefix,
            'len': cc_name_of(self._context),
        })

#-------------------------------------------------------------------------------
# 'ListOut' type

class ListOutStatementsCreator(OutStatementsCreator):
    def __init__(self):
        super().__init__()
        self._cc_array_length_name = unique_str()

    def pre(self, formatter):
        super().pre(formatter)
        formatter.write("""
            int %(u)s = 0;
            auto %(cc)s = &%(u)s;
        """ % {
            'cc': cc_name_of(self._context),
            'u': self._cc_array_length_name
        })

    def post(self, formatter):
        formatter.write("""
            %(oz)s = buildDynamicList(vm, *(%(cc)s), *(%(cc)s) + %(u)s);
        """ % {
            'oz': self.oz_out_prefix,
            'cc': self.cc_name,
            'u': self._cc_array_length_name
        })

#-------------------------------------------------------------------------------
# 'PointerIn' type

class PointerInStatementsCreator(InStatementsCreator):
    def pre(self, formatter):
        formatter.write("""
            std::remove_cv<%(t)s>::type %(u)s;
            unbuild(vm, %(oz)s, %(u)s);
            %(cc)s = &%(u)s;
        """ % {
            't': to_cc(self._type.get_pointee()),
            'u': unique_str(),
            'cc': self.cc_prefix,
            'oz': self.oz_in_name,
        })


