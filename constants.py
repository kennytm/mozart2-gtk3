BLACKLISTED_TYPEDEFS = {
    '__va_list_tag'
}

BLACKLISTED_FUNCTIONS = {
    'cairo_rectangle_list_destroy'  # we don't need to call this function at all.
}

SPECIAL_INOUTS = {
    'cairo_get_user_data': {'return': 'NodeOut'},
    'cairo_set_user_data': {'user_data': 'NodeIn', 'destroy': ('NodeDeleter', 0)},
}

SPECIAL_TYPES = {
    '_cairo_rectangle_list': ("""
            return buildRecord(vm,
                buildArity(vm, MOZART_STR("rectangleList"), MOZART_STR("status"), MOZART_STR("rectangles")),
                build(vm, cc.status), buildDynamicList(vm, cc.rectangles, cc.num_rectangles)
            );
        """, None)
}

#SPECIAL_TYPES = {
#    'cairo_destroy_func_t':
#}

