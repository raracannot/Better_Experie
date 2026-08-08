# 物体染色工具：清理/随机/集合色/父级色/顶点数量染色
# 独立面板注册到属性编辑器物体属性页签 (PROPERTIES / WINDOW / object)

import bpy
import random
import mathutils

COLOR_LIB = {
    'COLOR_01': (0.7530, 0.1170, 0.1046, 1.0),  # 红
    'COLOR_02': (0.8714, 0.3613, 0.0908, 1.0),  # 橙
    'COLOR_03': (0.8714, 0.7084, 0.0908, 1.0),  # 黄
    'COLOR_04': (0.1946, 0.5972, 0.1946, 1.0),  # 绿
    'COLOR_05': (0.1095, 0.4621, 0.8148, 1.0),  # 蓝
    'COLOR_06': (0.2623, 0.0999, 0.6939, 1.0),  # 紫
    'COLOR_07': (0.5583, 0.1683, 0.4735, 1.0),  # 粉
    'COLOR_08': (0.1912, 0.0887, 0.0529, 1.0),  # 棕
    'NONE': (0.6514, 0.6514, 0.6514, 1.0),  # 灰
}

def _resolve_targets(self, context):
    """按修饰键确定目标物体：无=所有选中，Shift=视图层全部"""
    if self.target_scope == 'ALL':
        return list(context.view_layer.objects)
    return list(context.selected_objects)

def _read_scope(self, event):
    if event.shift:
        self.target_scope = 'ALL'
    else:
        self.target_scope = 'SELECTED'

def _get_vertex_count(obj):
    data = getattr(obj, 'data', None)
    if data is None:
        return None
    if hasattr(data, 'vertices'):
        return len(data.vertices)
    if hasattr(data, 'splines'):
        count = 0
        for spline in data.splines:
            if hasattr(spline, 'points'):
                count += len(spline.points)
            if hasattr(spline, 'bezier_points'):
                count += len(spline.bezier_points)
        return count
    if hasattr(data, 'points'):
        return len(data.points)
    if hasattr(data, 'elements'):
        return len(data.elements)
    return None

def _get_volume_box(obj):
    if obj.dimensions:
        d = obj.dimensions
        return d[0] * d[1] * d[2]
    return None

def _mix_colors(c1, c2, ratio):
    return (
        c1[0] * (1 - ratio) + c2[0] * ratio,
        c1[1] * (1 - ratio) + c2[1] * ratio,
        c1[2] * (1 - ratio) + c2[2] * ratio,
        1.0,
    )

base_description="\n[左键]点击:为所有选中物体染色\n[Shift+左键]点击:为视图层全部物体染色"

class BetterExperie_OT_ObjectColorClear(bpy.types.Operator):
    bl_idname = "better_experie.object_color_clear"
    bl_label = "清理颜色"
    bl_description = "还原物体颜色为默认色" + base_description
    bl_options = {'REGISTER', 'UNDO'}

    target_scope: bpy.props.EnumProperty(
        items=[('SELECTED', "选中", ""), ('ALL', "全部", "")],
        default='SELECTED', options={'HIDDEN'})

    def invoke(self, context, event):
        _read_scope(self, event)
        return self.execute(context)

    def execute(self, context):
        targets = _resolve_targets(self, context)
        for obj in targets:
            obj.color = (1.0, 1.0, 1.0, 1.0)
        self.report({'INFO'}, f"已清理 {len(targets)} 个物体颜色")
        return {'FINISHED'}


class BetterExperie_OT_ObjectColorRandom(bpy.types.Operator):
    bl_idname = "better_experie.object_color_random"
    bl_label = "随机颜色"
    bl_description = "随机为物体着色" + base_description
    bl_options = {'REGISTER', 'UNDO'}

    target_scope: bpy.props.EnumProperty(
        items=[('SELECTED', "选中", ""), ('ALL', "全部", "")],
        default='SELECTED', options={'HIDDEN'})
    color_count: bpy.props.IntProperty(
        name="颜色数量", description="0表示每个物体一个颜色；大于0表示在N个颜色的色卡中随机挑选",
        default=0, min=0, max=1000)
    hue_only: bpy.props.BoolProperty(
        name="仅色相随机", description="启用时颜色在HSV的H等距排布，S和V为1，实现亮纯色随机",
        default=True)

    def draw(self, context):
        layout = self.layout
        col = layout.column(align=True)
        col.prop(self, "color_count")
        col.prop(self, "hue_only")


    def invoke(self, context, event):
        _read_scope(self, event)
        return context.window_manager.invoke_props_dialog(self, width=300)

    def execute(self, context):
        targets = _resolve_targets(self, context)
        if not targets:
            return {'CANCELLED'}

        if self.hue_only:
            n = self.color_count if self.color_count > 0 else len(targets)
            for i, obj in enumerate(targets):
                h = i / n if n > 0 else 0.0
                c = mathutils.Color()
                c.hsv = (h % 1.0, 1.0, 1.0)
                obj.color = (c.r, c.g, c.b, 1.0)
        else:
            if self.color_count > 0:
                palette = []
                for _ in range(self.color_count):
                    c = mathutils.Color((random.random(), random.random(), random.random()))
                    palette.append((c.r, c.g, c.b, 1.0))
                for obj in targets:
                    obj.color = random.choice(palette)
            else:
                for obj in targets:
                    c = mathutils.Color((random.random(), random.random(), random.random()))
                    obj.color = (c.r, c.g, c.b, 1.0)

        self.report({'INFO'}, f"已为 {len(targets)} 个物体随机着色")
        return {'FINISHED'}


class BetterExperie_OT_ObjectColorCollection(bpy.types.Operator):
    bl_idname = "better_experie.object_color_collection"
    bl_label = "设集合色"
    bl_description = "将物体颜色设为所在集合的颜色" + base_description
    bl_options = {'REGISTER', 'UNDO'}

    target_scope: bpy.props.EnumProperty(
        items=[('SELECTED', "选中", ""), ('ALL', "全部", "")],
        default='SELECTED', options={'HIDDEN'})

    def invoke(self, context, event):
        _read_scope(self, event)
        return self.execute(context)

    def execute(self, context):
        targets = _resolve_targets(self, context)
        count = 0
        for obj in targets:
            if obj.users_collection:
                collection = obj.users_collection[0]
                obj.color = COLOR_LIB.get(collection.color_tag, COLOR_LIB['NONE'])
                count += 1
        self.report({'INFO'}, f"已设置 {count} 个物体的集合色")
        return {'FINISHED'}


class BetterExperie_OT_ObjectColorParent(bpy.types.Operator):
    bl_idname = "better_experie.object_color_parent"
    bl_label = "设父级色"
    bl_description = "为顶层父级随机高饱和颜色，子级逐级降低饱和度" + base_description
    bl_options = {'REGISTER', 'UNDO'}

    target_scope: bpy.props.EnumProperty(
        items=[('SELECTED', "选中", ""), ('ALL', "全部", "")],
        default='SELECTED', options={'HIDDEN'})
    optimize_display: bpy.props.BoolProperty(
        name="优化显示", description="勾选时步长自动依据每个顶层父级的最大子级层数计算，顶层为1、底层为0.4",
        default=True)

    # 内参
    _base_saturation = 1.0
    _step = 0.05
    _min_ratio = 0.4

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "optimize_display")

    def invoke(self, context, event):
        _read_scope(self, event)
        return context.window_manager.invoke_props_dialog(self, width=360)

    def execute(self, context):
        targets = _resolve_targets(self, context)
        if not targets:
            return {'CANCELLED'}

        # 找出所有顶层父级
        roots = set()
        for obj in targets:
            root = obj
            while root.parent:
                root = root.parent
            roots.add(root)

        for root in roots:
            hue = random.random()

            # 计算该顶层父级的最大子级层数（顶层深度0）
            if self.optimize_display:
                max_depth = 0
                queue_d = [(root, 0)]
                visited_d = {root}
                while queue_d:
                    node, depth = queue_d.pop(0)
                    max_depth = max(max_depth, depth)
                    for child in node.children:
                        if child not in visited_d:
                            visited_d.add(child)
                            queue_d.append((child, depth + 1))
                # 顶层=1.0，底层=0.4，按最大层数均分
                step = (self._base_saturation - self._base_saturation * self._min_ratio) / max_depth if max_depth > 0 else 0
            else:
                step = self._step

            # BFS 遍历子树，逐级降饱和
            queue = [(root, 0)]
            visited = {root}
            while queue:
                node, depth = queue.pop(0)
                sat = self._base_saturation - step * depth
                min_sat = self._base_saturation * self._min_ratio
                sat = max(sat, min_sat)
                c = mathutils.Color()
                c.hsv = (hue, sat, 1.0)
                node.color = (c.r, c.g, c.b, 1.0)
                for child in node.children:
                    if child not in visited:
                        visited.add(child)
                        queue.append((child, depth + 1))

        self.report({'INFO'}, f"已按 {len(roots)} 个父级层级染色")
        return {'FINISHED'}


class BetterExperie_OT_ObjectColorVertexCount(bpy.types.Operator):
    bl_idname = "better_experie.object_color_vertex_count"
    bl_label = "顶点数量染色"
    bl_description = "根据顶点数量或密度为物体着色（支持网格与曲线）" + base_description
    bl_options = {'REGISTER', 'UNDO'}

    target_scope: bpy.props.EnumProperty(
        items=[('SELECTED', "选中", ""), ('ALL', "全部", "")],
        default='SELECTED', options={'HIDDEN'})
    metric: bpy.props.EnumProperty(
        name="着色依据",
        items=[
            ('COUNT', "顶点数量", "按顶点总数着色"),
            ('DENSITY', "顶点密度", "按顶点数/体积着色"),
        ],
        default='COUNT')
    max_color: bpy.props.FloatVectorProperty(
        name="最大色", subtype='COLOR', size=4, min=0.0, max=1.0,
        default=(1.0, 0.0, 0.0, 1.0))
    min_color: bpy.props.FloatVectorProperty(
        name="最小色", subtype='COLOR', size=4, min=0.0, max=1.0,
        default=(1.0, 1.0, 1.0, 1.0))
    optimize_sort: bpy.props.BoolProperty(
        name="优化排序", description="启用时根据排序序号染色，否则根据真实比例染色",
        default=True)

    def draw(self, context):
        layout = self.layout
        col = layout.column(align=True)
        col.prop(self, "metric", text="")
        col.separator()
        row = col.row(align=True)
        row.prop(self, "max_color", text="最大")
        row.prop(self, "min_color", text="最小")
        col.prop(self, "optimize_sort")

    def invoke(self, context, event):
        _read_scope(self, event)
        return context.window_manager.invoke_props_dialog(self, width=320)

    def execute(self, context):
        targets = _resolve_targets(self, context)

        valid = []
        for obj in targets:
            vertex = _get_vertex_count(obj)
            if vertex is None or vertex <= 0:
                continue
            if self.metric == 'DENSITY':
                volume = _get_volume_box(obj)
                if volume is None or volume <= 0:
                    continue
                value = vertex / volume
            else:
                value = vertex
            valid.append((obj, value))

        if not valid:
            self.report({'WARNING'}, "没有符合条件的网格/曲线物体")
            return {'CANCELLED'}

        if self.optimize_sort:
            valid.sort(key=lambda x: x[1])
            n = len(valid)
            for i, (obj, _) in enumerate(valid):
                ratio = i / (n - 1) if n > 1 else 0
                obj.color = _mix_colors(self.min_color, self.max_color, ratio)
        else:
            values = [v for _, v in valid]
            mn, mx = min(values), max(values)
            for obj, value in valid:
                ratio = (value - mn) / (mx - mn) if mx > mn else 0
                obj.color = _mix_colors(self.min_color, self.max_color, ratio)

        self.report({'INFO'}, f"已按顶点{'密度' if self.metric == 'DENSITY' else '数量'}为 {len(valid)} 个物体染色")
        return {'FINISHED'}


# ═══════════════════════════════════════════════════════════════
# 面板：属性编辑器 → 物体属性页签
# ═══════════════════════════════════════════════════════════════

class BETTER_EXPERIE_PT_object_dye_tool(bpy.types.Panel):
    bl_label = "物体染色工具"
    bl_idname = "BETTER_EXPERIE_PT_object_dye_tool"
    bl_space_type = 'PROPERTIES'
    bl_options = {'DEFAULT_CLOSED'}
    bl_region_type = 'WINDOW'
    bl_context = "object"
    bl_parent_id = "OBJECT_PT_display"
    
    @classmethod
    def poll(cls, context):
        return context.active_object is not None

    def draw(self, context):
        obj = context.active_object
        if not obj:
            return
        layout = self.layout
        # layout.prop(obj,"color",text="")
        col = layout.column(align=True)
        row = col.row(align=True)
        row.operator("better_experie.object_color_clear", text="清理颜色", icon='X')
        row.operator("better_experie.object_color_random", text="随机颜色", icon='SHADERFX')
        row = col.row(align=True)
        row.operator("better_experie.object_color_collection", text="设集合色", icon='OUTLINER_COLLECTION')
        row.operator("better_experie.object_color_parent", text="设父级色", icon='BONE_DATA')
        # col.separator()
        layout.operator("better_experie.object_color_vertex_count", text="顶点数量染色", icon='MESH_DATA')
 
classes = (
    BetterExperie_OT_ObjectColorClear,
    BetterExperie_OT_ObjectColorRandom,
    BetterExperie_OT_ObjectColorCollection,
    BetterExperie_OT_ObjectColorParent,
    BetterExperie_OT_ObjectColorVertexCount,
    BETTER_EXPERIE_PT_object_dye_tool,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
