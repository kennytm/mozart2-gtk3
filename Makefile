MOZART_SRC_DIR ?= $(realpath ../mozart2-vm)
MOZART_DIR ?= $(MOZART_SRC_DIR)/build/debug
BOOTCOMPILER_DIR ?= $(realpath ../mozart2-bootcompiler)
MOZART_LIB_DIR ?= $(realpath ../mozart2-library)
MODULE ?= cairo
PACKAGES ?= $(MODULE)

OUT_DIR = src/$(MODULE).out/
BASE_ENV_TXT = $(OUT_DIR)baseenv.txt

EXTRA_CFLAGS = $(shell pkg-config --cflags $(PACKAGES))
EXTRA_LDFLAGS = $(shell pkg-config --libs $(PACKAGES))

CreateAst = clang++ -std=c++11 -stdlib=libc++ -Wno-return-type \
                    -I$(MOZART_DIR)/vm/main -emit-ast $(EXTRA_CFLAGS)
Generator = $(MOZART_DIR)/generator/main/generator

CXX = g++
CXXFLAGS = -std=c++11 -I$(MOZART_DIR)/vm/main -I$(MOZART_DIR)/boostenv/main -g \
           -I$(OUT_DIR) -Isrc $(EXTRA_CFLAGS)
OZBC = java -jar $(BOOTCOMPILER_DIR)/target/scala-2.9.1/bootcompiler_2.9.1-2.0-SNAPSHOT-one-jar.jar
OZBCFLAGS = -h boostenv.hh -h $(MODULE).hh -b $(BASE_ENV_TXT) \
            -m $(MOZART_DIR)/vm/main -m $(MOZART_DIR)/boostenv/main -m $(OUT_DIR)

LDFLAGS = $(MOZART_DIR)/boostenv/main/libmozartvmboost.a \
          $(MOZART_DIR)/vm/main/libmozartvm.a \
          -lboost_system -lboost_filesystem -lboost_thread -pthread \
	  $(EXTRA_LDFLAGS)

all: lib test

#-------------------------------------------------------------------------------

PYTHON_FILES = $(wildcard *.py)
TRANSLATION_RESULT = src/$(MODULE).cc src/$(MODULE).hh \
                     src/$(MODULE)-types-decl.hh src/$(MODULE)-types.hh \
		     src/$(MODULE)-builders.hh
BUILTINS_AST = src/$(MODULE).astbi
INTFIMPL_AST = src/$(MODULE).ast
BUILTINS_RESULT = $(OUT_DIR)$(MODULE)builtins.cc $(OUT_DIR)$(MODULE)builtins.hh
INTFIMPL_RESULT = $(OUT_DIR)intfimpl
CC_RESULT = src/$(MODULE).o

lib: $(CC_RESULT)

$(TRANSLATION_RESULT): $(PYTHON_FILES)
	python3 translator.py $(MODULE)

$(INTFIMPL_AST): src/$(MODULE)-types-decl.hh
	$(CreateAst) -o $@ -DMOZART_GENERATOR $<

$(BUILTINS_AST): src/$(MODULE).hh
	$(CreateAst) -o $@ -DMOZART_BUILTIN_GENERATOR $<

$(INTFIMPL_RESULT): $(INTFIMPL_AST)
	$(Generator) intfimpl $< $(OUT_DIR)
	echo 1 > $@

$(BUILTINS_RESULT): $(BUILTINS_AST)
	$(Generator) builtins $< $(OUT_DIR) $(MODULE)builtins

%.o: %.cc $(INTFIMPL_RESULT) $(BUILTINS_RESULT) src/$(MODULE)-types.hh
	$(CXX) $(CXXFLAGS) -c -o $@ $<

#-------------------------------------------------------------------------------

BASE_ENV = $(OUT_DIR)base
ESSENTIAL_OZ = c-files/$(MODULE)_test.oz \
               $(MOZART_LIB_DIR)/init/Init.oz \
               $(MOZART_SRC_DIR)/boostenv/lib/OS.oz \
               $(MOZART_LIB_DIR)/sys/Property.oz \
               $(MOZART_LIB_DIR)/sys/System.oz \
               $(MOZART_LIB_DIR)/dp/URL.oz \
               $(MOZART_LIB_DIR)/support/DefaultURL.oz \
               $(MOZART_LIB_DIR)/sp/Error.oz \
               $(MOZART_LIB_DIR)/sp/ErrorFormatters.oz
LINKER = $(OUT_DIR)linker
TEST_RESULT = src/$(MODULE)-test

test: $(TEST_RESULT)

$(BASE_ENV).cc $(BASE_ENV_TXT): $(TRANSLATION_RESULT)
	$(OZBC) $(OZBCFLAGS) --baseenv -o $@ \
            $(MOZART_LIB_DIR)/base/Base.oz $(MOZART_LIB_DIR)/boot/BootBase.oz

define EssentialOzTemplate =
OZ_RESULT += $$(OUT_DIR)$$(notdir $(1)).o
$$(OUT_DIR)$$(notdir $(1)).cc: $(1) $$(BASE_ENV_TXT)
	$$(OZBC) $$(OZBCFLAGS) -o $$@ $$<
endef
$(foreach oz, $(ESSENTIAL_OZ), $(eval $(call EssentialOzTemplate, $(oz))))

$(LINKER).cc: $(ESSENTIAL_OZ) $(BASE_ENV_TXT)
	$(OZBC) --linker $(OZBCFLAGS) -o $@ $(ESSENTIAL_OZ)

$(TEST_RESULT): $(BASE_ENV).o $(LINKER).o $(OZ_RESULT) $(CC_RESULT)
	$(CXX) -o $@ $^ $(LDFLAGS)

#-------------------------------------------------------------------------------

clean:
	rm -rf src/*

.PHONY: all clean lib test

