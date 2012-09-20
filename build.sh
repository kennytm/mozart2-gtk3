#!/bin/sh

MOZART_DIR=`realpath ../mozart2/build/debug`

python3 translator.py $1
cd src
mkdir $1.out
clang++ -std=c++11 -stdlib=libc++ \
        -I$MOZART_DIR/vm/main \
        -femit-ast \
        -o $1.astbi \
        -DMOZART_BUILTIN_GENERATOR \
        $1.hh
clang++ -std=c++11 -stdlib=libc++ \
        -I$MOZART_DIR/vm/main \
        -femit-ast \
        -o $1.ast \
        -DMOZART_GENERATOR \
        $1-types-decl.hh
$MOZART_DIR/generator/main/generator intfimpl $1.ast $1.out/
$MOZART_DIR/generator/main/generator builtins $1.astbi $1.out/ ${1}builtins
g++ -std=c++11 -I$MOZART_DIR/vm/main -I$MOZART_DIR/boostenv/main -I$1.out -I. -o $1.o $1.cc

