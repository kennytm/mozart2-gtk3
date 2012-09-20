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
        return ["%s; %s = &%s;" % (cc_decl, self._cc_prefix, cc_complete_name)]

    def post(self):
        return []

#-------------------------------------------------------------------------------
# "Out" type.

class OutStatementsCreator(StatementsCreator):
    @property
    def oz_inout(self):
        return 'Out'

    def pre(self):
        return super().pre()

    def post(self):
        type_kind = self._type.kind
        if is_primitive_type(self._type):
            return self._decode_primitive_type()
        elif is_c_string(self._type):
            return self._decode_c_string()
        elif type_kind == TypeKind.RECORD:
            return self._decode_record()
        elif type_kind == TypeKind.POINTER:
            return self._decode_pointer()
        elif type_kind == TypeKind.ENUM:
            return self._decode_enum()
        elif type_kind == TypeKind.TYPEDEF:
            return self._decode_canonical()
        else:
            raise NotImplementedError('Not implemented to convert %s to %s' %
                                      (to_cc(self._type, self._cc_name), self._oz_name))

    def _decode_primitive_type(self):
        return [self._oz_prefix + " = build(vm, " + self._cc_name + ");"]

    def _decode_c_string(self):
        return [self._oz_prefix +
                " = String::build(vm, newLString(vm, toUTF<nchar>(makeLString(" +
                self._cc_name + ");"]

    def _decode_record(self):
        struct_decl = self._type.get_declaration()
        if struct_decl.is_definition():
            return self._decode_struct(struct_decl)
        else:
            struct_name = struct_decl.spelling.decode('utf-8')
            return ["%s = D_%s::build(vm, &%s);" % (self._oz_prefix, struct_name, self._cc_name)]

    def _decode_struct(self, struct_decl):
        cc_statements = []
        oz_temp_names = []
        field_names = []

        creator = self.__copy__()
        creator._with_declaration = True

        for decl in struct_decl.get_children():
            subtype = decl.type
            field_name = decl.spelling.decode('utf-8')
            field_names.append(field_name)
            oz_temp_name = unique_str()
            oz_temp_names.append(oz_temp_name)

            creator._type = subtype
            creator.cc_name = self._cc_name + "." + field_name
            creator.oz_name = oz_temp_name
            cc_statements.extend(creator.post())

        field_names_concat = '"), MOZART_STR("'.join(field_names)
        oz_temp_names_concat = '), std::move('.join(oz_temp_names)

        struct_name = struct_decl.spelling.decode('utf-8')
        oz_record_name = strip_prefix_and_camelize(struct_name)

        cc_statements.append("""
            %s = buildRecord(vm,
                buildArity(vm, MOZART_STR("%s"), MOZART_STR("%s")),
                std::move(%s)
            );
        """ % (self._oz_prefix, oz_record_name, field_names_concat, oz_temp_names_concat))

        return cc_statements

    def _decode_enum(self):
        enum_decl = self._type.get_declaration()
        cc_enum_names = [enum.spelling.decode('utf-8') for enum in enum_decl.get_children()]
        atom_names = strip_common_prefix_and_camelize(cc_enum_names)

        cc_atom_name = unique_str();
        cc_atom_length_name = unique_str();

        cc_statements = ["""
             const nchar* %s;
             size_t %s;
             switch (%s)
             {
        """ % (cc_atom_name, cc_atom_length_name, self._cc_name)]

        for cc_enum_name, atom_name in zip(cc_enum_names, atom_names):
            cc_statements.append("""
                case %s:
                    %s = MOZART_STR("%s");
                    %s = %s;
                    break;
            """ % (cc_enum_name, cc_atom_name, atom_name, cc_atom_length_name, len(atom_name)))

        cc_statements.append("""
                default:
                    %(a)s = nullptr;
                    break;
            }

            %(oz)s = (%(a)s != nullptr) ?
                        Atom::build(vm, %(a)s, %(l)s) :
                        SmallInt::build(vm, %(cc)s);
        """ % {'a':cc_atom_name, 'l':cc_atom_length_name, 'oz':self._oz_prefix, 'cc':self._cc_name})

        return cc_statements

    def _decode_pointer(self):
        creator = self.__copy__()
        creator._type = self._type.get_pointee()
        creator.cc_name = '(*(' + self._cc_name + '))'
        return creator.post()

    def _decode_canonical(self):
        creator = self.__copy__()
        creator._type = self._type.get_canonical()
        return creator.post()

#-------------------------------------------------------------------------------
# "In" type.

class InStatementsCreator(StatementsCreator):
    @property
    def oz_inout(self):
        return 'In'

    def post(self):
        return super().post()

    def pre(self):
        type_kind = self._type.kind
        if is_primitive_type(self._type):
            return self._encode_primitive_type()
        elif is_c_string(self._type):
            return self._encode_c_string()
        elif type_kind == TypeKind.RECORD:
            return self._encode_record()
        elif type_kind == TypeKind.POINTER:
            return self._encode_pointer()
        elif type_kind == TypeKind.ENUM:
            return self._encode_enum()
        elif type_kind == TypeKind.TYPEDEF:
            return self._encode_canonical()
        else:
            raise NotImplementedError('Not implemented to convert %s to %s' %
                                      (self._oz_name, to_cc(self._type, self._cc_name)))

    def _encode_primitive_type(self):
        kind = self._type.kind
        if kind == TypeKind.BOOL:
            interface = "BoolValue"
            method = "boolValue"
        elif kind in INTEGER_KINDS:
            interface = "IntegerValue"
            method = "intValue"
        elif kind in FLOAT_KINDS:
            interface = "FloatValue"
            method = "floatValue"
        return ['%s = %s(%s).%s(vm);' % (self._cc_prefix, interface, self._oz_name, method)]

    def _encode_c_string(self):
        return ["""
            auto %(u)s = vsToString<char>(vm, %(oz)s);
            %(cc)s = %(u)s.c_str();
        """ % {'cc': self._cc_prefix, 'oz': self._oz_name, 'u': unique_str()}]

    def _encode_record(self):
        temp_interface_name = unique_str()
        struct_decl = self._type.get_declaration()
        struct_name = struct_decl.spelling.decode('utf-8')

        cc_statements = ["Dottable %s(%s);" % (temp_interface_name, self._oz_name)]
        if self._with_declaration:
            cc_statements.append(struct_name + ' ' + self._cc_name + ';')

        creator = self.__copy__()
        creator._with_declaration = False

        for decl in struct_decl.get_children():
            subtype = decl.type
            field_name = decl.spelling.decode('utf-8')
            oz_temp_field_name = unique_str()
            cc_statements.append("""
                auto %s = %s.dot(vm, build(vm, MOZART_STR("%s")));
            """ % (oz_temp_field_name, temp_interface_name, field_name))

            creator._type = subtype
            creator.oz_name = oz_temp_field_name
            creator.cc_name = self._cc_name + '.' + field_name
            cc_statements.extend(creator.pre())

        return cc_statements

    def _encode_pointer(self):
        pointee = self._type.get_pointee().get_canonical()
        kind = pointee.kind
        if kind == TypeKind.RECORD:
            struct = pointee.get_declaration()
            if not struct.is_definition():
                struct_name = struct.spelling.decode('utf-8')
                return ["""
                    %s = %s.as<D_%s>().value();
                """ % (self._cc_prefix, self._oz_name, struct_name)]

        cc_complete_name = unique_str()

        creator = self.__copy__()
        creator._type = pointee
        creator._cc_name = cc_complete_name
        creator.with_declaration = True

        cc_statements = creator.pre()
        cc_statements.append(self._cc_prefix + ' = &' + cc_complete_name + ';')
        return cc_statements

    def _encode_enum(self):
        enum_decl = self._type.get_declaration()
        enum_name = enum_decl.spelling.decode('utf-8')
        cc_enum_names = [enum.spelling.decode('utf-8') for enum in enum_decl.get_children()]
        atom_names = strip_common_prefix_and_camelize(cc_enum_names)

        cc_string_name = unique_str()
        cc_map_name = unique_str()

        cc_atom_name = unique_str()
        cc_atom_length_name = unique_str()

        cc_statements = ["""
            auto %s = vsToString(%s);
            static const std::unordered_map<std::basic_string<nchar>, %s> %s = {
        """ % (cc_atom_name, self._oz_name, enum_name, cc_map_name)]

        cc_statements.extend('{MOZART_STR("' + atom_name + '"), ' + cc_enum_name + '},'
                             for cc_enum_name, atom_name in zip(cc_enum_names, atom_names))

        cc_statements.append("""
            };

            auto %(i)s = %(m)s.find(%(a)s);
            %(cc)s = (%(i)s != %(m)s.end()) ?
                        %(i)s->second :
                        (%(e)s) IntegerValue(%(oz)s).intValue(vm);
        """ % {
            'i': unique_str(),
            'm': cc_map_name,
            'a': cc_atom_name,
            'cc': self._cc_prefix,
            'e': enum_name,
            'oz': self._oz_name,
        })

        return cc_statements

    def _encode_canonical(self):
        creator = self.__copy__()
        creator._type = self._type.get_canonical()
        return creator.pre()

#-------------------------------------------------------------------------------
# 'NodeOut' type

class NodeOutStatementsCreator(StatementsCreator):
    @property
    def oz_inout(self):
        return 'Out'

    def post(self):
        return ["""
            auto %(u)s = static_cast<std::pair<ProtectedNode, VM>*>(*(%(cc)s));
            %(oz)s = UnstableNode(vm, *%(u)s->first);
        """ % {'oz':self._oz_prefix, 'cc':self._cc_name, 'u':unique_str()}]

#-------------------------------------------------------------------------------
# 'NodeIn' type

class NodeInStatementsCreator(InStatementsCreator):
    @property
    def oz_inout(self):
        return 'In'

    def pre(self):
        return ["""
            %s = new std::pair<ProtectedNode, VM>(ozProtect(vm, %s), vm);
        """ % (self._cc_prefix, self._oz_name)]

#-------------------------------------------------------------------------------
# 'NodeDeleter' type

class NodeDeleterStatementsCreator(InStatementsCreator):
    def pre(self):
        lambda_args = ', '.join(to_cc(subtype, name='x_lambda_'+str(i))
                                for i, subtype in enumerate(self._type.get_pointee().argument_types()))
        return ["""
            %(p)s = [](%(l)s) {
                auto %(u)s = static_cast<std::pair<ProtectedNode, VM>*>(x_lambda_%(n)s);
                ozUnprotect(%(u)s->second, %(u)s->first);
                delete %(u)s;
            };
        """ % {'p':self._cc_prefix, 'l':lambda_args, 'u':unique_str(), 'n':self._context}]

#-------------------------------------------------------------------------------

def get_statement_creators(func_cursor, c_func_name):
    inouts = SPECIAL_INOUTS.get(c_func_name, {})
    globals_dict = globals()

    def decode_inout(arg_name, default, real_arg_name, typ):
        inout_tuple = inouts.get(arg_name, (default, None))
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

        arg_name = arg.spelling.decode('utf-8')
        yield decode_inout(arg_name, 'In', arg_name, arg.type.get_canonical())


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

    for creator in creators:
        creator.with_declaration = True
        cc_statements.extend(creator.pre())

    call_args = (creator.cc_name for creator in creators
                                 if creator.oz_name != '_x_oz_return')
    call_statement = c_func_name + '(' + ', '.join(call_args) + ');'
    if func_cursor.result_type.get_canonical().kind != TypeKind.VOID:
        call_statement = '*_x_cc__x_oz_return = ' + call_statement
    cc_statements.append(call_statement)

    for creator in creators:
        creator.with_declaration = False
        cc_statements.extend(creator.post())

    arg_proto = ''.join(', ' + creator.oz_inout + ' ' + creator.oz_name
                        for creator in creators
                        if creator.oz_inout is not None and creator.oz_name != 'return')

    return (arg_proto, cc_statements)

__all__ = ['get_cc_function_definition']

