# 边组工具

import bpy
import bmesh
import time
import numpy as np
import gpu
from gpu_extras.batch import batch_for_shader
from bpy.app.handlers import persistent

from ...addon_prefs import quick_group_tools_enabled

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

def get_attribute_index(mesh, name):
    """属性在 mesh.attributes 里的下标；找不到返回 -1。"""
    for index, attribute in enumerate(mesh.attributes):
        if attribute.name == name:
            return index
    return -1

def unique_attribute_name(mesh, base):
    """属性名在 mesh.attributes 里全局唯一，重名时自己加 .001。

    bmesh 建层遇到跨域同名会静默丢弃该层（既不报错也不自动加 .001），
    所以建层前必须先把名字算好，不能指望 Blender 兜底。
    """
    existing = {attribute.name for attribute in mesh.attributes}
    if base not in existing:
        return base
    index = 1
    while f"{base}.{index:03d}" in existing:
        index += 1
    return f"{base}.{index:03d}"

def get_active_edge_group_index(context, mesh):
    """当前边组在 mesh.attributes 里的下标；没有边组时返回 -1。

    template_list 的 active index 是「原始集合下标」，不是过滤后列表的行号，
    所以这里全程用 mesh.attributes 的下标。

    又因为 mesh.attributes 的下标会随进出编辑模式整体前移
    （实测编辑模式建的两个组从 12/13 变成 0/1），光存下标会在切模式后指错，
    所以再记一个名字：下标对不上就按名字把选中的组找回来。
    """
    window_manager = context.window_manager
    count = len(mesh.attributes)
    if count == 0:
        return -1

    index = max(0, min(window_manager.better_experie_edge_groups_active_index, count - 1))
    attribute = mesh.attributes[index]
    if is_edge_group_attribute(attribute):
        if window_manager.better_experie_edge_group_active_name != attribute.name:
            window_manager.better_experie_edge_group_active_name = attribute.name
        return index

    # 下标失效（切模式、删属性后整体前移、或别的插件改了列表）：按记住的名字找回
    remembered = window_manager.better_experie_edge_group_active_name
    if remembered:
        for fallback, item in enumerate(mesh.attributes):
            if item.name == remembered and is_edge_group_attribute(item):
                window_manager.better_experie_edge_groups_active_index = fallback
                return fallback

    # 名字也没了（组被删/被改名）：退到第一个边组
    for fallback, attribute in enumerate(mesh.attributes):
        if is_edge_group_attribute(attribute):
            window_manager.better_experie_edge_groups_active_index = fallback
            window_manager.better_experie_edge_group_active_name = attribute.name
            return fallback
    return -1

def get_active_edge_group(context, mesh):
    """获取当前活动边组属性。"""
    index = get_active_edge_group_index(context, mesh)
    if index < 0:
        return None
    attribute = mesh.attributes[index]
    return attribute if is_edge_group_attribute(attribute) else None

def set_active_edge_group_index(context, mesh, index):
    """设置当前活动边组索引（mesh.attributes 下标），越界时夹回有效范围。"""
    window_manager = context.window_manager
    count = len(mesh.attributes)
    index = 0 if count == 0 else max(0, min(index, count - 1))
    window_manager.better_experie_edge_groups_active_index = index

    attribute = mesh.attributes[index] if count else None
    window_manager.better_experie_edge_group_active_name = (
        attribute.name if attribute is not None and is_edge_group_attribute(attribute) else "")

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
        # 4.2 没有 bitflag_item_never_show，退回 0（不设过滤位即不显示）
        hidden = getattr(self, "bitflag_item_never_show", 0)
        for attribute in mesh.attributes:
            if is_edge_group_attribute(attribute):
                flags.append(self.bitflag_filter_item)
            else:
                flags.append(hidden)
        return flags, order

    def draw_item(self, context, layout, _data, item, _icon, _active_data, _active_propname, index):
        row = layout.row(align=True)
        if context.mode == 'EDIT_MESH' and quick_group_tools_enabled():
            # 行内按钮：选择（只选/Shift 加选/Ctrl 弃选）与保存选集（加入/覆盖/移除）
            select_button = row.operator("better_experie.edge_group_select", text="", emboss=False, icon='RESTRICT_SELECT_OFF')
            select_button.index = index
            save_button = row.operator("better_experie.edge_group_quick_assign", text="", emboss=False, icon='IMPORT')
            save_button.index = index
            save_button.weight = context.window_manager.better_experie_edge_group_weight
            row.separator()
            
        row.prop(item, "name", text="", emboss=False, icon='EDGESEL')

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
        base_name = self.name.strip() or EDGE_GROUP_DEFAULT_NAME
        attribute_name = unique_attribute_name(mesh, base_name)
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

        attribute_index = get_attribute_index(mesh, attribute_name)
        set_active_edge_group_index(context, mesh, attribute_index if attribute_index >= 0 else 0)

        if attribute_name != base_name:
            self.report({'INFO'}, f"名称【{base_name}】已被占用，边组新建为【{attribute_name}】")
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
        if group_index < 0:
            self.report({'WARNING'}, "没有可删除的边组")
            return {'CANCELLED'}
        attribute = mesh.attributes[group_index]

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

        # 删除后优先选原位置之后的第一个边组，没有就退回最后一个
        remaining = [
            index for index, item in enumerate(mesh.attributes)
            if is_edge_group_attribute(item)
        ]
        if remaining:
            next_index = next((index for index in remaining if index >= group_index), remaining[-1])
        else:
            next_index = 0
        set_active_edge_group_index(context, mesh, next_index)
        self.report({'INFO'}, f"已删除边组【{attribute_name}】")
        return {'FINISHED'}


# ------------------------------------------------------------------------
# 编辑模式：分配 / 移除 / 选择
# ------------------------------------------------------------------------
def write_edge_weights(bm, layer, weight, state):
    """把权重写进边组：加入 / 覆盖 / 移除，返回 (写入数, 清零数)"""
    written = 0
    cleared = 0
    for edge in bm.edges:
        if state == 'REMOVE':
            if edge.select and edge[layer] > EDGE_GROUP_MEMBER_THRESHOLD:
                edge[layer] = 0.0
                cleared += 1
            continue
        if edge.select:
            edge[layer] = weight
            written += 1
        elif state == 'REPLACE' and edge[layer] > EDGE_GROUP_MEMBER_THRESHOLD:
            edge[layer] = 0.0
            cleared += 1
    return written, cleared


def report_edge_weights(operator, name, weight, state, written, cleared):
    if state == 'REMOVE':
        if cleared:
            operator.report({'INFO'}, f"已从【{name}】移除 {cleared} 条边")
        else:
            operator.report({'INFO'}, f"选中的边本来就不在【{name}】里")
    elif state == 'REPLACE':
        operator.report({'INFO'},
                        f"已覆盖【{name}】：{written} 条写入权重 "
                        f"{weight:.3f}，{cleared} 条清零")
    elif written:
        operator.report({'INFO'}, f"已向 {written} 条边分配权重 {weight:.3f}")
    else:
        operator.report({'INFO'}, "没有选中的边")


class BetterExperie_OT_EdgeGroupAssign(bpy.types.Operator):
    bl_idname = "better_experie.edge_group_assign"
    bl_description = "将 Weight 写入选中的边；点击=加入，Shift+点击=覆盖，Ctrl+点击=移除"
    bl_label = "分配"
    bl_options = {'REGISTER', 'UNDO'}

    weight: bpy.props.FloatProperty(
        name="Weight",description="写入当前选中边的权重",
        default=1.0,min=0.0,max=1.0)

    state: bpy.props.EnumProperty(
        name="分配方式",
        items=[
            ('ADD', "加入", "把选中的边加入该边组"),
            ('REPLACE', "覆盖", "写入选中的边，未选中的边清零"),
            ('REMOVE', "移除", "把选中的边移出该边组"),
        ],
        default='ADD',
    )

    def invoke(self, context, event):
        # 面板按钮点击时 event 由 window->runtime->eventstate 补上
        if event is not None:
            if getattr(event, "ctrl", False):
                self.state = 'REMOVE'
            elif getattr(event, "shift", False):
                self.state = 'REPLACE'
            else:
                self.state = 'ADD'
        return self.execute(context)

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

        written, cleared = write_edge_weights(bm, layer, self.weight, self.state)
        bmesh.update_edit_mesh(mesh,loop_triangles=False,destructive=False)
        report_edge_weights(self, attribute.name, self.weight, self.state, written, cleared)
        return {'FINISHED'}


class BetterExperie_OT_EdgeGroupQuickAssign(bpy.types.Operator):
    bl_idname = "better_experie.edge_group_quick_assign"
    bl_label = "保存选集到边组"
    bl_description = "左键点击：将选中项加入该边组（加入）\nShift+左键点击：以选中项作为该边组（覆盖）\nCtrl+左键点击：在边组中移出选中项（移除）"
    bl_options = {'REGISTER', 'UNDO'}

    index: bpy.props.IntProperty(
        name="边组下标",
        description="列表行下标；-1 表示当前活动边组",
        default=-1,
    )
    weight: bpy.props.FloatProperty(
        name="Weight", description="写入选中边的权重",
        default=1.0, min=0.0, max=1.0)
    state: bpy.props.EnumProperty(
        name="保存方式",
        items=[
            ('ADD', "加入", "把选中的边加入该边组"),
            ('REPLACE', "覆盖", "写入选中的边，未选中的边清零"),
            ('REMOVE', "移除", "把选中的边移出该边组"),
        ],
        default='ADD',
    )

    @classmethod
    def poll(cls, context):
        obj = get_active_mesh_object(context)
        return obj is not None and obj.mode == 'EDIT'

    def invoke(self, context, event):
        if self.index >= 0 and event is not None:
            if getattr(event, "ctrl", False):
                self.state = 'REMOVE'
            elif getattr(event, "shift", False):
                self.state = 'REPLACE'
            else:
                self.state = 'ADD'
        return self.execute(context)

    def execute(self, context):
        obj = get_active_mesh_object(context)
        if obj is None or obj.mode != 'EDIT':
            self.report({'WARNING'}, "请在网格编辑模式下执行此操作")
            return {'CANCELLED'}

        mesh = obj.data
        if not 0 <= self.index < len(mesh.attributes):
            self.report({'WARNING'}, "该边组已不存在，请刷新列表后重试")
            return {'CANCELLED'}

        attribute = mesh.attributes[self.index]
        if not is_edge_group_attribute(attribute):
            self.report({'WARNING'}, f"【{attribute.name}】不是边组")
            return {'CANCELLED'}
        set_active_edge_group_index(context, mesh, self.index)

        bm, layer = get_edit_float_layer(mesh, attribute.name)
        if layer is None:
            self.report({'ERROR'}, "未找到边组数据层")
            return {'CANCELLED'}

        written, cleared = write_edge_weights(bm, layer, self.weight, self.state)
        bmesh.update_edit_mesh(mesh,loop_triangles=False,destructive=False)
        report_edge_weights(self, attribute.name, self.weight, self.state, written, cleared)
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

        cleared = 0
        selected = 0
        for edge in bm.edges:
            if not edge.select:
                continue
            selected += 1
            if edge[layer] > EDGE_GROUP_MEMBER_THRESHOLD:
                edge[layer] = 0.0
                cleared += 1

        bmesh.update_edit_mesh(mesh,loop_triangles=False,destructive=False)

        if selected == 0:
            self.report({'INFO'}, "没有选中的边")
        elif cleared == 0:
            self.report({'INFO'}, f"选中的边本来就不在【{attribute.name}】里")
        else:
            self.report({'INFO'}, f"已从【{attribute.name}】移除 {cleared} 条边")
        return {'FINISHED'}

def apply_selection_by_edges(bm, members, state):
    """按边集合改选择状态（只动边，端点由边自动带上）。

    三个坑都实测过：
    1. bm.select_flush() 会把「两端点都已选中」的额外边也选上（6 条变 7 条）；
    2. 写 face.select = True 会连带选中该面的所有边，所以只在「该面所有边已选中」时才补面；
    3. 写 face.select = False 会连带取消该面的所有边，所以弃选时先记下要保留的边，
       清完面再恢复，否则已选中的边会被一起清掉。
    """
    if state == 'REPLACE':
        for vert in bm.verts:
            vert.select = False
        for edge in bm.edges:
            edge.select = False
        for face in bm.faces:
            face.select = False

    member_set = set(members)
    if state == 'REMOVE':
        affected_faces = {face for edge in members for face in edge.link_faces}
        doomed = [face for face in affected_faces
                  if face.select and any(edge in member_set for edge in face.edges)]
        # 写 face.select = False 会把该面的边一起取消，所以先记下要保留的边
        keep_edges = [edge for edge in bm.edges if edge.select and edge not in member_set]
        for face in doomed:
            face.select = False
        for edge in keep_edges:
            edge.select = True
        for edge in members:
            edge.select = False
        for face in affected_faces:
            if not face.select and all(edge.select for edge in face.edges):
                face.select = True
        return

    # edge.select = True 本身会把端点带上，不需要再手点顶点
    for edge in members:
        edge.select = True

    # 只补「所有边都选中」的面：这样不会带出多余边；
    # 反过来写 face.select = False 会把该面的边一起取消，所以永远不写 False
    for face in {face for edge in members for face in edge.link_faces}:
        if not face.select and all(edge.select for edge in face.edges):
            face.select = True


class BetterExperie_OT_EdgeGroupSelect(bpy.types.Operator):
    bl_idname = "better_experie.edge_group_select"
    bl_label = "选择边组"
    bl_description = "左键点击：添加该边组的边到选中项（加入）\nShift+左键点击：以该边组的边设为选中项（覆盖）\nCtrl+左键点击：从选中项中取消选中该边组的边（移除）"
    bl_options = {'REGISTER', 'UNDO'}

    index: bpy.props.IntProperty(
        name="边组下标",
        description="列表行下标；-1 表示当前活动边组",
        default=-1,
    )
    state: bpy.props.EnumProperty(
        name="选择方式",
        items=[
            ('REPLACE', "只选", "清空其它选择，只保留该边组的边"),
            ('ADD', "加选", "把该边组的边加入当前选择"),
            ('REMOVE', "弃选", "从当前选择里去掉该边组的边"),
        ],
        default='ADD',
    )

    @classmethod
    def poll(cls, context):
        obj = get_active_mesh_object(context)
        return obj is not None and obj.mode == 'EDIT'

    def invoke(self, context, event):
        # 只有列表行按钮（index >= 0）才用修饰键决定方式；
        # 面板按钮（index = -1）沿用按钮上写死的 state，语义与原生顶点组面板一致
        if self.index >= 0 and event is not None:
            if getattr(event, "ctrl", False):
                self.state = 'REMOVE'
            elif getattr(event, "shift", False):
                self.state = 'REPLACE'
            else:
                self.state = 'ADD'
        return self.execute(context)

    def execute(self, context):
        obj = get_active_mesh_object(context)
        if obj is None or obj.mode != 'EDIT':
            self.report({'WARNING'}, "请在网格编辑模式下执行此操作")
            return {'CANCELLED'}

        mesh = obj.data
        attribute = self._resolve_attribute(context, mesh)
        if attribute is None:
            return {'CANCELLED'}

        bm, layer = get_edit_float_layer(mesh, attribute.name)
        if layer is None:
            self.report({'ERROR'}, "未找到边组数据层")
            return {'CANCELLED'}

        members = [edge for edge in bm.edges if edge[layer] > EDGE_GROUP_MEMBER_THRESHOLD]

        apply_selection_by_edges(bm, members, self.state)

        bmesh.update_edit_mesh(mesh, loop_triangles=False, destructive=False)

        if not members:
            self.report({'INFO'}, f"边组【{attribute.name}】里没有已分配的边")
            return {'FINISHED'}

        action = {'REPLACE': "只选", 'ADD': "加选", 'REMOVE': "弃选"}[self.state]
        self.report({'INFO'}, f"{action} {len(members)} 条边（{attribute.name}）")
        return {'FINISHED'}

    def _resolve_attribute(self, context, mesh):
        """index >= 0 时取该行边组并设为活动组；-1 时取活动组"""
        if self.index < 0:
            attribute = get_active_edge_group(context, mesh)
            if attribute is None:
                self.report({'WARNING'}, "请先创建或选择一个边组")
            return attribute

        if self.index >= len(mesh.attributes):
            self.report({'WARNING'}, "该边组已不存在，请刷新列表后重试")
            return None

        attribute = mesh.attributes[self.index]
        if not is_edge_group_attribute(attribute):
            self.report({'WARNING'}, f"【{attribute.name}】不是边组")
            return None

        set_active_edge_group_index(context, mesh, self.index)
        return attribute


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

        members = [edge for edge in bm.edges if edge[layer] > EDGE_GROUP_MEMBER_THRESHOLD]
        apply_selection_by_edges(bm, members, 'REMOVE')

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

        # 读一次活动边组：索引若失效（切模式 / 删改属性导致整体前移）会在这里顺手修正，
        # 保证列表高亮和实际操作的是同一个边组
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
            panel_select = row.operator("better_experie.edge_group_select", text="选择")
            panel_select.index = -1
            panel_select.state = 'ADD'
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
    BetterExperie_OT_EdgeGroupQuickAssign,
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
    bpy.types.WindowManager.better_experie_edge_group_active_name = bpy.props.StringProperty(
        name="活动边组名称",description="记住选中的边组名，属性下标失效时据此恢复",default="")
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
    if hasattr(bpy.types.WindowManager, "better_experie_edge_group_active_name"):
        del bpy.types.WindowManager.better_experie_edge_group_active_name

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
