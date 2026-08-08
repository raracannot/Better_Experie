# 网格卡片式高级选择器

import bpy
import math
import bmesh
import mathutils 

# ========== 卡片数据结构 ==========
class BetterExperie_MeshFilterCardItem(bpy.types.PropertyGroup):
    rule_type: bpy.props.EnumProperty(
        items=[
            ('EDGE_LENGTH', "边长度范围", "选中指定长度范围的边"),
            ('FACE_AREA', "面面积范围", "选中指定面积范围的面"),
            ('VERT_EDGE_COUNT', "点边数（仅点模式）", "选中链接了指定数量边的点，仅点模式下起效"),
            ('FACE_EDGE_COUNT', "面边数", "选中链接了指定数量边的面"),
            ('EDGE_TYPE', "按边类型", "选中指定类型的边"),
            ('EDGE_SAME_DIR', "相同方向边（参考已选中）", "参考已选中的边，选中其他符合夹角的边"), 
            ('EDGE_SAME_UV_DIR', "相同UV方向边（参考已选中）", "参考已选中的边，选中其他符合夹角的边"),
            ('FACE_VIEW_ALIGN', "朝向视口的面", "参考当前视口，选中朝向视口的面"),
            ('EDGE_FACE_COUNT', "边面数", "选中邻面数量在指定范围内的边"),
            ('VERTEX_GROUP', "顶点组", "选中属于指定顶点组的元素（点/边/面）"),
            ('EDGE_ANGLE', "边角度", "按边的邻面夹角筛选边"),
        ],
        default='FACE_EDGE_COUNT',
        name="筛选规则"
    )

    float_min: bpy.props.FloatProperty(name="最小值", default=0.0, min=0)
    float_max: bpy.props.FloatProperty(name="最大值", default=10.0, min=0)
    int_min: bpy.props.IntProperty(name="最小值", default=0, min=0)
    int_max: bpy.props.IntProperty(name="最大值", default=100, min=0)
    
    angle_threshold: bpy.props.FloatProperty(name="角度阈值", default=10.0, min=0, max=90)

    str_param: bpy.props.StringProperty(name="顶点组关键词")
    ignore_case: bpy.props.BoolProperty(name="忽略大小写", default=True)
    use_regex: bpy.props.BoolProperty(
        name="启用正则匹配",
        description="按正则表达式匹配顶点组名。示例：^hand 匹配以hand开头的组；(L|R)$ 匹配结尾为L或R的组",
        default=False)
    use_wildcard: bpy.props.BoolProperty(
        name="启用通配符匹配",
        description="按通配符匹配顶点组名：*任意字符，?单字符。示例：hand* 匹配以hand开头的组；*_L 匹配结尾为_L的组",
        default=False)

    angle_compare: bpy.props.EnumProperty(
        name="角度比较",
        items=[
            ('LESS', "小于等于", "夹角 ≤ 阈值"),
            ('GREATER', "大于等于", "夹角 ≥ 阈值"),
        ],
        default='LESS')
    angle_value: bpy.props.FloatProperty(
        name="角度阈值", default=30.0, min=0.0, max=360.0, subtype='ANGLE')

    edge_type: bpy.props.EnumProperty(
        items=[
            ('SHARP', "锐边", ""),
            ('SMOOTH', "平滑边", ""),
            ('SEAM', "缝合边", ""),
            ('BOUNDARY', "边界边", ""),
            ('BEVEL', "倒角边", ""),
            ('CREASE', "折痕边", ""),
            ('FREESTYLE', "Freestyle边", "")
        ],
        name="边类型"
    )
    
    invert: bpy.props.BoolProperty(name="反向", default=False)

# ========== 全局配置 ==========
class BetterExperie_MeshFilterConfig(bpy.types.PropertyGroup):
    selection_mode: bpy.props.EnumProperty(
        items=[
            ('SET_SELECTION', "设为选择", ""),
            ('ADD_TO_SELECTION', "添加选择", ""),
            ('REMOVE_FROM_SELECTION', "移除选择", ""),
        ],
        default='SET_SELECTION',
        name="选择模式"
    )
    logic_mode: bpy.props.EnumProperty(
        items=[
            ('AND', "全部满足", ""),
            ('OR', "任一满足", ""),
            ('NOT', "排除所有", ""),
        ],
        default='AND', name="组合逻辑"
    )
    filter_cards: bpy.props.CollectionProperty(type=BetterExperie_MeshFilterCardItem)

# ========== 卡片操作 ==========
class BetterExperie_OT_MeshFilterAddCard(bpy.types.Operator):
    bl_idname = "better_experie.mesh_filter_add_card"
    bl_label = "添加卡片"
    bl_description = "添加一个新的网格筛选规则卡片"
    def execute(self, context):
        config = context.scene.better_experie_mesh_filter_prop
        card = config.filter_cards.add()
        if len(config.filter_cards) > 1:
            last = config.filter_cards[-2]
            card.rule_type = last.rule_type
            card.int_min = last.int_min
            card.int_max = last.int_max
            card.float_min = last.float_min
            card.float_max = last.float_max
            card.edge_type = last.edge_type
            card.angle_threshold = last.angle_threshold
            card.str_param = last.str_param
            card.ignore_case = last.ignore_case
            card.use_regex = last.use_regex
            card.use_wildcard = last.use_wildcard
            card.angle_compare = last.angle_compare
            card.angle_value = last.angle_value
            card.invert = last.invert
        return {'FINISHED'}

class BetterExperie_OT_MeshFilterCopyCard(bpy.types.Operator):
    bl_idname = "better_experie.mesh_filter_copy_card"
    bl_label = "复制卡片"
    bl_description = "复制当前选中的网格筛选规则卡片"
    card_index: bpy.props.IntProperty()
    def execute(self, context):
        config = context.scene.better_experie_mesh_filter_prop
        src = config.filter_cards[self.card_index]
        new = config.filter_cards.add()
        new.rule_type = src.rule_type
        new.int_min = src.int_min
        new.int_max = src.int_max
        new.float_min = src.float_min
        new.float_max = src.float_max
        new.edge_type = src.edge_type
        new.angle_threshold = src.angle_threshold
        new.str_param = src.str_param
        new.ignore_case = src.ignore_case
        new.use_regex = src.use_regex
        new.use_wildcard = src.use_wildcard
        new.angle_compare = src.angle_compare
        new.angle_value = src.angle_value
        new.invert = src.invert
        config.filter_cards.move(len(config.filter_cards)-1, self.card_index+1)
        return {'FINISHED'}

class BetterExperie_OT_MeshFilterDeleteCard(bpy.types.Operator):
    bl_idname = "better_experie.mesh_filter_delete_card"
    bl_label = "删除卡片"
    bl_description = "删除当前选中的网格筛选规则卡片"
    card_index: bpy.props.IntProperty()
    def execute(self, context):
        config = context.scene.better_experie_mesh_filter_prop
        if len(config.filter_cards) > 1:
            config.filter_cards.remove(self.card_index)
        return {'FINISHED'}

# ========== 主筛选弹窗 ==========
class BetterExperie_OT_MeshFilterBatchSelector(bpy.types.Operator):
    bl_idname = "better_experie.mesh_filter_batch_selector"
    bl_label = "网格高级选择器"
    bl_description = "基于自定义规则批量筛选网格元素（面/边/顶点）"
    bl_options = {'UNDO', 'REGISTER'}

    # 新增：存储边编号的类属性（在 invoke 中赋值，execute 中使用）
    crease_set: set = None
    bevel_set: set = None
    freestyle_set: set = None
    
    def invoke(self, context, event):
        config = context.scene.better_experie_mesh_filter_prop
        if len(config.filter_cards) == 0:
            config.filter_cards.add()
        return context.window_manager.invoke_props_dialog(self, width=520)

    def invoke(self, context, event):
        # 先检查是否处于网格编辑模式
        obj = context.active_object
        if not obj or obj.type != 'MESH' or context.mode != 'EDIT_MESH':
            self.report({'WARNING'}, "请在网格编辑模式使用")
            return {'CANCELLED'}

        # 临时切换到物体模式，读取边属性
        bpy.ops.object.mode_set(mode='OBJECT')
        mesh = obj.data

        crease_attr = mesh.attributes.get("crease_edge")
        bevel_attr = mesh.attributes.get("bevel_weight_edge")
        freestyle_attr = mesh.attributes.get("freestyle_edge")

        # 记录属性值 > 0 的边索引
        self.crease_set = set()
        self.bevel_set = set()
        self.freestyle_set = set()

        if crease_attr:
            for i, data in enumerate(crease_attr.data):
                if data.value > 0:
                    self.crease_set.add(i)

        if bevel_attr:
            for i, data in enumerate(bevel_attr.data):
                if data.value > 0:
                    self.bevel_set.add(i)

        if freestyle_attr:
            # freestyle_edge 通常为布尔属性，value 可能是 0.0 / 1.0 或布尔值
            for i, data in enumerate(freestyle_attr.data):
                val = data.value if hasattr(data, 'value') else 0
                if val > 0:
                    self.freestyle_set.add(i)

        # 记录顶点组索引 → 名称映射，供顶点组规则使用
        self._active_vg_names = [(vg.index, vg.name) for vg in obj.vertex_groups]

        # 切回编辑模式
        bpy.ops.object.mode_set(mode="EDIT")

        # 原有逻辑：添加默认卡片并打开弹窗
        config = context.scene.better_experie_mesh_filter_prop
        if len(config.filter_cards) == 0:
            config.filter_cards.add()
        return context.window_manager.invoke_props_dialog(self, width=520)
        
        
    def draw(self, context):
        layout = self.layout
        config = context.scene.better_experie_mesh_filter_prop

        row = layout.row()
        row.prop(config, "selection_mode", text="")
        row.prop(config, "logic_mode", text="")

        for idx, card in enumerate(config.filter_cards):
            box = layout.box()
            header = box.row(align=True)
            header.prop(card, "invert", text="", icon='ARROW_LEFTRIGHT')
            header.prop(card, "rule_type", text="")
            cp = header.operator("better_experie.mesh_filter_copy_card", icon='COPY_ID', text="")
            cp.card_index = idx
            dl = header.operator("better_experie.mesh_filter_delete_card", icon='X', text="")
            dl.card_index = idx
            self.draw_card(box, card)

        layout.operator("better_experie.mesh_filter_add_card", icon='ADD', text="添加卡片")

    def draw_card(self, layout, card):
        col = layout.column(align=True)
        rule = card.rule_type

        if rule == 'EDGE_LENGTH':
            col.prop(card, "float_min", text="长度≥")
            col.prop(card, "float_max", text="长度≤")
        elif rule == 'FACE_AREA':
            col.prop(card, "float_min", text="面积≥")
            col.prop(card, "float_max", text="面积≤")
        elif rule == 'VERT_EDGE_COUNT':
            col.prop(card, "int_min", text="连接边≥")
            col.prop(card, "int_max", text="连接边≤")
        elif rule == 'FACE_EDGE_COUNT':
            col.prop(card, "int_min", text="面边数≥")
            col.prop(card, "int_max", text="面边数≤")
        elif rule == 'EDGE_TYPE':
            col.prop(card, "edge_type", text="")
        elif rule == 'EDGE_SAME_DIR':
            col.prop(card, "angle_threshold", text="世界角度阈值")
        elif rule == 'EDGE_SAME_UV_DIR':
            col.prop(card, "angle_threshold", text="UV角度阈值")
        elif rule == 'FACE_VIEW_ALIGN':
            col.prop(card, "angle_threshold", text="视口角度阈值")
        elif rule == 'EDGE_FACE_COUNT':
            col.prop(card, "int_min", text="邻面≥")
            col.prop(card, "int_max", text="邻面≤")
        elif rule == 'VERTEX_GROUP':
            col.prop(card, "str_param", text="顶点组关键词")
            col.prop(card, "ignore_case")
            col.prop(card, "use_regex")
            col.prop(card, "use_wildcard")
            if card.use_regex and card.use_wildcard:
                col.label(text="正则与通配符同时开启，通配符优先生效", icon='ERROR')
            col.label(text="点模式选点；边/面模式选全部顶点在组内的元素", icon='INFO')
        elif rule == 'EDGE_ANGLE':
            row = col.row(align=True)
            row.prop(card, "angle_compare", text="")
            row.prop(card, "angle_value", text="")
            
    # ========== 工具：获取边方向向量 ==========
    def get_edge_vector(self, edge):
        v1 = edge.verts[0].co
        v2 = edge.verts[1].co
        return (v2 - v1).normalized()

    def get_edge_uv_vector(self, edge, uv_layer):
        try:
            loops = edge.link_loops
            if not loops:
                return None
            loop = loops[0]
            v1 = edge.verts[0]
            v2 = edge.verts[1]

            uv1 = None
            uv2 = None
            for l in loop.face.loops:
                if l.vert == v1:
                    uv1 = l[uv_layer].uv
                if l.vert == v2:
                    uv2 = l[uv_layer].uv
            if uv1 is None or uv2 is None:
                return None
            vec = (uv2 - uv1).normalized()
            return vec
        except:
            return None
            
    # ========== 工具：向量夹角（角度） ==========
    def vector_angle_deg(self, a, b):
        dot = max(min(a.dot(b), 1.0), -1.0)
        return math.degrees(math.acos(dot))

    # ========== 工具：名称匹配（正则/通配/包含） ==========
    def _name_match(self, text, card):
        import fnmatch
        pattern = card.str_param
        if not pattern:
            return False
        if card.use_wildcard:
            if card.ignore_case:
                return fnmatch.fnmatchcase(text.lower(), pattern.lower())
            return fnmatch.fnmatchcase(text, pattern)
        if card.use_regex:
            import re
            try:
                flags = re.IGNORECASE if card.ignore_case else 0
                return re.search(pattern, text, flags) is not None
            except re.error:
                return False
        if card.ignore_case:
            return pattern.lower() in text.lower()
        return pattern in text

    # ========== 工具：顶点组归属判断（逐点独立） ==========
    def _vert_in_group(self, vert, card, deform_layer):
        """顶点是否属于任意名称匹配的顶点组"""
        if deform_layer is None:
            return False
        for g in vert[deform_layer].items():
            if g is not None:
                group_index, _weight = g
                vg_name = None
                # 通过 bmesh 外的顶点组名查找
                for vg in self._active_vg_names:
                    if vg[0] == group_index:
                        vg_name = vg[1]
                        break
                if vg_name is not None and self._name_match(vg_name, card):
                    return True
        return False
        
    # ========== 筛选核心 ==========
    def match_vert(self, vert, card, deform_layer=None):
        """仅处理顶点规则"""
        rule = card.rule_type
        res = False
        try:
            if rule == 'VERT_EDGE_COUNT':
                cnt = len(vert.link_edges)
                low = min(card.int_min, card.int_max)
                high = max(card.int_min, card.int_max)
                res = (low <= cnt <= high)
            elif rule == 'VERTEX_GROUP':
                res = self._vert_in_group(vert, card, deform_layer)
        except:
            res = False
        if card.invert:
            res = not res
        return res

    def match_edge(self, edge, card, ref_dirs=None, ref_uv_dirs=None, uv_layer=None, view_forward=None, deform_layer=None):
        """仅处理边规则"""
        rule = card.rule_type
        res = False
        try:
            if rule == 'EDGE_LENGTH':
                length = edge.calc_length()
                low = min(card.float_min, card.float_max)
                high = max(card.float_min, card.float_max)
                res = (low <= length <= high)
            elif rule == 'EDGE_FACE_COUNT':
                cnt = len(edge.link_faces)
                low = min(card.int_min, card.int_max)
                high = max(card.int_min, card.int_max)
                res = (low <= cnt <= high)
            elif rule == 'EDGE_ANGLE':
                if len(edge.link_faces) == 2:
                    angle = math.degrees(edge.calc_face_angle())
                    if card.angle_compare == 'LESS':
                        res = (angle <= card.angle_value)
                    else:
                        res = (angle >= card.angle_value)
                else:
                    res = False
            elif rule == 'VERTEX_GROUP':
                # 边模式：所有端点都属于匹配的顶点组
                res = all(self._vert_in_group(v, card, deform_layer) for v in edge.verts)
            elif rule == 'EDGE_TYPE':
                t = card.edge_type
                if t == 'SHARP':
                    res = not edge.smooth
                elif t == 'SMOOTH':
                    res = edge.smooth
                elif t == 'SEAM':
                    res = edge.seam
                elif t == 'BOUNDARY':
                    res = edge.is_boundary
                elif t == 'BEVEL':
                    res = hasattr(self, 'bevel_set') and edge.index in self.bevel_set
                elif t == 'CREASE':
                    res = hasattr(self, 'crease_set') and edge.index in self.crease_set
                elif t == 'FREESTYLE':
                    res = hasattr(self, 'freestyle_set') and edge.index in self.freestyle_set
            elif rule == 'EDGE_SAME_DIR' and ref_dirs is not None:
                e_vec = self.get_edge_vector(edge)
                max_angle = card.angle_threshold
                for r_vec in ref_dirs:
                    ang = self.vector_angle_deg(e_vec, r_vec)
                    if ang <= max_angle or (180 - ang) <= max_angle:
                        res = True
                        break
            elif rule == 'EDGE_SAME_UV_DIR' and ref_uv_dirs is not None and uv_layer is not None:
                e_vec = self.get_edge_uv_vector(edge, uv_layer)
                if e_vec is not None:
                    max_angle = card.angle_threshold
                    for r_vec in ref_uv_dirs:
                        ang = self.vector_angle_deg(e_vec, r_vec)
                        if ang <= max_angle or (180 - ang) <= max_angle:
                            res = True
                            break
        except:
            res = False
        if card.invert:
            res = not res
        return res

    def match_face(self, face, card, view_forward=None, deform_layer=None):
        """仅处理面规则"""
        rule = card.rule_type
        res = False
        try:
            if rule == 'FACE_AREA':
                area = face.calc_area()
                low = min(card.float_min, card.float_max)
                high = max(card.float_min, card.float_max)
                res = (low <= area <= high)
            elif rule == 'FACE_EDGE_COUNT':
                cnt = len(face.edges)
                low = min(card.int_min, card.int_max)
                high = max(card.int_min, card.int_max)
                res = (low <= cnt <= high)
            elif rule == 'VERTEX_GROUP':
                # 面模式：所有顶点都属于匹配的顶点组
                res = all(self._vert_in_group(v, card, deform_layer) for v in face.verts)
            elif rule == 'FACE_VIEW_ALIGN' and view_forward is not None:
                face_normal = face.normal.normalized()
                ang = self.vector_angle_deg(face_normal, -view_forward)
                res = (ang <= card.angle_threshold)
        except:
            res = False
        if card.invert:
            res = not res
        return res

    def evaluate_matches(self, matches, logic_mode):
        if logic_mode == 'AND':
            return all(matches)
        elif logic_mode == 'OR':
            return any(matches)
        elif logic_mode == 'NOT':
            return not any(matches)
        return False
    

    def execute(self, context):
        obj = context.active_object
        if not obj or obj.type != 'MESH' or context.mode != 'EDIT_MESH':
            self.report({'WARNING'}, "请在网格编辑模式使用")
            return {'CANCELLED'}

        orig_mode = context.tool_settings.mesh_select_mode[:]
        config = context.scene.better_experie_mesh_filter_prop
        logic_mode = config.logic_mode
        cards = config.filter_cards

        target_verts = set()
        target_edges = set()
        target_faces = set()

        # 先一次性拿到 bmesh，不反复重建
        bm = bmesh.from_edit_mesh(obj.data)
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        bm.faces.ensure_lookup_table()

        # 获取视口方向
        view_forward = context.space_data.region_3d.view_rotation @ mathutils.Vector((0, 0, -1))
        view_forward.normalize()

        # 获取活动UV
        uv_layer = bm.loops.layers.uv.active
        if not uv_layer:
            uv_layer = None

        # 获取顶点组层
        deform_layer = bm.verts.layers.deform.active
        
        # 预先获取已选中边的方向
        ref_edges = [e for e in bm.edges if e.select]
        ref_dirs = [self.get_edge_vector(e) for e in ref_edges]

        # UV参考方向
        ref_uv_dirs = []
        if uv_layer is not None:
            for e in ref_edges:
                vec = self.get_edge_uv_vector(e, uv_layer)
                if vec:
                    ref_uv_dirs.append(vec)
                
        # 统一判断所有点
        for v in bm.verts:
            matches = [self.match_vert(v, c, deform_layer) for c in cards]
            if self.evaluate_matches(matches, logic_mode):
                target_verts.add(v.index)

        # 统一判断所有边
        for e in bm.edges:
            matches = [self.match_edge(e, c, ref_dirs, ref_uv_dirs, uv_layer, view_forward, deform_layer) for c in cards]
            if self.evaluate_matches(matches, logic_mode):
                target_edges.add(e.index)

        # 统一判断所有面
        for f in bm.faces:
            matches = [self.match_face(f, c, view_forward, deform_layer) for c in cards]
            if self.evaluate_matches(matches, logic_mode):
                target_faces.add(f.index)

        # 应用选择
        sel_mode = config.selection_mode

        # 将 BMesh 选择模式限定为当前用户模式，避免跨域传播
        select_modes = set()
        if orig_mode[0]:
            select_modes.add('VERT')
        if orig_mode[1]:
            select_modes.add('EDGE')
        if orig_mode[2]:
            select_modes.add('FACE')
        # bm.select_mode 不允许空值，回退到顶点模式
        bm.select_mode = select_modes if select_modes else {'VERT'}

        if sel_mode == 'SET_SELECTION':
            # 先全部取消选择
            for v in bm.verts: v.select = False
            for e in bm.edges: e.select = False
            for f in bm.faces: f.select = False

        if sel_mode in {'SET_SELECTION', 'ADD_TO_SELECTION'}:
            # 只在目标元素自身域上设置选择，不手动选中子元素
            for i in target_verts:
                bm.verts[i].select = True
            for i in target_edges:
                bm.edges[i].select = True
            for i in target_faces:
                bm.faces[i].select = True

        elif sel_mode == 'REMOVE_FROM_SELECTION':
            for i in target_verts: bm.verts[i].select = False
            for i in target_edges: bm.edges[i].select = False
            for i in target_faces: bm.faces[i].select = False

        # 按当前选择模式同步底层选择（关键修复）
        # 不再手动选中子元素，也不使用 select_flush(True) 的顶点域向上传播，
        # 避免"目标边顶点恰好覆盖整张面"时把其余边/面误选
        bm.select_flush_mode()
        bmesh.update_edit_mesh(obj.data)

        # 恢复用户原本的模式
        context.tool_settings.mesh_select_mode = orig_mode

        self.report({'INFO'}, f"选中：{len(target_verts)}点 {len(target_edges)}边 {len(target_faces)}面")
        return {'FINISHED'}

        
        
# ========== 菜单 ==========
# def mesh_filter_draw(self, context):
    # layout = self.layout
    # layout.separator(type="LINE")
    # layout.operator("better_experie.mesh_filter_batch_selector", text="筛选式选取", icon='FILTER')

# ========== 注册 ==========
classes = (
    BetterExperie_MeshFilterCardItem,
    BetterExperie_MeshFilterConfig,
    BetterExperie_OT_MeshFilterAddCard,
    BetterExperie_OT_MeshFilterCopyCard,
    BetterExperie_OT_MeshFilterDeleteCard,
    BetterExperie_OT_MeshFilterBatchSelector,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.better_experie_mesh_filter_prop = bpy.props.PointerProperty(type=BetterExperie_MeshFilterConfig)
    # bpy.types.VIEW3D_MT_select_edit_mesh.append(mesh_filter_draw)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.better_experie_mesh_filter_prop
    # bpy.types.VIEW3D_MT_select_edit_mesh.remove(mesh_filter_draw)

if __name__ == "__main__":
    register()