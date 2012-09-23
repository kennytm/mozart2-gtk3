import re
from common import CC_NAME_OF_RETURN

BLACKLISTED = [re.compile(p) for p in [
    '__va_list_tag$',
    'cairo_(?:rectangle_list|path)_destroy$',
    # ^ we don't need to call these functions at all.
    'cairo_(?:glyph|text_cluster)_(?:allocate|free)$',
    # ^ we will allocate them on behalf of the users.
]]

SPECIAL_INOUTS = [(re.compile(p), i) for p, i in {
    'cairo_(?:font_face_|scaled_font_)?get_user_data$':
        {'return': 'NodeOut'},
    'cairo_(?:font_face_|scaled_font_)?set_user_data$':
        {'user_data': 'NodeIn'},
    'cairo_set_dash$':
        {'dashes': ('ListIn', 'num_dashes'), 'num_dashes': 'Skip'},
    'cairo_(?:user_to_device|device_to_user)$':
        {'x': 'InOut', 'y': 'InOut'},
    'cairo_(?:user_to_device|device_to_user)_distance$':
        {'dx': 'InOut', 'dy': 'InOut'},
    'cairo_(?:path|stroke|fill|clip)_extents$':
        {'x1': 'Out', 'x2': 'Out', 'y1': 'Out', 'y2': 'Out'},
    'cairo_get_font_matrix$':
        {'matrix': 'Out'},
    'cairo_scaled_font_get_(?:ctm|(?:font|scale)_matrix)$':
        {'ctm': 'Out', 'scale_matrix': 'Out', 'font_matrix': 'Out'},
    'cairo_get_current_point$':
        {'x': 'Out', 'y': 'Out'},
    'cairo_(?:show_(?:text_)?glyphs|glyph_path)$':
        {'glyphs': ('ListIn', 'num_glyphs'), 'num_glyphs': 'Skip',
         'clusters': ('ListIn', 'num_clusters'), 'num_clusters': 'Skip',
         'utf8_len': ('Constant', '-1')},
    'cairo_(?:(?:scaled_font_)?(?:text|glyph)|(?:scaled_)?font)_extents$':
        {'extents': 'Out',
         'num_glyphs': 'Skip', 'glyphs': ('ListIn', 'num_glyphs')},
}.items()]

FUNCTION_SETUP = {}

FUNCTION_TEARDOWN = {
    'cairo_copy_clip_rectangle_list':
        'cairo_rectangle_list_destroy(*' + CC_NAME_OF_RETURN + ');',
    'cairo_copy_path':
        'cairo_path_destroy(*' + CC_NAME_OF_RETURN + ');',
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

OPAQUE_STRUCTS = set()

