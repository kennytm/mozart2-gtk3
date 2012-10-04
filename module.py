from os.path import join
from contextlib import contextmanager
from writer import Writer
from common import *


class ModuleHeaderWriter(Writer):
    def __init__(self, basename):
        super().__init__(join(SRC, basename + HH_EXT))
        self._basename = basename

    def write_prolog(self):
        super().write_prolog()
        self.write("""
            #include <mozart.hh>

            namespace m2g3 {{
                using namespace ::mozart;
                using namespace ::mozart::builtins;

                #ifndef MOZART_BUILTIN_GENERATOR
                #include "{bn}{out}/{bn}{bihh}"
                #endif
        """.format(bn=self._basename, out=OUT_EXT, bihh=BUILTINS_HH_EXT))

    def write_epilog(self):
        self.write("}") # }
        super().write_epilog()

    @contextmanager
    def write_module(self, modname):
        self.write("""
                struct M_{0} : Module {{
                    M_{0}() : Module("{0}") {{ }}
        """.format(modname))
        yield
        self.write("};")    # }

    def write_function(self, ozfunc):
        self.write("""
                    struct P_{0} : Builtin<P_{0}> {{
                        P_{0}() : Builtin("{0}") {{ }}
                        void operator()(VM vm{1});
                    }};
        """.format(ozfunc.oz_function_name, ozfunc.get_arg_proto()))


class ModuleWriter(Writer):
    def __init__(self, basename):
        super().__init__(join(SRC, basename + CC_EXT))
        self._basename = basename

    def write_prolog(self):
        self.write("""
            #include "{bn}{hh}"
            #include "{bn}{bd}"
            #include "{bn}{ty}"

            namespace m2g3 {{
                using namespace ::mozart;
                using namespace ::mozart::builtins;
        """.format(bn=self._basename, hh=HH_EXT, bd=BUILDERS_HH_EXT, ty=TYPES_HH_EXT))

    def write_epilog(self):
        self.write("""
                #include "{bn}{out}/{bn}{bicc}"
            }}
        """.format(bn=self._basename, out=OUT_EXT, bicc=BUILTINS_CC_EXT))

    def write_function(self, modname, ozfunc):
        self.write("""
                void M_{0}::P_{1}::operator()(VM vm{2}) {{
        """.format(modname, ozfunc.oz_function_name, ozfunc.get_arg_proto()))
        ozfunc.write_to(self)
        self.write("}") # }

