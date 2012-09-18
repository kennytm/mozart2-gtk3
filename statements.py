from constants import *
from common import *
from fake_type import PointerOf
from to_cc import to_cc

def create_no_statements(typ, name_1, name_2, with_declaration, context):
    return []

#-------------------------------------------------------------------------------
# Post actions:

def create_out_statements_post(typ, cc_name, oz_name, with_declaration, context):
    """
    Create a list of C++ declarations and statements encoding a C value into an
    Oz UnstableNode.
    """
    prefix = 'auto ' + oz_name if with_declaration else oz_name

    if is_primitive_type(typ):
        return [prefix + " = build(vm, " + cc_name + ");"]

    elif is_c_string(typ):
        prefix = 'auto ' if with_declaration else ''
        return [prefix + " = String::build(vm, newLString(vm, toUTF<nchar>(makeLString(" + cc_name + ");"]

    elif typ.kind == TypeKind.RECORD:
        struct_decl = typ.get_declaration()
        struct_name = struct_decl.spelling.decode('utf-8')

        if struct_decl.is_definition():
            cc_statements = []
            temp_oz_names = []
            field_names = []

            record_name = strip_prefix_and_camelize(struct_name)
            for decl in struct_decl.get_children():
                subtype = decl.type
                field_name = decl.spelling.decode('utf-8')
                field_names.append(field_name)
                temp_oz_name = unique_str()
                temp_oz_names.append(temp_oz_name)
                cc_statements.extend(create_out_statements_post(subtype,
                                                                cc_name + "." + field_name,
                                                                temp_oz_name,
                                                                with_declaration=True,
                                                                context=context))

            field_names_concat = '"), MOZART_STR("'.join(field_names)
            temp_oz_names_concat = '), std::move('.join(temp_oz_names)

            cc_statements.append("""
                %s = buildRecord(vm,
                    buildArity(vm, MOZART_STR("%s"), MOZART_STR("%s")),
                    std::move(%s)
                );
            """ % (prefix, record_name, field_names_concat, temp_oz_names_concat))

        else:
            return ["%s = D_%s::build(vm, &%s);" % (prefix, struct_name, cc_name)]

        return cc_statements

    elif typ.kind == TypeKind.POINTER:
        cc_real_name = '(*(' + cc_name + '))'
        return create_out_statements_post(typ.get_pointee(),
                                          cc_real_name,
                                          oz_name,
                                          with_declaration,
                                          context)

    raise NotImplementedError('Not implemented to convert %s to %s with TypeKind %s' %
                              (cc_name, oz_name, typ.kind.spelling.decode('utf-8')))

#-------------------------------------------------------------------------------
# Pre actions:

def create_in_statements_pre(typ, oz_name, cc_name, with_declaration, context):
    """
    Create a list of C++ statements decoding an Oz RichNode into a C value. The
    target variable must already been declared.
    """
    prefix = 'auto ' + cc_name if with_declaration else cc_name

    if is_c_string(typ):
        return ["""
            auto %(unique)s = vsToString<char>(vm, %(oz)s);
            %(cc)s = %(uniq)s.c_str();
        """ % {'cc': prefix, 'oz': oz_name, 'unique': unique_str()}]

    elif is_primitive_type(typ):
        kind = typ.kind
        if kind == TypeKind.BOOL:
            interface = "BoolValue"
            method = "boolValue"
        elif kind in INTEGER_KINDS:
            interface = "IntegerValue"
            method = "intValue"
        elif kind in FLOAT_KINDS:
            interface = "FloatValue"
            method = "floatValue"

        return ['%s = %s(%s).%s(vm);' % (prefix, interface, oz_name, method)]

    elif typ.kind == TypeKind.RECORD:
        temp_interface_name = unique_str()
        struct_decl = typ.get_declaration()
        struct_name = struct_decl.spelling.decode('utf-8')

        cc_statements = ["Dottable %s(%s);" % (temp_interface_name, oz_name)]
        if with_declaration:
            cc_statements.append(struct_name + ' ' + cc_name + ';')

        for decl in struct_decl.get_children():
            subtype = decl.type
            field_name = decl.spelling.decode('utf-8')
            temp_oz_field_name = unique_str()
            cc_statements.append("""
                auto %s = %s.dot(vm, build(vm, MOZART_STR("%s")));
            """ % (temp_oz_field_name, temp_interface_name, field_name))
            cc_statements.extend(create_in_statements_pre(subtype,
                                                          temp_oz_field_name,
                                                          cc_name + '.' + field_name,
                                                          with_declaration=False,
                                                          context=context))
        return cc_statements

    elif typ.kind == TypeKind.POINTER:
        pointee = typ.get_pointee().get_canonical()
        kind = pointee.kind
        if kind == TypeKind.RECORD:
            struct = pointee.get_declaration()
            if not struct.is_definition():
                struct_name = struct.spelling.decode('utf-8')
                return ['%s = %s.as<D_%s>().value()' % (prefix, oz_name, struct_name)]

        cc_complete_name = unique_str()
        cc_statements = create_in_statements_pre(pointee,
                                                 oz_name,
                                                 cc_complete_name,
                                                 with_declaration=True,
                                                 context=context)
        cc_statements.append('%s = &%s;' % (prefix, cc_complete_name))
        return cc_statements


    raise NotImplementedError('Not implemented to convert %s to %s with TypeKind %s' %
                              (oz_name, cc_name, typ.kind.spelling.decode('utf-8')))


def create_deref_declarations_pre(typ, oz_name, cc_name, with_declaration, context):
    """
    Create a declaration for arguments accepting a C++ pointer as an output
    argument.
    """
    prefix = 'auto ' + cc_name if with_declaration else cc_name
    cc_complete_name = unique_str()
    cc_decl = to_cc(typ.get_pointee(), cc_complete_name)
    return ["%s; %s = &%s;" % (cc_decl, prefix, cc_complete_name)]

#-------------------------------------------------------------------------------

STATEMENTS_CREATORS = {
    'in': (create_in_statements_pre, create_no_statements, 'In'),
    'out': (create_deref_declarations_pre, create_out_statements_post, 'Out'),
}

#-------------------------------------------------------------------------------

def get_arg_spec(func_cursor, c_func_name):
    inouts = SPECIAL_INOUTS.get(c_func_name, {})

    for arg in func_cursor.get_children():
        if arg.kind != CursorKind.PARM_DECL:
            continue
        arg_name = arg.spelling.decode('utf-8')
        (inout, context) = inouts.get(arg_name, ('in', None))
        (stc_pre, stc_post, oz_inout) = STATEMENTS_CREATORS[inout]
        yield (arg.type.get_canonical(), arg_name, stc_pre, stc_post, oz_inout, context)

    return_type = func_cursor.result_type.get_canonical()
    if return_type.kind != TypeKind.VOID:
        (inout, context) = inouts.get('return', ('out', None))
        (stc_pre, stc_post, oz_inout) = STATEMENTS_CREATORS[inout]
        yield (PointerOf(return_type), '_x_oz_return', stc_pre, stc_post, oz_inout, context)


def get_cc_function_definition(func_cursor, c_func_name):
    """
    Get the C++ function definition from a clang function Cursor. The result is
    a 2-tuple, with the first being a C++ code of the signature of the Oz
    built-in procedure (e.g. ``, In arg1, Out arg2``), and the second being a
    list of C++ statements of the built-in procedure.
    """

    arg_specs = list(get_arg_spec(func_cursor, c_func_name))

    cc_names = []
    cc_statements = []

    for typ, oz_name, stc_pre, _, _, context in arg_specs:
        cc_name = '_x_cc_' + oz_name
        cc_names.append(cc_name)
        if stc_pre is not None:
            cc_statements.extend(stc_pre(typ, oz_name, cc_name,
                                         with_declaration=True,
                                         context=context))

    call_statement = c_func_name + '(' + ', '.join(cc_names) + ');'
    if func_cursor.result_type.get_canonical().kind != TypeKind.VOID:
        call_statement = '*_x_cc__x_oz_return = ' + call_statement
    cc_statements.append(call_statement)

    for typ, oz_name, _, stc_post, _, context in arg_specs:
        cc_name = '_x_cc_' + oz_name
        if stc_post is not None:
            cc_statements.extend(stc_post(typ, cc_name, oz_name,
                                          with_declaration=False,
                                          context=context))

    arg_proto = ''.join(', ' + oz_inout + ' ' + oz_name
                        for _, oz_name, _, _, oz_inout, _ in arg_specs
                        if oz_name != 'return')

    return (arg_proto, cc_statements)

__all__ = ['get_cc_function_definition']

