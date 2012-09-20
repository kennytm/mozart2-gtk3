from common import *

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
            cc = BoolValue(oz).boolValue(vm);
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
    """

def struct_builder(struct_decl):
    struct_name = struct_decl.spelling.decode('utf-8')

    if struct_decl.is_definition():
        field_names = [field.spelling.decode('utf-8') for field in struct_decl.get_children()]
        field_names_concat = '"), MOZART_STR("'.join(field_names)
        sub_builders_concat = '), build(vm, cc.'.join(field_names)
        extractors_concat = ''.join("""
            unbuild(vm, dottable.dot(vm, Atom::build(vm, MOZART_STR("%(f)s")), cc.%(f)s);
        """ % {'f':f} for f in field_names)

        return """
            static UnstableNode build(VM vm, const %(s)s& cc)
            {
                return buildRecord(vm,
                    buildArity(vm, MOZART_STR("%(ss)s"), MOZART_STR("%(f)s"),
                    build(vm, cc.%(b)s)
                );
            }

            static void unbuild(VM vm, RichNode oz, %(s)s& cc)
            {
                Dottable dottable (oz);
                %(x)s
            }
        """ % {
            's': struct_name,
            'ss': strip_prefix_and_camelize(struct_name),
            'f': field_names_concat,
            'b': sub_builders_concat,
            'x': extractors_concat
        }

    else:
        return """
            static UnstableNode build(VM vm, %(s)s* cc) {
                return D_%(s)s::build(vm, cc);
            }

            static void build(VM vm, RichNode node, %(s)s*& cc) {
                cc = node.as<D_%(s)s>().value();
            }
        """ % {'s': struct_name}

def enum_builder(enum_decl):
    cc_enum_names = [enum.spelling.decode('utf-8') for enum in enum_decl.get_children()]
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
        's': enum_decl.spelling.decode('utf-8'),
        'c': cases,
        'e': entries
    }


