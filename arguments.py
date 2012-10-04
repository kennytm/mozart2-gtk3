from common import cc_name_of, oz_in_name_of, oz_out_name_of, unique_str
from fake_type import IntType
from to_cc import to_cc

class _Argument:
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
        assert issubclass(new_type, _Argument)
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

class Out(_Argument):
    @staticmethod
    def get_oz_inout():
        return 'Out'

    def post(self, formatter):
        formatter.write(self.oz_out_prefix + ' = build(vm, *' + self.cc_name + ');')

#-------------------------------------------------------------------------------

class In(_Argument):
    @staticmethod
    def get_oz_inout():
        return 'In'

    def pre(self, formatter):
        if self._with_declaration:
            formatter.write(to_cc(self._type, self.cc_name) + ';')
        formatter.write('unbuild(vm, ' + self.oz_in_name + ', ' + self.cc_name + ');')

#-------------------------------------------------------------------------------

class InOut(Out):
    @staticmethod
    def get_oz_inout():
        return 'InOut'

    def pre(self, formatter):
        in_creator = In()
        in_creator._type = self._type.get_pointee()
        in_creator._name = unique_str()
        in_creator._with_declaration = True
        in_creator._context = self._context

        formatter.write('auto &' + in_creator.oz_in_name + ' = ' + self.oz_in_name + ';')
        in_creator.pre(formatter)
        formatter.write(self.cc_prefix + ' = &' + in_creator.cc_name + ';')

#-------------------------------------------------------------------------------

class NodeOut(Out):
    def post(self, formatter):
        formatter.write(self.oz_out_prefix + ' = WrappedNode::get(vm, *(' + self.cc_name + '));')

#-------------------------------------------------------------------------------

class NodeIn(In):
    def pre(self, formatter):
        formatter.write(self.cc_prefix + ' = WrappedNode::create(vm, ' + self.oz_in_name + ');')

#-------------------------------------------------------------------------------

class NodeDeleter(_Argument):
    def pre(self, formatter):
        args = self._type.get_canonical().get_pointee().argument_types()
        lambda_args = ', '.join(to_cc(subtype, name='x_lambda_'+str(i))
                                for i, subtype in enumerate(args))
        formatter.write("""
            {0} = []({1}) {{ WrappedNode::destroy(x_lambda_{2}); }};
        """.format(self.cc_prefix, lambda_args, self._context))

#-------------------------------------------------------------------------------

class AddressIn(In):
    def pre(self, formatter):
        formatter.write("""
            {0} = reinterpret_cast<{1}>(IntegerValue({2}).intValue(vm));
        """.format(self.cc_prefix, to_cc(self._type), self.oz_in_name))

#-------------------------------------------------------------------------------

class Skip(_Argument):
    def pre(self, formatter):
        pass

#-------------------------------------------------------------------------------

class Constant(_Argument):
    def pre(self, formatter):
        formatter.write(self.cc_prefix + ' = ' + self._context + ';')

#-------------------------------------------------------------------------------

class ListIn(In):
    def pre(self, formatter):
        formatter.write("""
            std::vector<std::remove_cv<{t}>::type> {u};
            ozListForEach(vm, {oz}, [vm, &{u}](UnstableNode& node) {{
                std::remove_cv<{t}>::type content;
                unbuild(vm, node, content);
                {u}.push_back(std::move(content));
            }}, MOZART_STR("{t}"));
            {cc} = {u}.data();
            auto {l} = {u}.size();
        """.format(
            u=unique_str(), t=to_cc(self._type.get_pointee()),
            oz=self.oz_in_name, cc=self.cc_prefix, l=cc_name_of(self._context)
        ))

#-------------------------------------------------------------------------------

class ListOut(Out):
    def __init__(self):
        super().__init__()
        self._cc_array_length_name = unique_str()

    def pre(self, formatter):
        super().pre(formatter)
        formatter.write("""
            int {u} = 0;
            auto {cc} = &{u};
        """.format(cc=cc_name_of(self._context), u=self._cc_array_length_name))

    def post(self, formatter):
        formatter.write("""
            {oz} = buildDynamicList(vm, *({cc}), *({cc}) + {u});
        """.format(oz=self.oz_out_prefix, cc=self.cc_name, u=self._cc_array_length_name))

#-------------------------------------------------------------------------------

class PointerIn(In):
    def pre(self, formatter):
        formatter.write("""
            std::remove_cv<{t}>::type {u};
            unbuild(vm, {oz}, {u});
            {cc} = &{u};
        """.format(
            t=to_cc(self._type.get_pointee()), u=unique_str(),
            oz=self.oz_in_name, cc=self.cc_prefix
        ))

#-------------------------------------------------------------------------------

class BooleanIn(In):
    def pre(self, formatter):
        formatter.write(self.cc_prefix + ' = BooleanValue(' + self.oz_in_name + ').boolValue(vm);')

class BooleanOut(Out):
    def post(self, formatter):
        formatter.write(self.oz_out_prefix + ' = Boolean::build(vm, ' + self.cc_name + ');')

#-------------------------------------------------------------------------------

class StringIn(In):
    def pre(self, formatter):
        if self._with_declaration:
            formatter.write(to_cc(self._type, self.cc_name) + ';')
        formatter.write('unbuildString(vm, ' + self.oz_in_name + ', ' + self.cc_name + ');')

class StringOut(Out):
    def post(self, formatter):
        formatter.write(self.oz_out_prefix + ' = buildString(vm, ' + self.cc_name + ');')


