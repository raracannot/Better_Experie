# 对象卡片式高级选择器

import bpy
import re
import math
import fnmatch

# ========== 工具函数 ==========
def matches_pattern(text, pattern, ignore_case, use_regex=False, use_wildcard=False):
    if not pattern:
        return False
    # 通配符匹配（* ?），尊重忽略大小写
    if use_wildcard:
        if ignore_case:
            return fnmatch.fnmatchcase(text.lower(), pattern.lower())
        return fnmatch.fnmatchcase(text, pattern)
    # 正则匹配
    if use_regex:
        try:
            flags = re.IGNORECASE if ignore_case else 0
            return re.search(pattern, text, flags) is not None
        except re.error:
            return False
    # 普通子串包含
    if ignore_case:
        return pattern.lower() in text.lower()
    return pattern in text

def get_object_type_enum_items(self, context):
    return [(item.identifier, item.name, item.description) for item in bpy.types.Object.bl_rna.properties['type'].enum_items]

def get_modifier_enum_items(self, context):
    return [(item.identifier, item.name, item.description) for item in bpy.types.Modifier.bl_rna.properties['type'].enum_items if item.identifier != 'DUMMY']

    
# ========== 卡片数据结构 ==========
class BetterExperie_ObjectFilterCardItem(bpy.types.PropertyGroup):
    rule_type: bpy.props.EnumProperty(
        items=[
            ('VERTEX_RANGE', "顶点数范围", ""),
            ('OBJ_NAME', "对象名称包含", ""),
            ('MAT_NAME', "材质名称包含", ""),
            ('MODIFIER', "包含修改器", ""),
            ('OBJ_TYPE', "对象类型", ""),
            ('PROPERTY', "属性包含", ""),
            ('KEYFRAME', "有关键帧", ""),
            ('KEYFRAME_FRAME_RANGE', "关键帧时间范围", ""),
            ('NODE_NAME', "节点名称包含", ""),
            ('OBJ_COLOR', "物体颜色", "选中与指定颜色接近的物体"),
        ],
        default='VERTEX_RANGE',
        name="筛查规则"
    )
    str_param: bpy.props.StringProperty(name="关键词")
    ignore_case: bpy.props.BoolProperty(name="忽略大小写", default=True)
    use_regex: bpy.props.BoolProperty(
        name="启用正则匹配",
        description="按正则表达式匹配名称。\n示例：\n^Chair_ 匹配以Chair_开头；\n_v\\d+$ 匹配结尾带_v1/_v2等版本号；\n(Lamp|Light) 匹配Lamp或Light",
        default=False)
    use_wildcard: bpy.props.BoolProperty(
        name="启用通配符匹配",
        description="按通配符匹配名称：*匹配任意字符，?匹配单个字符。\n示例：\nChair* 匹配以Chair开头；\n*_L* 匹配名称中带_L的；\nModel_?.blend 匹配Model_A.blend等",
        default=False)
    int_min: bpy.props.IntProperty(name="最小值", default=0, min=0)
    int_max: bpy.props.IntProperty(name="最大值", default=1000, min=0)
    enum_param: bpy.props.EnumProperty(items=get_object_type_enum_items, name="类型")
    mod_param: bpy.props.EnumProperty(items=get_modifier_enum_items, name="修改器")
    prop_param: bpy.props.EnumProperty(
        items=[
            ('VERTEX_GROUP', "顶点组", ""),
            ('SHAPE_KEY', "形态键", ""),
            ('UV', "UV贴图", ""),
            ('COLOR_ATTRIBUTE', "颜色属性", ""),
        ],
        default='VERTEX_GROUP',
        name="属性类型"
    )
    color_param: bpy.props.FloatVectorProperty(
        name="目标颜色", subtype='COLOR', size=4,
        min=0.0, max=1.0, default=(1.0, 1.0, 1.0, 1.0))
    color_threshold: bpy.props.FloatProperty(
        name="近似阈值", description="颜色 RGB 距离阈值，0为完全一致",
        default=0.1, min=0.0, max=1.0, subtype='FACTOR')
    invert: bpy.props.BoolProperty(name="反向", default=False)

# ========== 全局配置存储 ==========
class BetterExperie_ObjectFilterConfig(bpy.types.PropertyGroup):
    selection_mode: bpy.props.EnumProperty(
        items=[
            ('SET_SELECTION', "设为选择", ""),
            ('ADD_TO_SELECTION', "添加选择", ""),
            ('REMOVE_FROM_SELECTION', "移除选择", ""),
        ],
        default='SET_SELECTION',
        name="选择模式"
    )
    selection_scope: bpy.props.EnumProperty(
        items=[
            ('ALL_OBJECTS', "全部对象", ""),
            ('IN_COLLECTION', "选中集合", ""),
            ('IN_VIEWPORT', "视口可见", ""),
        ],
        default='ALL_OBJECTS',
        name="选择范围"
    )
    filter_cards: bpy.props.CollectionProperty(type=BetterExperie_ObjectFilterCardItem)

    logic_mode: bpy.props.EnumProperty(
        items=[
            ('AND', "满足（且）", ""),
            ('OR', "任一满足（或）", ""),
            ('NOT', "排除（非）", ""),
        ],
        default='AND', name="逻辑关系"
    )
    
# ========== 独立 Operator：增删改卡片 ==========
class BetterExperie_OT_ObjectFilterAddCard(bpy.types.Operator):
    bl_idname = "better_experie.object_filter_add_card"
    bl_label = "添加卡片"
    bl_description = "添加新卡片"
    def execute(self, context):
        config = context.scene.better_experie_object_filter_config_prop
        card = config.filter_cards.add()
        if len(config.filter_cards) > 1:
            last = config.filter_cards[-2]
            card.rule_type = last.rule_type
            card.str_param = last.str_param
            card.ignore_case = last.ignore_case
            card.use_regex = last.use_regex
            card.use_wildcard = last.use_wildcard
            card.int_min = last.int_min
            card.int_max = last.int_max
            card.enum_param = last.enum_param
            card.mod_param = last.mod_param
            card.prop_param = last.prop_param
            card.color_param = last.color_param
            card.color_threshold = last.color_threshold
            card.invert = last.invert
            self.report({'INFO'}, "新建一张筛查卡片")
        return {'FINISHED'}

class BetterExperie_OT_ObjectFilterCopyCard(bpy.types.Operator):
    bl_idname = "better_experie.object_filter_copy_card"
    bl_label = "复制卡片"
    bl_description = "复制当前卡片并插入到其后"
    card_index: bpy.props.IntProperty()
    def execute(self, context):
        config = context.scene.better_experie_object_filter_config_prop
        src = config.filter_cards[self.card_index]
        new = config.filter_cards.add()
        new.rule_type = src.rule_type
        new.str_param = src.str_param
        new.ignore_case = src.ignore_case
        new.use_regex = src.use_regex
        new.use_wildcard = src.use_wildcard
        new.int_min = src.int_min
        new.int_max = src.int_max
        new.enum_param = src.enum_param
        new.mod_param = src.mod_param
        new.prop_param = src.prop_param
        new.color_param = src.color_param
        new.color_threshold = src.color_threshold
        new.invert = src.invert
        # 移动到原卡片之后
        config.filter_cards.move(len(config.filter_cards)-1, self.card_index+1)
        self.report({'INFO'}, "成功复制所选筛查卡片")
        return {'FINISHED'}

class BetterExperie_OT_ObjectFilterDeleteCard(bpy.types.Operator):
    bl_idname = "better_experie.object_filter_delete_card"
    bl_label = "删除卡片"
    bl_description = "删除当前卡片"
    card_index: bpy.props.IntProperty()
    def execute(self, context):
        config = context.scene.better_experie_object_filter_config_prop
        if len(config.filter_cards) > 1:
            config.filter_cards.remove(self.card_index)
            self.report({'INFO'}, "删除所选筛查卡片")
        else:
            self.report({'INFO'}, "请至少保留一张筛查卡片")
        return {'FINISHED'}

# ========== 弹窗 Operator（只负责显示和执行筛选） ==========
class BetterExperie_OT_ObjectFilterBatchSelector(bpy.types.Operator):
    bl_idname = "better_experie.object_filter_batch_selector"
    bl_label = "卡片式高级选择器"
    bl_description = "配置筛选卡片并执行选择"
    bl_options = {'UNDO'}

    def invoke(self, context, event):
        config = context.scene.better_experie_object_filter_config_prop
        if len(config.filter_cards) == 0:
            config.filter_cards.add()
            
        return context.window_manager.invoke_props_dialog(self, width=500)

    def draw(self, context):
        layout = self.layout
        config = context.scene.better_experie_object_filter_config_prop

        # 全局设置
        row = layout.row()
        row.prop(config, "selection_mode", text="")
        row.prop(config, "selection_scope", text="")
        row.prop(config, "logic_mode", text="")

        # 卡片列表
        for idx, card in enumerate(config.filter_cards):
            box = layout.box()
            header = box.row(align=True)
            header.prop(card, "invert", text="", icon='ARROW_LEFTRIGHT')
            header.prop(card, "rule_type", text="")
            copy_op = header.operator("better_experie.object_filter_copy_card", text="", icon='COPY_ID')
            copy_op.card_index = idx
            del_op = header.operator("better_experie.object_filter_delete_card", text="", icon='X')
            del_op.card_index = idx
            self.draw_card_ui(box, card)

        # 添加卡片按钮
        layout.operator("better_experie.object_filter_add_card", text="添加卡片", icon='ADD')

    def draw_card_ui(self, layout, card):
        rule = card.rule_type
        col = layout.column(align=True)
        if rule == 'VERTEX_RANGE':
            col.prop(card, "int_min", text="顶点≥")
            col.prop(card, "int_max", text="顶点≤")
        elif rule == 'OBJ_NAME':
            col.prop(card, "str_param", text="名称包含")
            row = col.row()
            row.prop(card, "ignore_case")
            row.prop(card, "use_regex")
            row.prop(card, "use_wildcard")
            if card.use_regex and card.use_wildcard:
                col.label(text="正则与通配符同时开启，通配符优先生效", icon='ERROR')
        elif rule == 'MAT_NAME':
            col.prop(card, "str_param", text="材质包含")
            row = col.row()
            row.prop(card, "ignore_case")
            row.prop(card, "use_regex")
            row.prop(card, "use_wildcard")
            if card.use_regex and card.use_wildcard:
                col.label(text="正则与通配符同时开启，通配符优先生效", icon='ERROR')
        elif rule == 'MODIFIER':
            col.prop(card, "mod_param")
        elif rule == 'OBJ_TYPE':
            col.prop(card, "enum_param")
        elif rule == 'PROPERTY':
            col.prop(card, "prop_param")
            col.prop(card, "str_param", text="包含")
            row = col.row()
            row.prop(card, "ignore_case")
            row.prop(card, "use_regex")
            row.prop(card, "use_wildcard")
            if card.use_regex and card.use_wildcard:
                col.label(text="正则与通配符同时开启，通配符优先生效", icon='ERROR')
        elif rule == 'KEYFRAME':
            col.label(text="条件：有关键帧对象")
        elif rule == 'KEYFRAME_FRAME_RANGE':
            col.prop(card, "int_min", text="起始帧≥")
            col.prop(card, "int_max", text="结束帧≤")
        elif rule == 'NODE_NAME':
            col.prop(card, "str_param", text="节点包含")
            row = col.row()
            row.prop(card, "ignore_case")
            row.prop(card, "use_regex")
            col.prop(card, "use_wildcard")
            if card.use_regex and card.use_wildcard:
                col.label(text="正则与通配符同时开启，通配符优先生效", icon='ERROR')
        elif rule == 'OBJ_COLOR':
            col.prop(card, "color_param", text="")
            col.prop(card, "color_threshold", slider=True)

    # ---------- 筛选核心逻辑 ----------
    def get_scope_objects(self, context):
        config = context.scene.better_experie_object_filter_config_prop
        scope = config.selection_scope
        valid_types = {'MESH', 'CURVE', 'SURFACE', 'META', 'FONT', 'POINTCLOUD', 'VOLUME',
                       'GPENCIL', 'ARMATURE', 'LATTICE', 'EMPTY', 'LIGHT', 'CAMERA', 'SPEAKER'}
        if scope == 'IN_COLLECTION':
            return [o for o in context.selected_objects if o.type in valid_types]
        elif scope == 'ALL_OBJECTS':
            return [o for o in context.view_layer.objects if o.type in valid_types]
        elif scope == 'IN_VIEWPORT':
            return [o for o in context.visible_objects if o.type in valid_types]
        return []

    def get_action_fcurves(self, action):
        if hasattr(action, 'fcurves'):
            return list(action.fcurves)
        if hasattr(action, 'layers'):
            fcurves = []
            for layer in action.layers:
                for strip in layer.strips:
                    if hasattr(strip, 'channelbags'):
                        for channelbag in strip.channelbags:
                            if hasattr(channelbag, 'fcurves'):
                                fcurves.extend(channelbag.fcurves)
            return fcurves
        return []

    def get_keyframe_frame_range(self, obj):
        if not obj.animation_data or not obj.animation_data.action:
            return (None, None)
        action = obj.animation_data.action
        fcurves = self.get_action_fcurves(action)
        min_frame = float('inf')
        max_frame = -float('inf')
        has_key = False
        for fcurve in fcurves:
            for kp in fcurve.keyframe_points:
                frame = kp.co.x
                if frame < min_frame:
                    min_frame = frame
                if frame > max_frame:
                    max_frame = frame
                has_key = True
        if not has_key:
            return (None, None)
        return (min_frame, max_frame)

    def match_card(self, obj, card):
        rule = card.rule_type
        result = False

        if rule == 'VERTEX_RANGE':
            if hasattr(obj.data, 'vertices'):
                cnt = len(obj.data.vertices)
                result = card.int_min <= cnt <= card.int_max
        elif rule == 'OBJ_NAME':
            result = matches_pattern(obj.name, card.str_param, card.ignore_case, card.use_regex, card.use_wildcard)
        elif rule == 'MAT_NAME':
            if hasattr(obj.data, 'materials'):
                for mat in obj.data.materials:
                    if mat and matches_pattern(mat.name, card.str_param, card.ignore_case, card.use_regex, card.use_wildcard):
                        result = True
                        break
        elif rule == 'MODIFIER':
            result = any(mod.type == card.mod_param for mod in obj.modifiers)
        elif rule == 'OBJ_TYPE':
            result = obj.type == card.enum_param
        elif rule == 'PROPERTY':
            t = card.prop_param
            kw = card.str_param
            if t == 'VERTEX_GROUP':
                result = any(matches_pattern(vg.name, kw, card.ignore_case, card.use_regex, card.use_wildcard) for vg in obj.vertex_groups)
            elif t == 'SHAPE_KEY':
                result = obj.data.shape_keys and any(
                    matches_pattern(sk.name, kw, card.ignore_case, card.use_regex, card.use_wildcard) for sk in obj.data.shape_keys.key_blocks)
            elif t == 'UV':
                result = any(matches_pattern(uv.name, kw, card.ignore_case, card.use_regex, card.use_wildcard) for uv in obj.data.uv_layers)
            elif t == 'COLOR_ATTRIBUTE':
                result = any(matches_pattern(ca.name, kw, card.ignore_case, card.use_regex, card.use_wildcard) for ca in obj.data.color_attributes)
        elif rule == 'KEYFRAME':
            if obj.animation_data and obj.animation_data.action:
                fcurves = self.get_action_fcurves(obj.animation_data.action)
                result = any(fcurve.keyframe_points for fcurve in fcurves)
        elif rule == 'KEYFRAME_FRAME_RANGE':
            min_frame, max_frame = self.get_keyframe_frame_range(obj)
            if min_frame is not None:
                result = not (max_frame < card.int_min or min_frame > card.int_max)
        elif rule == 'NODE_NAME':
            kw = card.str_param
            found = False
            if hasattr(obj.data, 'materials'):
                for mat in obj.data.materials:
                    if mat and mat.node_tree:
                        for n in mat.node_tree.nodes:
                            if matches_pattern(n.name, kw, card.ignore_case, card.use_regex, card.use_wildcard) or \
                               matches_pattern(n.label, kw, card.ignore_case, card.use_regex, card.use_wildcard):
                                found = True
                                break
                    if found:
                        break
            if not found:
                for mod in obj.modifiers:
                    if mod.type == 'NODES' and mod.node_group:
                        for n in mod.node_group.nodes:
                            if matches_pattern(n.name, kw, card.ignore_case, card.use_regex, card.use_wildcard) or \
                               matches_pattern(n.label, kw, card.ignore_case, card.use_regex, card.use_wildcard):
                                found = True
                                break
                    if found:
                        break
            result = found
        elif rule == 'OBJ_COLOR':
            c1 = obj.color
            c2 = card.color_param
            dist = math.sqrt(
                (c1[0] - c2[0]) ** 2 +
                (c1[1] - c2[1]) ** 2 +
                (c1[2] - c2[2]) ** 2
            ) / math.sqrt(3)
            result = dist <= card.color_threshold

        if card.invert:
            result = not result
        return result

    def execute_filters(self, context):
        config = context.scene.better_experie_object_filter_config_prop
        all_objs = self.get_scope_objects(context)
        cards = config.filter_cards
        logic_mode = config.logic_mode

        result = []
        for obj in all_objs:
            matches = [self.match_card(obj, card) for card in cards]

            if logic_mode == 'AND':
                ok = all(matches)
            elif logic_mode == 'OR':
                ok = any(matches)
            elif logic_mode == 'NOT':
                ok = not any(matches)
            
            if ok:
                result.append(obj)

        # 应用选择
        if config.selection_mode == 'SET_SELECTION':
            bpy.ops.object.select_all(action='DESELECT')

        for obj in result:
            obj.select_set(config.selection_mode != 'REMOVE_FROM_SELECTION')

        self.report({'INFO'}, f"选中 {len(result)} 个对象")
        
        
    def execute(self, context):
        self.execute_filters(context)
        return {'FINISHED'}

# ========== 注册 ==========
classes = (
    BetterExperie_ObjectFilterCardItem,
    BetterExperie_ObjectFilterConfig,
    BetterExperie_OT_ObjectFilterAddCard,
    BetterExperie_OT_ObjectFilterCopyCard,
    BetterExperie_OT_ObjectFilterDeleteCard,
    BetterExperie_OT_ObjectFilterBatchSelector,
)

# def object_filter_draw(self, context):
    # layout = self.layout
    # layout.separator(type="LINE")
    # layout.operator("better_experie.object_filter_batch_selector", text="筛选式选取", icon='FILTER')

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.better_experie_object_filter_config_prop = bpy.props.PointerProperty(type=BetterExperie_ObjectFilterConfig)
    # bpy.types.VIEW3D_MT_select_object.append(object_filter_draw)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.better_experie_object_filter_config_prop
    # bpy.types.VIEW3D_MT_select_object.remove(object_filter_draw)

if __name__ == "__main__":
    register()