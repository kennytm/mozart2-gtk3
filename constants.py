BLACKLISTED_TYPEDEFS = {'__va_list_tag'}

SPECIAL_INOUTS = {
#    'test_foo_get_pair': {'pair': 'Out'},
#    'test_foo_get_obj': {'return': 'NodeOut'},
#    'test_foo_set_obj': {'obj': 'NodeIn', 'deleter': ('NodeDeleter', 1)},
    'cairo_get_user_data': {'return': 'NodeOut'},
    'cairo_set_user_data': {'user_data': 'NodeIn', 'destroy': ('NodeDeleter', 0)},
}

#SPECIAL_TYPES = {
#    'cairo_destroy_func_t':
#}

