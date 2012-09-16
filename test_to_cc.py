#!/usr/bin/env python3
#
# This file just tests whether 'to_cc.py' works correctly.

from clang.cindex import TranslationUnit, Config, CursorKind
from to_cc import to_cc
from io import StringIO
from itertools import zip_longest

Config.set_compatibility_check(False)

test_content = b"""
    char* x0;
    const unsigned char** x1;
    const int* const* volatile const& x2;
    int *(*x3)(char *w, int y);
    int *(&&x4)(char*, char*);
    double&(^x5)(double**&, ...);
    _Complex float volatile* x6;
    int x7[5][6];
    int*(*x8)[5];
    long long (*(*(* const x9)[9])[7])[4];
    unsigned (*(*(*x10)(int ))[7])[4];

    struct S { int s; } x11;
    struct { int t; } x12;
    union U { int s; float f; } x13;
    union { int* p; double d; } x14;
    enum E { FOO, BAR } x15;
    union { struct { int a; int b; }; long long c; } x16;

    int (*(*x17)(void))[3];

    typedef int T;
    T x18;
    T** x19;
    T x20[3 - 2];

    @interface Foo {} @end
    @protocol P {} @end
    Foo* x21;
    id x22;
    SEL x23;
    Class x24;

//  The following are not supported yet, but we don't care right now since
//  Objective-C and C++ aren't in the scope of this project.

//  Foo<P>* x25;

//  namespace N {
//      class K;
//  }
//  N::K* x26;
"""

results = [
    'char *x',
    'unsigned char const **x',
    'int const *const *const volatile &x',
    'int *(*x)(char *, int)',
    'int *(&&x)(char *, char *)',
    'double &(^x)(double **&, ...)',
    'float _Complex volatile *x',
    'int x[5][6]',
    'int *(*x)[5]',
    'long long (*(*(*const x)[9])[7])[4]',
    'unsigned (*(*(*x)(int))[7])[4]',
    'S x',
    'struct { int t; } x',
    'U x',
    'union { int *p; double d; } x',
    'E x',
    'union { struct { int a; int b; }; long long c; } x',
    'int (*(*x)())[3]',
    'T x',
    'T **x',
    'T x[1]',
    'Foo *x',
    'id x',
    'SEL x',
    'Class x',
#   'Foo<P> *x',
#   'N::K *x'
]

tu = TranslationUnit.from_source('test.cc',
                                 args=[b'-x', b'objective-c++'],
                                 unsaved_files=[(b'test.cc', test_content)])
declarations = (d for d in tu.cursor.get_children() if d.kind == CursorKind.VAR_DECL)
for result, decl in zip_longest(results, declarations):
    typ = decl.type
    cc_decl = to_cc(typ, name='x')
    if result != cc_decl:
        print("Assertion failure:", result, "==", cc_decl)





