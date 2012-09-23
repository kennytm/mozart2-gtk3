from common import *
from constants import *
from itertools import product
from collections import namedtuple

def is_concrete(struct_decl):
    return struct_decl.is_definition() and name_of(struct_decl) not in OPAQUE_STRUCTS

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

        template <typename T>
        static typename std::enable_if<!std::is_fundamental<T>::value, UnstableNode>::type build(VM vm, T* ptr)
        {
            return build(vm, *ptr);
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
        static typename std::enable_if<std::is_fundamental<T>::value, UnstableNode>::type build(VM vm, T value)
        {
            return ::mozart::build(vm, value);
        }
    """

#-------------------------------------------------------------------------------

def array_field_fixer(field_name, fields, struct_decl):
    if not field_name.startswith('num_'):
        return False

    array_field_name = field_name[4:]
    if array_field_name not in fields:
        return False

    num_field = fields[field_name].field
    (array_field, array_atom_name, _, _) = fields[array_field_name]

    if array_field.type.kind != TypeKind.POINTER:
        return False
    if num_field.type.kind not in INTEGER_KINDS:
        return False

    new_builder = 'buildDynamicList(vm, cc.%(a)s, cc.%(a)s + cc.%(n)s)' % {'a': array_field_name, 'n': field_name}

    del fields[field_name]
    fields[array_field_name] = FieldInfo(array_field, array_atom_name, new_builder, "")

    return True

FIXERS = [array_field_fixer]

#-------------------------------------------------------------------------------

FieldInfo = namedtuple('FieldInfo', ['field', 'atom', 'builder', 'unbuilder'])

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

def fixup_fields(fields, struct_decl):
    modified = True
    while modified:
        modified = False
        for fixer, field_name in product(FIXERS, list(fields)):
            if fixer(field_name, fields, struct_decl):
                modified = True
                break

def struct_builder(struct_decl):
    struct_name = name_of(struct_decl)
    if is_concrete(struct_decl):
        field_names = map(name_of, struct_decl.get_children())
        field_objects = dict(map(create_field_info_pair, struct_decl.get_children()))

        fixup_fields(field_objects, struct_decl)

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

__all__ = ['builder', 'common_unbuild_functions', 'is_concrete']

