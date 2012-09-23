import re
from common import CC_NAME_OF_RETURN

BLACKLISTED = {
    '__va_list_tag',
    'cairo_rectangle_list_destroy',  # we don't need to call these functions at all.
    'cairo_path_destroy'
}

SPECIAL_INOUTS = {
    'cairo_get_user_data': {'return': 'NodeOut'},
    'cairo_set_user_data': {'user_data': 'NodeIn'},
    'cairo_set_dash': {'dashes': ('ListIn', 'num_dashes'), 'num_dashes': 'Skip'},
    'cairo_user_to_device': {'x': 'InOut', 'y': 'InOut'},
    'cairo_user_to_device_distance': {'dx': 'InOut', 'dy': 'InOut'},
    'cairo_device_to_user': {'x': 'InOut', 'y': 'InOut'},
    'cairo_device_to_user_distance': {'dx': 'InOut', 'dy': 'InOut'},
    'cairo_path_extents': {'x1': 'Out', 'x2': 'Out', 'y1': 'Out', 'y2': 'Out'},
}

FUNCTION_SETUP = {}

FUNCTION_TEARDOWN = {
    'cairo_copy_clip_rectangle_list': 'cairo_rectangle_list_destroy(*' + CC_NAME_OF_RETURN + ');',
    'cairo_copy_path': 'cairo_path_destroy(*' + CC_NAME_OF_RETURN + ');',
}

SPECIAL_INOUTS_FOR_TYPES = {
    'cairo_destroy_func_t': ('NodeDeleter', 0),
    'cairo_user_data_key_t const *': 'AddressIn',
    'cairo_matrix_t const *': 'PointerIn',
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

