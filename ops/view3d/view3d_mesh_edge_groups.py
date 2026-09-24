# 边组工具

import bpy
import bmesh
import time
import numpy as np
import gpu
from gpu_extras.batch import batch_for_shader
from bpy.app.handlers import persistent

# ------------------------------------------------------------------------
# 常量
# ------------------------------------------------------------------------

EDGE_GROUP_DEFAULT_NAME = "Edge Group"
EDGE_GROUP_MEMBER_THRESHOLD = 0.0

EDGE_GROUP_PREVIEW_DURATION = 1.5
EDGE_GROUP_PREVIEW_LINE_WIDTH = 5.0
EDGE_GROUP_PREVIEW_COLOR = (0.05, 1.0, 0.35, 1.0)


# ------------------------------------------------------------------------
# GPU 预览状态
# ------------------------------------------------------------------------
_edge_preview_state = {
    "handler": None,
    "coords": None,
    "alpha": 1.0,
    "start_time": 0.0,
}

_edge_preview_shader = None

# ------------------------------------------------------------------------
# 工具函数
# ------------------------------------------------------------------------
def get_active_mesh_object(context):
    """获取当前活动网格对象。"""
    obj = context.object
    if obj and obj.type == 'MESH':
        return obj
    return None

def is_edge_group_attribute(attribute):
    """
    边组定义：
    - Domain：EDGE
    - Data Type：FLOAT
    """
    return (attribute.domain == 'EDGE' and attribute.data_type == 'FLOAT')

def get_edge_group_attributes(mesh):
    """获取网格内所有 EDGE + FLOAT 属性。"""
    return [attribute for attribute in mesh.attributes if is_edge_group_attribute(attribute)]

def get_active_edge_group_index(context, mesh):
    """获取安全的当前边组索引。"""
    groups = get_edge_group_attributes(mesh)
    if not groups:
        return 0
    index = context.window_manager.better_experie_edge_groups_active_index
    return max(0, min(index, len(groups) - 1))

def get_active_edge_group(context, mesh):
    """获取当前活动边组属性。"""
    groups = get_edge_group_attributes(mesh)
    if not groups:
        return None
    index = get_active_edge_group_index(context, mesh)
    return groups[index]

def set_active_edge_group_index(context, index):
    """设置当前活动边组索引。"""
    context.window_manager.better_experie_edge_groups_active_index = max(0, index)

def get_edit_float_layer(mesh, attribute_name):
    """获取编辑模式 BMesh 中的边 Float Layer。"""
    bm = bmesh.from_edit_mesh(mesh)
    layer = bm.edges.layers.float.get(attribute_name)
    return bm, layer

# ------------------------------------------------------------------------
# GPU 边线预览
# ------------------------------------------------------------------------
def _tag_redraw_all_3dviews():
    """请求所有 3D View 重绘。"""
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()

def _remove_edge_preview_handler():
    """清理预览 Draw Handler 与缓存数据。"""
    handler = _edge_preview_state.get("handler")
    if handler is not None:
        try:
            bpy.types.SpaceView3D.draw_handler_remove(handler,'WINDOW')
        except (ValueError, ReferenceError):
            pass

    _edge_preview_state["handler"] = None
    _edge_preview_state["coords"] = None
    _edge_preview_state["alpha"] = 1.0
    _edge_preview_state["start_time"] = 0.0


def _is_view3d_xray_enabled():
    """
    检查当前存在的 3D 视图是否开启 X-Ray。

    找到第一个 VIEW_3D 后直接读取其 shading.show_xray。
    """
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                space = area.spaces.active
                return space.shading.show_xray
    return False


def _draw_edge_preview():
    """
    GPU 绘制回调。

    使用 UNIFORM_COLOR + LINES 画高亮边线。
    依据视口 X-Ray 状态切换深度检测。
    """
    coords = _edge_preview_state.get("coords")
    alpha = _edge_preview_state.get("alpha", 0.0)
    if coords is None or len(coords) == 0 or alpha <= 0.0:
        return

    global _edge_preview_shader

    try:
        if _edge_preview_shader is None:
            _edge_preview_shader = gpu.shader.from_builtin('UNIFORM_COLOR')

        shader = _edge_preview_shader

        batch = batch_for_shader(shader,'LINES',{"pos": coords},)
        color = (EDGE_GROUP_PREVIEW_COLOR[0],EDGE_GROUP_PREVIEW_COLOR[1], EDGE_GROUP_PREVIEW_COLOR[2],alpha,)
        gpu.state.blend_set('ALPHA')

        if _is_view3d_xray_enabled():
            gpu.state.depth_test_set('NONE')
        else:
            gpu.state.depth_test_set('LESS_EQUAL')
        gpu.state.line_width_set(EDGE_GROUP_PREVIEW_LINE_WIDTH)

        shader.bind()
        shader.uniform_float("color", color)
        batch.draw(shader)

    except ReferenceError:
        pass

    except Exception:
        import traceback
        traceback.print_exc()

    finally:
        gpu.state.line_width_set(1.0)
        gpu.state.blend_set('NONE')
        gpu.state.depth_test_set('LESS_EQUAL')

def _edge_preview_fade_timer():
    """更新透明度并在预览结束后清理。"""
    try:
        if _edge_preview_state.get("handler") is None:
            return None

        elapsed = time.time() - _edge_preview_state["start_time"]
        if elapsed >= EDGE_GROUP_PREVIEW_DURATION:
            _remove_edge_preview_handler()
            _tag_redraw_all_3dviews()
            return None

        _edge_preview_state["alpha"] = max(0.0,1.0 - elapsed / EDGE_GROUP_PREVIEW_DURATION,)
        _tag_redraw_all_3dviews()
        return 0.03

    except Exception:
        import traceback
        traceback.print_exc()
        _remove_edge_preview_handler()
        return None


@persistent
def _cleanup_edge_preview_on_load(dummy):
    """加载新文件时回收残留的预览 handler 与 timer。"""
    _remove_edge_preview_handler()
    if bpy.app.timers.is_registered(_edge_preview_fade_timer):
        bpy.app.timers.unregister(_edge_preview_fade_timer)


def _collect_edge_group_preview_coords(context, use_deformed=False):
    """
    收集当前活动边组中 Weight > 0 的边线坐标。

    参数：
    - use_deformed：True 时读取修改器堆栈后的求值网格。

    返回：
    - NumPy float32 坐标数组，形状为 (edge_count * 2, 3)
    - 没有可预览边时返回 None
    """
    obj = get_active_mesh_object(context)
    if obj is None:
        return None

    mesh = obj.data
    attribute = get_active_edge_group(context, mesh)
    if attribute is None:
        return None

    matrix_world = obj.matrix_world
    coords = []
    if obj.mode == 'EDIT':
        bm, layer = get_edit_float_layer(mesh, attribute.name)
        if layer is None:
            return None

        for edge in bm.edges:
            if edge[layer] > EDGE_GROUP_MEMBER_THRESHOLD:
                coords.append(matrix_world @ edge.verts[0].co.copy())
                coords.append(matrix_world @ edge.verts[1].co.copy())
    elif use_deformed:
        depsgraph = context.evaluated_depsgraph_get()
        eval_obj = obj.evaluated_get(depsgraph)
        eval_mesh = eval_obj.data
        world = eval_obj.matrix_world
        eval_attribute = eval_mesh.attributes.get(attribute.name)
        if eval_attribute is None or not is_edge_group_attribute(eval_attribute):
            return None

        for edge in eval_mesh.edges:
            if eval_attribute.data[edge.index].value > EDGE_GROUP_MEMBER_THRESHOLD:
                vertex_a = eval_mesh.vertices[edge.vertices[0]]
                vertex_b = eval_mesh.vertices[edge.vertices[1]]

                coords.append(world @ vertex_a.co)
                coords.append(world @ vertex_b.co)
    else:
        for edge in mesh.edges:
            edge_weight = attribute.data[edge.index].value

            if edge_weight > EDGE_GROUP_MEMBER_THRESHOLD:
                vertex_a = mesh.vertices[edge.vertices[0]]
                vertex_b = mesh.vertices[edge.vertices[1]]

                coords.append(matrix_world @ vertex_a.co)
                coords.append(matrix_world @ vertex_b.co)

    if not coords:
        return None
    return np.asarray(coords, dtype=np.float32)

# ------------------------------------------------------------------------
# UI 列表
# ------------------------------------------------------------------------
class BETTER_EXPERIE_UL_edge_groups(bpy.types.UIList):
    """只显示 EDGE 域 FLOAT 类型属性。"""
    def filter_items(self, _context, mesh, _property):
        flags = []
        order = list(range(len(mesh.attributes)))
        for attribute in mesh.attributes:
            if is_edge_group_attribute(attribute):
                flags.append(self.bitflag_filter_item)
            else:
                flags.append(self.bitflag_item_never_show)
        return flags, order

    def draw_item(self,_context,layout,_data,item,_icon,_active_data,_active_propname,_index):
        layout.prop(item,"name",text="",emboss=False,icon='EDGESEL')

# ------------------------------------------------------------------------
# 新增 / 删除边组
# ------------------------------------------------------------------------

class BetterExperie_OT_EdgeGroupAdd(bpy.types.Operator):
    bl_idname = "better_experie.edge_group_add"
    bl_description = "添加 Edge 域 Float 属性"
    bl_label = "新增边组"
    bl_options = {'REGISTER', 'UNDO'}

    name: bpy.props.StringProperty(name="名称",default=EDGE_GROUP_DEFAULT_NAME)

    def execute(self, context):
        obj = get_active_mesh_object(context)
        if obj is None:
            self.report({'WARNING'}, "请先选择一个网格对象")
            return {'CANCELLED'}

        mesh = obj.data
        attribute_name = self.name.strip() or EDGE_GROUP_DEFAULT_NAME
        if obj.mode == 'EDIT':
            bm = bmesh.from_edit_mesh(mesh)
            layer = bm.edges.layers.float.new(attribute_name)
            attribute_name = layer.name
            for edge in bm.edges:
                edge[layer] = 0.0
            bmesh.update_edit_mesh(mesh,loop_triangles=False,destructive=False)
        else:
            attribute = mesh.attributes.new(name=attribute_name,type='FLOAT',domain='EDGE')
            attribute_name = attribute.name
        groups = get_edge_group_attributes(mesh)

        new_index = next(
            (
                index
                for index, attribute in enumerate(groups)
                if attribute.name == attribute_name
            ),max(0, len(groups) - 1),)

        set_active_edge_group_index(context, new_index)
        return {'FINISHED'}


class BetterExperie_OT_EdgeGroupRemove(bpy.types.Operator):
    bl_idname = "better_experie.edge_group_remove"
    bl_description = "删除当前 Edge 域 Float 属性"
    bl_label = "删除边组"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = get_active_mesh_object(context)
        if obj is None:
            self.report({'WARNING'}, "请先选择一个网格对象")
            return {'CANCELLED'}

        mesh = obj.data
        group_index = get_active_edge_group_index(context, mesh)
        attribute = get_active_edge_group(context, mesh)
        if attribute is None:
            self.report({'WARNING'}, "没有可删除的边组")
            return {'CANCELLED'}

        attribute_name = attribute.name
        if obj.mode == 'EDIT':
            bm = bmesh.from_edit_mesh(mesh)
            layer = bm.edges.layers.float.get(attribute_name)
            if layer is None:
                self.report({'ERROR'},"找不到当前边组的 Float 数据层。")
                return {'CANCELLED'}

            bm.edges.layers.float.remove(layer)
            bmesh.update_edit_mesh(mesh,loop_triangles=False,destructive=False)

        else:
            mesh.attributes.remove(attribute)

        groups = get_edge_group_attributes(mesh)
        set_active_edge_group_index(context,min(group_index, max(0, len(groups) - 1)))
        return {'FINISHED'}


# ------------------------------------------------------------------------
# 编辑模式：分配 / 移除 / 选择
# ------------------------------------------------------------------------
class BetterExperie_OT_EdgeGroupAssign(bpy.types.Operator):
    bl_idname = "better_experie.edge_group_assign"
    bl_description = "将 Weight 写入选中的边"
    bl_label = "分配"
    bl_options = {'REGISTER', 'UNDO'}

    weight: bpy.props.FloatProperty(
        name="Weight",description="写入当前选中边的权重",
        default=1.0,min=0.0,max=1.0)

    def execute(self, context):
        obj = get_active_mesh_object(context)
        if obj is None or obj.mode != 'EDIT':
            self.report({'WARNING'}, "请在网格编辑模式下执行此操作")
            return {'CANCELLED'}

        mesh = obj.data
        attribute = get_active_edge_group(context, mesh)
        if attribute is None:
            self.report({'WARNING'}, "请先创建或选择一个边组")
            return {'CANCELLED'}

        bm, layer = get_edit_float_layer(mesh, attribute.name)
        if layer is None:
            self.report({'ERROR'}, "未找到边组数据层")
            return {'CANCELLED'}

        selected_count = 0
        for edge in bm.edges:
            if edge.select:
                edge[layer] = self.weight
                selected_count += 1

        bmesh.update_edit_mesh(mesh,loop_triangles=False,destructive=False)

        if selected_count == 0:
            self.report({'INFO'}, "没有选中的边")
        else:
            self.report({'INFO'},f"已向 {selected_count} 条边分配权重 {self.weight:.3f}")
        return {'FINISHED'}

class BetterExperie_OT_EdgeGroupRemoveFrom(bpy.types.Operator):
    bl_idname = "better_experie.edge_group_remove_from"
    bl_description = "将选中边的 Weight 清零"
    bl_label = "移除"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = get_active_mesh_object(context)
        if obj is None or obj.mode != 'EDIT':
            self.report({'WARNING'}, "请在网格编辑模式下执行此操作")
            return {'CANCELLED'}

        mesh = obj.data
        attribute = get_active_edge_group(context, mesh)
        if attribute is None:
            self.report({'WARNING'}, "请先创建或选择一个边组")
            return {'CANCELLED'}

        bm, layer = get_edit_float_layer(mesh, attribute.name)
        if layer is None:
            self.report({'ERROR'}, "未找到边组数据层")
            return {'CANCELLED'}

        for edge in bm.edges:
            if edge.select:
                edge[layer] = 0.0

        bmesh.update_edit_mesh(mesh,loop_triangles=False,destructive=False)
        return {'FINISHED'}

class BetterExperie_OT_EdgeGroupSelect(bpy.types.Operator):
    bl_idname = "better_experie.edge_group_select"
    bl_description = "选择当前边组中 Weight 大于零的边"
    bl_label = "选择"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = get_active_mesh_object(context)
        if obj is None or obj.mode != 'EDIT':
            self.report({'WARNING'}, "请在网格编辑模式下执行此操作")
            return {'CANCELLED'}

        mesh = obj.data
        attribute = get_active_edge_group(context, mesh)
        if attribute is None:
            self.report({'WARNING'}, "请先创建或选择一个边组")
            return {'CANCELLED'}

        bm, layer = get_edit_float_layer(mesh, attribute.name)
        if layer is None:
            self.report({'ERROR'}, "未找到边组数据层")
            return {'CANCELLED'}

        for edge in bm.edges:
            if edge[layer] > EDGE_GROUP_MEMBER_THRESHOLD:
                edge.select = True

        bmesh.update_edit_mesh(mesh,loop_triangles=False,destructive=False)
        return {'FINISHED'}


class BetterExperie_OT_EdgeGroupDeselect(bpy.types.Operator):
    bl_idname = "better_experie.edge_group_deselect"
    bl_description = "取消选择当前边组中 Weight 大于零的边"
    bl_label = "取消选择"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = get_active_mesh_object(context)
        if obj is None or obj.mode != 'EDIT':
            self.report({'WARNING'}, "请在网格编辑模式下执行此操作")
            return {'CANCELLED'}

        mesh = obj.data
        attribute = get_active_edge_group(context, mesh)
        if attribute is None:
            self.report({'WARNING'}, "请先创建或选择一个边组")
            return {'CANCELLED'}

        bm, layer = get_edit_float_layer(mesh, attribute.name)
        if layer is None:
            self.report({'ERROR'}, "未找到边组数据层")
            return {'CANCELLED'}

        for edge in bm.edges:
            if edge[layer] > EDGE_GROUP_MEMBER_THRESHOLD:
                edge.select = False

        bmesh.update_edit_mesh(mesh,loop_triangles=False,destructive=False)
        return {'FINISHED'}

# ------------------------------------------------------------------------
# 边组预览
# ------------------------------------------------------------------------
class BetterExperie_OT_EdgeGroupPreview(bpy.types.Operator):
    bl_idname = "better_experie.edge_group_preview"
    bl_description = "高亮显示当前边组的边线，并在短暂显示后渐隐；Ctrl+点击显示修改器堆栈后的边线"
    bl_label = "预览边线"
    bl_options = {'REGISTER'}

    use_deformed: bpy.props.BoolProperty(default=False)

    @classmethod
    def poll(cls, context):
        return get_active_mesh_object(context) is not None

    def invoke(self, context, event):
        self.use_deformed = bool(event.ctrl)
        return self.execute(context)

    def execute(self, context):
        obj = get_active_mesh_object(context)
        if obj is None:
            self.report({'WARNING'}, "请先选择一个网格对象")
            return {'CANCELLED'}

        attribute = get_active_edge_group(context, obj.data)
        if attribute is None:
            self.report({'WARNING'}, "请先创建或选择一个边组")
            return {'CANCELLED'}

        coords = _collect_edge_group_preview_coords(context, self.use_deformed)
        if coords is None or len(coords) == 0:
            self.report({'WARNING'},"没有可预览边：请确认边已分配 Weight，且 Weight 大于 0。",)
            return {'CANCELLED'}

        edge_count = len(coords) // 2

        # 若此前预览尚未结束，则清理旧预览。
        _remove_edge_preview_handler()

        _edge_preview_state["coords"] = coords
        _edge_preview_state["alpha"] = 1.0
        _edge_preview_state["start_time"] = time.time()

        _edge_preview_state["handler"] = (
            bpy.types.SpaceView3D.draw_handler_add(_draw_edge_preview,(),'WINDOW','POST_VIEW'))

        if not bpy.app.timers.is_registered(_edge_preview_fade_timer):
            bpy.app.timers.register(_edge_preview_fade_timer)
        _tag_redraw_all_3dviews()
        self.report({'INFO'}, f"正在预览 {edge_count} 条边")
        return {'FINISHED'}

# ------------------------------------------------------------------------
# 面板
# ------------------------------------------------------------------------
class BETTER_EXPERIE_PT_edge_groups(bpy.types.Panel):
    bl_label = "边组"
    bl_idname = "BETTER_EXPERIE_PT_edge_groups"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "data"

    @classmethod
    def poll(cls, context):
        obj = context.object
        return obj is not None and obj.type == 'MESH'

    def draw(self, context):
        layout = self.layout
        obj = context.object
        mesh = obj.data
        window_manager = context.window_manager
        active_group = get_active_edge_group(context, mesh)

        row = layout.row()
        list_column = row.column()
        list_column.template_list(
            "BETTER_EXPERIE_UL_edge_groups",
            "better_experie_edge_groups",
            mesh,
            "attributes",
            window_manager,
            "better_experie_edge_groups_active_index",
            rows=5,
        )

        buttons = row.column(align=True)
        buttons.operator("better_experie.edge_group_add", icon='ADD', text="")
        buttons.operator("better_experie.edge_group_remove", icon='REMOVE', text="")

        if active_group is None:
            return

        if obj.mode == 'EDIT':
            row = layout.row(align=True)
            assign_operator = row.operator("better_experie.edge_group_assign",text="分配")
            assign_operator.weight = window_manager.better_experie_edge_group_weight
            row.operator("better_experie.edge_group_remove_from",text="移除",)
            row.separator()
            row.operator("better_experie.edge_group_select", text="选择")
            row.operator("better_experie.edge_group_deselect", text="取消选择")
        
            layout.use_property_split = True
            layout.use_property_decorate = False
            layout.prop(window_manager,"better_experie_edge_group_weight",text="Weight",)
                    
        layout.operator("better_experie.edge_group_preview",text="预览边线",icon='RESTRICT_VIEW_OFF')


# ------------------------------------------------------------------------
# 注册
# ------------------------------------------------------------------------

classes = (
    BETTER_EXPERIE_UL_edge_groups,
    BetterExperie_OT_EdgeGroupAdd,
    BetterExperie_OT_EdgeGroupRemove,
    BetterExperie_OT_EdgeGroupAssign,
    BetterExperie_OT_EdgeGroupRemoveFrom,
    BetterExperie_OT_EdgeGroupSelect,
    BetterExperie_OT_EdgeGroupDeselect,
    BetterExperie_OT_EdgeGroupPreview,
    BETTER_EXPERIE_PT_edge_groups,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    bpy.types.WindowManager.better_experie_edge_groups_active_index = bpy.props.IntProperty(
        name="活动边组索引",default=0,min=0)
    bpy.types.WindowManager.better_experie_edge_group_weight = bpy.props.FloatProperty(
        name="Edge Group Weight",description="分配给选中边的边组权重",default=1.0,min=0.0,max=1.0)

    if _cleanup_edge_preview_on_load not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(_cleanup_edge_preview_on_load)


def unregister():
    _remove_edge_preview_handler()
    if bpy.app.timers.is_registered(_edge_preview_fade_timer):
        bpy.app.timers.unregister(_edge_preview_fade_timer)

    if _cleanup_edge_preview_on_load in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_cleanup_edge_preview_on_load)

    if hasattr(bpy.types.WindowManager, "better_experie_edge_group_weight"):
        del bpy.types.WindowManager.better_experie_edge_group_weight
    if hasattr(bpy.types.WindowManager, "better_experie_edge_groups_active_index"):
        del bpy.types.WindowManager.better_experie_edge_groups_active_index

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
