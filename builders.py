from common import *
from constants import *
from fixers import *
from itertools import product
from collections import OrderedDict
from fake_type import PointerOf
from to_cc import to_cc
import creators

#-------------------------------------------------------------------------------

def common_unbuild_functions():
    for int_type in ['char', 'signed char', 'unsigned char', 'short',
                     'unsigned short', 'int', 'unsigned', 'long',
                     'unsigned long', 'long long', 'unsigned long long']:
        yield """
            static void unbuild(VM vm, RichNode oz, %(s)s& cc)
            {
                cc = static_cast<%(s)s>(IntegerValue(oz).intValue(vm));
            }
        """ % {'s': int_type}

    for float_type in ['float', 'double', 'long double']:
        yield """
            static void unbuild(VM vm, RichNode oz, %(s)s& cc)
            {
                cc = static_cast<%(s)s>(FloatValue(oz).floatValue(vm));
            }
        """ % {'s': float_type}

    yield """
        static void unbuild(VM vm, RichNode oz, bool& cc)
        {
            cc = BooleanValue(oz).boolValue(vm);
        }

        static void unbuild(VM vm, RichNode oz, const char*& cc)
        {
            std::basic_stringstream<nchar> buffer;
            VirtualString(oz).toString(vm, buffer);
            auto str = buffer.str();
            auto utf = toUTF<char>(makeLString(str.c_str(), str.length()));
            auto lstring = newLString(vm, utf);
            cc = lstring.string;
        }

        template <typename It>
        static UnstableNode buildDynamicList(VM vm, It begin, It end)
        {
            OzListBuilder listBuilder (vm);
            while (begin != end)
                listBuilder.push_back(vm, *begin++);
            return listBuilder.get(vm);
        }

        template <typename T>
        static auto build(VM vm, T value)
            -> typename std::enable_if<(std::is_integral<T>::value && std::is_signed<T>::value &&
                                        sizeof(T) <= sizeof(nativeint)), UnstableNode>::type
        {
            nativeint extended = value;
            return ::mozart::build(vm, extended);
        }

        template <typename T>
        static auto build(VM vm, T value)
            -> typename std::enable_if<(std::is_integral<T>::value && std::is_unsigned<T>::value &&
                                        sizeof(T) <= sizeof(size_t)), UnstableNode>::type
        {
            size_t extended = value;
            return ::mozart::build(vm, extended);
        }

        template <typename T>
        static typename std::enable_if<!std::is_fundamental<T>::value, UnstableNode>::type build(VM vm, T* ptr)
        {
            return build(vm, *ptr);
        }

        static void* wrapNode(VM vm, RichNode node)
        {
            return new std::pair<ProtectedNode, VM>(ozProtect(vm, node), vm);
        }

        static UnstableNode unwrapNode(void* data)
        {
            auto pair = static_cast<std::pair<ProtectedNode, VM>*>(data);
            if (pair != nullptr)
                return UnstableNode(pair->second, *pair->first);
            else
                return build(pair->second, unit);
        }

        static void deleteWrappedNode(void* data)
        {
            if (data == nullptr)
                return;
            auto pair = static_cast<std::pair<ProtectedNode, VM>*>(data);
            ozUnprotect(pair->second, pair->first);
            delete pair;
        }
    """

#-------------------------------------------------------------------------------

def create_field_info_pair(field):
    field_name = name_of(field)
    atom = 'MOZART_STR("' + camelize(field_name) + '")'
    builder = 'build(vm, cc.' + field_name + ')'
    unbuilder = """
    {
        auto label = Atom::build(vm, %s);
        auto field = Dottable(oz).dot(vm, label);
        unbuild(vm, field, cc.%s);
    }
    """ % (atom, field_name)

    return (field_name, FieldInfo(field, atom, builder, unbuilder))

def struct_builder(struct_decl):
    struct_name = name_of(struct_decl)
    if is_concrete(struct_decl):
        field_names = map(name_of, struct_decl.get_children())
        field_objects = dict(map(create_field_info_pair, struct_decl.get_children()))

        fixup_fields(field_objects)

        (_, atoms, builders, unbuilders) = zip(*field_objects.values())

        return """
            static UnstableNode build(VM vm, const %(s)s& cc)
            {
                return buildRecord(vm,
                    buildArity(vm, MOZART_STR("%(ss)s"), %(f)s),
                    %(b)s
                );
            }

            static void unbuild(VM vm, RichNode oz, %(s)s& cc)
            {
                %(x)s
            }
        """ % {
            'ss': strip_prefix_and_camelize(struct_name),
            's': struct_name,
            'f': ', '.join(atoms),
            'b': ', '.join(builders),
            'x': '\n'.join(unbuilders)
        }

    else:
        return """
            static UnstableNode build(VM vm, %(s)s* cc) {
                return D_%(s)s::build(vm, cc);
            }

            static void unbuild(VM vm, RichNode node, %(s)s*& cc) {
                cc = node.as<D_%(s)s>().value();
            }

            static void unbuild(VM vm, RichNode node, const %(s)s*& cc) {
                cc = node.as<D_%(s)s>().value();
            }
        """ % {'s': struct_name}

#-------------------------------------------------------------------------------

def enum_builder(enum_decl):
    cc_enum_names = [name_of(enum) for enum in enum_decl.get_children()]
    atom_names = strip_common_prefix_and_camelize(cc_enum_names)

    cases = ''.join('case %s: return Atom::build(vm, MOZART_STR("%s"));\n' % t
                    for t in zip(cc_enum_names, atom_names))
    entries = ''.join('{MOZART_STR("%s"), %s},\n' % t
                      for t in zip(atom_names, cc_enum_names))

    return """
        static UnstableNode build(VM vm, %(s)s cc)
        {
            switch (cc)
            {
                %(c)s
                default: return SmallInt::build(vm, cc);
            }
        }

        static void unbuild(VM vm, RichNode oz, %(s)s& cc)
        {
            static const std::unordered_map<std::basic_string<nchar>, %(s)s> map = {
                %(e)s
            };

            auto str = vsToString<nchar>(vm, oz);
            auto it = map.find(str);
            if (it != map.end())
            {
                cc = it->second;
            }
            else
            {
                cc = static_cast<%(s)s>(IntegerValue(oz).intValue(vm));
            }
        }
    """ % {
        's': name_of(enum_decl),
        'c': cases,
        'e': entries
    }

#-------------------------------------------------------------------------------

def builder(type_node):
    type_name = name_of(type_node)
    try:
        (build, unbuild) = SPECIAL_TYPES[type_name]

    except KeyError:
        if type_node.kind == CursorKind.STRUCT_DECL:
            return struct_builder(type_node)
        elif type_node.kind == CursorKind.ENUM_DECL:
            return enum_builder(type_node)

    else:
        res = []
        if build:
            res.append("static UnstableNode build(VM vm, const %s& cc) { %s }" % (type_name, build))
        if unbuild:
            res.append("static void unbuild(VM vm, RichNode oz, %s& cc) { %s }" % (type_name, unbuild))
        return "\n".join(res)

#-------------------------------------------------------------------------------

def get_statement_creators(func_cursor, c_func_name):
    for regex, special_inouts in SPECIAL_INOUTS:
        if regex.match(c_func_name):
            inouts = special_inouts
            break
    else:
        inouts = {}

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

        creator = getattr(creators, inout + 'StatementsCreator')()
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

    try:
        return SPECIAL_FUNCTIONS[c_func_name]
    except KeyError:
        pass

    pre_fixup_creators = get_statement_creators(func_cursor, c_func_name)
    pre_fixup_creators_dict = OrderedDict((c._name, c) for c in pre_fixup_creators)
    fixup_args(pre_fixup_creators_dict)
    creators = list(pre_fixup_creators_dict.values())

    cc_statements = []

    try:
        cc_statements.append(FUNCTION_PRE_SETUP[c_func_name])
    except KeyError:
        pass

    for creator in creators:
        creator._with_declaration = True
        cc_statements.append(creator.pre())

    try:
        cc_statements.append(FUNCTION_POST_SETUP[c_func_name])
    except KeyError:
        pass

    call_args = (creator.cc_name for creator in creators if creator._name != 'return')
    call_statement = c_func_name + '(' + ', '.join(call_args) + ');'
    if func_cursor.result_type.get_canonical().kind != TypeKind.VOID:
        call_statement = '*' + CC_NAME_OF_RETURN + ' = ' + call_statement
    cc_statements.append(call_statement)

    for creator in creators:
        creator._with_declaration = False
        cc_statements.append(creator.post())

    try:
        cc_statements.append(FUNCTION_PRE_TEARDOWN[c_func_name])
    except KeyError:
        pass

    arg_proto = []
    for creator in creators:
        inout = creator.get_oz_inout()
        if inout in {'In', 'InOut'}:
            arg_proto.append(', In ' + creator.oz_in_name)
        if inout in {'Out', 'InOut'}:
            arg_proto.append(', Out ' + creator.oz_out_name)

    try:
        cc_statements.append(FUNCTION_POST_TEARDOWN[c_func_name])
    except KeyError:
        pass

    return (''.join(arg_proto), cc_statements)

__all__ = ['builder', 'common_unbuild_functions', 'is_concrete',
           'get_cc_function_definition', 'FieldInfo']

