BLACKLISTED = {
    '__va_list_tag',
    'cairo_rectangle_list_destroy'  # we don't need to call this function at all.
}

SPECIAL_INOUTS = {
    'cairo_get_user_data': {'return': 'NodeOut'},
    'cairo_set_user_data': {'user_data': 'NodeIn'},
}

FUNCTION_SETUP = {}

FUNCTION_TEARDOWN = {
    'cairo_copy_clip_rectangle_list': """
        cairo_rectangle_list_destroy(*_x_cc__x_oz_return);
    """
}

SPECIAL_INOUTS_FOR_TYPES = {
    'cairo_destroy_func_t': ('NodeDeleter', 0),
}

SPECIAL_TYPES = {
}

