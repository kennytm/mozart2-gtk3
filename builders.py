from os.path import join
from itertools import product
from collections import OrderedDict
from clang.cindex import CursorKind
from common import *
from fixers import FieldInfo, fixup_fields
from fake_type import PointerOf
from to_cc import to_cc
from writer import Writer

#-------------------------------------------------------------------------------

def _create_field_info_pair(field):
    field_name = name_of(field)
    atom = 'MOZART_STR("' + camelize(field_name) + '")'
    builder = 'build(vm, cc.' + field_name + ')'
    unbuilder = """
        {{
            auto label = Atom::build(vm, {0});
            auto field = Dottable(oz).dot(vm, label);
            unbuild(vm, field, cc.{1});
        }}
    """.format(atom, field_name)

    return (field_name, FieldInfo(field, atom, builder, unbuilder))


class BuildersWriter(Writer):
    def __init__(self, basename, constants):
        super().__init__(join(SRC, basename + BUILDERS_HH_EXT))
        self._basename = basename
        self._special_types = constants.SPECIAL_TYPES

    def write_prolog(self):
        super().write_prolog()

        self.write('''
            #include <type_traits>
            #include <unordered_map>
            #include <mozart.hh>
            #include "''' + self._basename + TYPES_DECL_HH_EXT + '''"

            namespace m2g3 {
                using namespace mozart;

                template <typename T>
                static inline constexpr bool is_integral_not_bool() {
                    return std::is_integral<T>::value && !std::is_same<typename std::decay<T>::type, bool>::value;
                }

                class WrappedNode {
                    VM _vm;
                    ProtectedNode _node;

                    WrappedNode(VM vm, RichNode node) : _vm(vm), _node(ozProtect(vm, node)) {}
                    ~WrappedNode() { ozUnprotect(_vm, _node); }

                public:
                    static void* create(VM vm, RichNode node) {
                        return new WrappedNode(vm, node);
                    }

                    static void destroy(void* data) {
                        delete static_cast<WrappedNode*>(data);
                    }

                    static UnstableNode get(VM vm, void* data) {
                        if (data != nullptr) {
                            auto node = static_cast<WrappedNode*>(data);
                            return UnstableNode(node->_vm, *node->_node);
                        } else {
                            return ::mozart::build(vm, ::mozart::unit);
                        }
                    }
                };

                template <typename T>
                static auto unbuild(VM vm, RichNode oz, T& cc)
                    -> typename std::enable_if<is_integral_not_bool<T>()>::type
                {
                    cc = static_cast<T>(IntegerValue(oz).intValue(vm));
                }

                template <typename T>
                static auto unbuild(VM vm, RichNode oz, T& cc)
                    -> typename std::enable_if<std::is_floating_point<T>::value>::type
                {
                    cc = static_cast<T>(FloatValue(oz).floatValue(vm));
                }

                static void unbuild(VM vm, RichNode oz, bool& cc) {
                    cc = BooleanValue(oz).boolValue(vm);
                }

                static void unbuild(VM vm, RichNode oz, const char*& cc) {
                    std::basic_stringstream<nchar> buffer;
                    VirtualString(oz).toString(vm, buffer);
                    auto str = buffer.str();
                    auto utf = toUTF<char>(makeLString(str.c_str(), str.length()));
                    auto lstring = newLString(vm, utf);
                    cc = lstring.string;
                }

                template <typename It>
                static UnstableNode buildDynamicList(VM vm, It begin, It end);

                template <typename T>
                static auto build(VM vm, T value)
                    -> typename std::enable_if<(is_integral_not_bool<T>() && std::is_signed<T>::value && sizeof(T) <= sizeof(nativeint)), UnstableNode>::type
                {
                    nativeint extended = value;
                    return ::mozart::build(vm, extended);
                }

                template <typename T>
                static auto build(VM vm, T value)
                    -> typename std::enable_if<(is_integral_not_bool<T>() && std::is_unsigned<T>::value && sizeof(T) <= sizeof(size_t)), UnstableNode>::type
                {
                    size_t extended = value;
                    return ::mozart::build(vm, extended);
                }
        ''')

    def write_epilog(self):
        self.write('''
                template <typename T>
                static auto build(VM vm, T* ptr)
                    -> typename std::enable_if<!std::is_fundamental<T>::value, UnstableNode>::type
                {
                    return build(vm, *ptr);
                }

                template <typename It>
                static UnstableNode buildDynamicList(VM vm, It begin, It end) {
                    OzListBuilder listBuilder (vm);
                    while (begin != end) {
                        listBuilder.push_back(vm, build(vm, *begin++));
                    }
                    return listBuilder.get(vm);
                }
            }
        ''')
        super().write_epilog()

    def write_type(self, type_node):
        """
        Write the builder and unbuilder representing the clang Node.
        """
        type_name = name_of(type_node)
        try:
            (builder_string, unbuilder_string) = self._special_types[type_name]

        except KeyError:
            if type_node.kind == CursorKind.STRUCT_DECL:
                if is_concrete(type_node):
                    self._write_concrete_struct(type_node)
                else:
                    self._write_abstract_struct(type_node)
            elif type_node.kind == CursorKind.ENUM_DECL:
                self._write_enum(type_node)

        else:
            if builder_string:
                self.write("""
                    static UnstableNode build(VM vm, const {0}& cc) {{
                        {1}
                    }}
                """.format(type_name, builder_string))
            if unbuilder_string:
                self.write("""
                    static void unbuild(VM vm, RichNode oz, {0}& cc) {{
                        {1}
                    }}
                """.format(type_name, unbuilder_string))

    def _write_concrete_struct(self, struct_decl):
        struct_name = name_of(struct_decl)
        field_names = map(name_of, struct_decl.get_children())
        field_objects = dict(map(_create_field_info_pair, struct_decl.get_children()))

        fixup_fields(field_objects)

        (_, atoms, builders, unbuilders) = zip(*field_objects.values())

        self.write("""
            static UnstableNode build(VM vm, const {s}& cc) {{
                return buildRecord(vm,
                    buildArity(vm, MOZART_STR("{ss}"), {f}),
                    {b}
                );
            }}
            static void unbuild(VM vm, RichNode oz, {s}& cc) {{
                {x}
            }}

        """.format(
            s=struct_name,
            ss=strip_prefix_and_camelize(struct_name),
            f=', '.join(atoms),
            b=', '.join(builders),
            x=''.join(unbuilders)
        ))

    def _write_abstract_struct(self, struct_decl):
        self.write("""
            static UnstableNode build(VM vm, {0}* cc) {{
                return D_{0}::build(vm, cc);
            }}
            static void unbuild(VM vm, RichNode node, {0}*& cc) {{
                cc = node.as<D_{0}>().value();
            }}
            static void unbuild(VM vm, RichNode node, const {0}*& cc) {{
                cc = node.as<D_{0}>().value();
            }}

        """.format(name_of(struct_decl)))

    def _write_enum(self, enum_decl):
        enum_name = name_of(enum_decl)
        cc_enum_names = [name_of(enum) for enum in enum_decl.get_children()]
        atom_names = list(strip_common_prefix_and_camelize(cc_enum_names))

        # {{

        self.write("""
            static UnstableNode build(VM vm, """ + enum_name + """ cc) {
                switch (cc) {
                    default: return SmallInt::build(vm, cc);
        """)

        for t in zip(cc_enum_names, atom_names):
            self.write('case {0}: return Atom::build(vm, MOZART_STR("{1}"));'.format(*t))

        self.write("""
                }}
            }}

            static void unbuild(VM vm, RichNode oz, {0}& cc) {{
                static const std::unordered_map<std::basic_string<nchar>, {0}> map = {{
        """.format(enum_name))

        for t in zip(atom_names, cc_enum_names):
            self.write('{{MOZART_STR("{0}"), {1}}},'.format(*t))

        self.write("""
                };

                auto str = vsToString<nchar>(vm, oz);
                auto it = map.find(str);
                if (it != map.end()) {
                    cc = it->second;
                } else {
                    cc = static_cast<""" + enum_name +""">(IntegerValue(oz).intValue(vm));
                }
            }

        """)

        # }}

