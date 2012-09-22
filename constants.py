

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
    'cairo_copy_clip_rectangle_list': 'cairo_rectangle_list_destroy(*x_cc_x_oz_return);',
    'cairo_copy_path': 'cairo_path_destroy(*x_cc_x_oz_return);',
}

SPECIAL_INOUTS_FOR_TYPES = {
    'cairo_destroy_func_t': ('NodeDeleter', 0),
    'cairo_user_data_key_t const *': 'AddressIn',
}

SPECIAL_TYPES = {
    'cairo_path_t': ("""
        OzListBuilder nodes (vm);
        int i = 0;
        while (i < cc->num_data)
        {
            auto data = &cc->data[i];
            switch (data->header.type)
            {
                case CAIRO_PATH_MOVE_TO:
                    nodes.push_back(vm, buildTuple(vm, MOZART_STR("moveTo"),
                                                   data[1].x, data[1].y));
                    break;
                case CAIRO_PATH_LINE_TO:
                    nodes.push_back(vm, buildTuple(vm, MOZART_STR("lineTo"),
                                                   data[1].x, data[1].y));
                    break;
                case CAIRO_PATH_CURVE_TO:
                    nodes.push_back(vm, buildTuple(vm, MOZART_STR("curveTo"),
                                                   data[1].x, data[1].y,
                                                   data[2].x, data[2].y,
                                                   data[3].x, data[3].y));
                    break;
                case CAIRO_PATH_CLOSE_PATH:
                    nodes.push_back(vm, MOZART_STR("closePath"));
                    break;
            }
            i += data->header.length;
        }

        return nodes.get(vm);
    """, None)
}

