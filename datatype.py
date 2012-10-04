from os.path import join
from writer import Writer
from common import SRC, C_FILES, TYPES_DECL_HH_EXT, TYPES_HH_EXT, C_FILES, C_EXT

class DataTypeDeclWriter(Writer):
    def __init__(self, basename, constants):
        super().__init__(join(SRC, basename + TYPES_DECL_HH_EXT))
        self._header = basename
        self._concrete_opaque_structs = constants.CONCRETE_OPAQUE_STRUCTS

    def write_prolog(self):
        super().write_prolog()
        self.write('#include "../' + C_FILES + '/' + self._header + C_EXT + '"')
        self.write('#include <mozart.hh>')

    def write_epilog(self):
        super().write_epilog()

    def write_datatype(self, struct_name):
        """
        Write a datatype.
        """
        self.write("""
            #ifndef MOZART_GENERATOR
            namespace m2g3 {{
                class D_{0};
            }}

            namespace mozart {{
                using ::m2g3::D_{0};
                #include "D_{0}-implem-decl.hh"
            }}
            #endif

            namespace m2g3 {{
        """.format(struct_name))

        if struct_name in self._concrete_opaque_structs:
            self._write_concrete_opaque_datatype(struct_name)
        else:
            self._write_abstract_datatype(struct_name)

        self.write("""
            }}

            #ifndef MOZART_GENERATOR
            namespace mozart {{
                using ::m2g3::D_{0};
                #include "D_{0}-implem-decl-after.hh"
            }}
            #endif
        """.format(struct_name))

    def _write_abstract_datatype(self, struct_name):
        self.write("""
                class D_{0} : public ::mozart::DataType<D_{0}>, public ::mozart::StoredAs<{0}*> {{
                public:
                    typedef ::mozart::SelfType<D_{0}>::Self Self;

                    D_{0}({0}* value) : _value(value) {{ }}

                    static void create({0}*& self, ::mozart::VM vm, {0}* value) {{ self = value; }}
                    static inline void create({0}*& self, ::mozart::VM vm, ::mozart::GR gr, Self from);

                    {0}* value() const {{ return _value; }}

                    inline void printReprToStream(Self self, ::mozart::VM vm, std::ostream& out, int depth);

                private:
                    {0}* _value;
                }};

        """.format(struct_name))

    def _write_concrete_opaque_datatype(self, struct_name):
        self.write("""
                class D_{0} : public ::mozart::DataType<D_{0}> {{
                public:
                    typedef ::mozart::SelfType<D_{0}>::Self Self;

                    D_{0}(::mozart::VM vm, const {0}& value) : _value(value) {{ }}
                    D_{0}(::mozart::VM vm, ::mozart::GR gr, Self from) : _value(from->_value) {{ }}
                    const {0}& value() const {{ return _value; }}

                private:
                    {0} _value;
                }};

        """.format(struct_name))



class DataTypeWriter(Writer):
    def __init__(self, basename, constants):
        super().__init__(join(SRC, basename + TYPES_HH_EXT))
        self._basename = basename
        self._concrete_opaque_structs = constants.CONCRETE_OPAQUE_STRUCTS

    def write_prolog(self):
        super().write_prolog()
        self.write('#include "' + self._basename + TYPES_DECL_HH_EXT + '"')

    def write_epilog(self):
        super().write_epilog()

    def write_datatype(self, struct_name):
        """
        Write a datatype.
        """
        self.write("""
            namespace mozart {{
                using ::m2g3::D_{0};
                #include "D_{0}-implem.hh"
            }}
        """.format(struct_name))

        if struct_name not in self._concrete_opaque_structs:
            self.write("""
                namespace m2g3 {{
                    void D_{0}::create({0}*& self, ::mozart::VM vm, ::mozart::GR gr, Self from) {{
                        self = from.get().value();
                    }}

                    void D_{0}::printReprToStream(Self self, ::mozart::VM vm, std::ostream& out, int depth) {{
                        out << "<D_{0}: " << value() << ">";
                    }}
                }}
            """.format(struct_name))

