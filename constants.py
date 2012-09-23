import re
from common import CC_NAME_OF_RETURN, cc_name_of, unique_str

BLACKLISTED = [re.compile(p) for p in [
    '__va_list_tag$',
    'cairo_(?:rectangle_list|path)_destroy$',
    # ^ we don't need to call these functions at all.
    'cairo_(?:glyph|text_cluster)_(?:allocate|free)$',
    # ^ we will destroy them on behalf of the users.
    'cairo_user_(?:scaled_font|font_face)',
    # ^ TODO: restore these functions.
]]

SPECIAL_INOUTS = [(re.compile(p), i) for p, i in {
    'cairo_(?:font_face_|scaled_font_)?get_user_data$':
        {'return': 'NodeOut'},
    'cairo_(?:font_face_|scaled_font_)?set_user_data$':
        {'user_data': 'NodeIn'},
    'cairo_(?:user_to_device|device_to_user)$':
        {'x': 'InOut', 'y': 'InOut'},
    'cairo_(?:user_to_device|device_to_user)_distance$':
        {'dx': 'InOut', 'dy': 'InOut'},
    'cairo_(?:path|stroke|fill|clip)_extents$':
        {'x1': 'Out', 'x2': 'Out', 'y1': 'Out', 'y2': 'Out'},
    'cairo_get_(?:font_)?matrix$':
        {'matrix': 'Out'},
    'cairo_scaled_font_get_(?:ctm|(?:font|scale)_matrix)$':
        {'ctm': 'Out', 'scale_matrix': 'Out', 'font_matrix': 'Out'},
    'cairo_get_current_point$':
        {'x': 'Out', 'y': 'Out'},
    'cairo_(?:show_(?:text_)?glyphs|glyph_path)$':
        {'utf8_len': ('Constant', '-1')},
    'cairo_(?:(?:scaled_font_)?(?:text|glyph)|(?:scaled_)?font)_extents$':
        {'extents': 'Out'},
    'cairo_scaled_font_text_to_glyphs':
        {'cluster_flags': 'Out', 'utf8_len': ('Constant', '-1')},
}.items()]

FUNCTION_PRE_SETUP = {}

FUNCTION_POST_SETUP = {}

FUNCTION_PRE_TEARDOWN = {}

FUNCTION_POST_TEARDOWN = {
    'cairo_copy_clip_rectangle_list':
        'cairo_rectangle_list_destroy(*' + CC_NAME_OF_RETURN + ');',
    'cairo_copy_path':
        'cairo_path_destroy(*' + CC_NAME_OF_RETURN + ');',
    'cairo_copy_path_flat':
        'cairo_path_destroy(*' + CC_NAME_OF_RETURN + ');',
    'cairo_scaled_font_text_to_glyphs': """
        cairo_text_cluster_free(*%s);
        cairo_glyph_free(*%s);
    """ % (cc_name_of('clusters'), cc_name_of('glyphs')),
}

SPECIAL_INOUTS_FOR_TYPES = {
    'cairo_destroy_func_t': ('NodeDeleter', 0),
    'cairo_user_data_key_t const *': 'AddressIn',
}

SPECIAL_TYPES = {
    'cairo_path': ("""
        OzListBuilder nodes (vm);
        int i = 0;
        while (i < cc.num_data)
        {
            auto data = &cc.data[i];
            switch (data->header.type)
            {
                case CAIRO_PATH_MOVE_TO:
                    nodes.push_back(vm, buildTuple(vm, MOZART_STR("moveTo"),
                                                   data[1].point.x, data[1].point.y));
                    break;
                case CAIRO_PATH_LINE_TO:
                    nodes.push_back(vm, buildTuple(vm, MOZART_STR("lineTo"),
                                                   data[1].point.x, data[1].point.y));
                    break;
                case CAIRO_PATH_CURVE_TO:
                    nodes.push_back(vm, buildTuple(vm, MOZART_STR("curveTo"),
                                                   data[1].point.x, data[1].point.y,
                                                   data[2].point.x, data[2].point.y,
                                                   data[3].point.x, data[3].point.y));
                    break;
                case CAIRO_PATH_CLOSE_PATH:
                    nodes.push_back(vm, MOZART_STR("closePath"));
                    break;
            }
            i += data->header.length;
        }

        return nodes.get(vm);
    """, """
        std::vector<cairo_path_data_t> data_list;
        ozListForEach(vm, oz, [vm, &data_list](RichNode node) {
            using namespace mozart::patternmatching;

            double x1, y1, x2, y2, x3, y3;
            cairo_path_data_t data[4];

            if (matchesTuple(vm, node, MOZART_STR("moveTo"), capture(x1), capture(y1)))
            {
                data[0].header.type = CAIRO_PATH_MOVE_TO;
                data[0].header.length = 2;
                data[1].point.x = x1;
                data[1].point.y = y1;
                data_list.insert(data_list.end(), data, data+2);
            }
            else if (matchesTuple(vm, node, MOZART_STR("lineTo"), capture(x1), capture(y1)))
            {
                data[0].header.type = CAIRO_PATH_LINE_TO;
                data[0].header.length = 2;
                data[1].point.x = x1;
                data[1].point.y = y1;
                data_list.insert(data_list.end(), data, data+2);
            }
            else if (matchesTuple(vm, node, MOZART_STR("curveTo"), capture(x1), capture(y1),
                                                                   capture(x2), capture(y2),
                                                                   capture(x3), capture(y3)))
            {
                data[0].header.type = CAIRO_PATH_LINE_TO;
                data[0].header.length = 4;
                data[1].point.x = x1;
                data[1].point.y = y1;
                data[2].point.x = x2;
                data[2].point.y = y2;
                data[3].point.x = x3;
                data[3].point.y = y3;
                data_list.insert(data_list.end(), data, data+4);
            }
            else if (matches(vm, node, MOZART_STR("closePath")))
            {
                data[0].header.type = CAIRO_PATH_CLOSE_PATH;
                data[0].header.length = 1;
                data_list.push_back(data[0]);
            }
            else
            {
                raiseTypeError(vm, MOZART_STR("cairo_path_data_t"), node);
            }
        }, MOZART_STR("cairo_path_data_t"));

        cc.status = CAIRO_STATUS_SUCCESS;
        cc.num_data = data_list.size();
        cc.data = new (vm) cairo_path_data_t[cc.num_data];
        memcpy(cc.data, data_list.data(), sizeof(*cc.data) * cc.num_data);
    """)
}

SPECIAL_FUNCTIONS = {
    'cairo_get_dash':
        (', In cr, Out dashes, Out offset', ["""
            cairo_t* cc_cr;
            unbuild(vm, cr, cc_cr);
            int cc_num_dashes = cairo_get_dash_count(cc_cr);
            std::unique_ptr<double[]> cc_dashes (new double[cc_num_dashes]);
            double cc_offset;
            cairo_get_dash(cc_cr, cc_dashes.get(), &cc_offset);
            dashes = buildDynamicList(vm, cc_dashes.get(), cc_dashes.get() + cc_num_dashes);
            offset = build(vm, cc_offset);
        """])
}

OPAQUE_STRUCTS = set()

