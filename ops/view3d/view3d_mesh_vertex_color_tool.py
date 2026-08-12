# 顶点颜色面板优化

import bpy
import bmesh
import math
import time
import numpy as np
import gpu
from gpu_extras.batch import batch_for_shader


class BetterExperie_VertexColorSettings(bpy.types.PropertyGroup):
    color: bpy.props.FloatVectorProperty(
        name="颜色",
        subtype='COLOR',
        size=4,
        min=0.0, max=1.0,
        default=(1.0, 1.0, 1.0, 1.0),
        description="要应用的颜色"
    )

    blend_mode: bpy.props.EnumProperty(
        name="混合模式",
        description="颜色应用的混合方式",
        items=[
            ('REPLACE', "替换", "直接替换为新颜色"),
            ('ADD', "添加", "与原颜色相加"),
            ('SUBTRACT', "减去", "从原颜色中减去"),
            ('MULTIPLY', "相乘", "与原颜色相乘"),
            ('LIGHTEN', "变亮", "保留两者中较亮的值"),
            ('DARKEN', "变暗", "保留两者中较暗的值"),
        ],
        default='REPLACE'
    )

    threshold: bpy.props.FloatProperty(
        name="阈值",
        description="颜色匹配的容差阈值（0为完全一致，越大越宽松）",
        default=0.2,
        min=0.0, max=2.0
    )


def _blend_color(old_c, new_c, mode):
    if mode == 'REPLACE':
        return new_c

    res = [0.0, 0.0, 0.0, 0.0]
    for i in range(4):
        if mode == 'ADD':
            res[i] = min(old_c[i] + new_c[i], 1.0)
        elif mode == 'SUBTRACT':
            res[i] = max(old_c[i] - new_c[i], 0.0)
        elif mode == 'MULTIPLY':
            res[i] = old_c[i] * new_c[i]
        elif mode == 'LIGHTEN':
            res[i] = max(old_c[i], new_c[i])
        elif mode == 'DARKEN':
            res[i] = min(old_c[i], new_c[i])
    return tuple(res)


def _color_distance(c1, c2):
    return math.sqrt((c1[0] - c2[0]) ** 2 + (c1[1] - c2[1]) ** 2 + (c1[2] - c2[2]) ** 2)


# ═══════════════════════════════════════════════════════════════
# 预览顶点颜色（GPU 高亮预览，参考 预览顶点组 的渐隐贴片实现）
# ═══════════════════════════════════════════════════════════════

_preview_state = {
    "handler": None,
    "coords_np": None,
    "colors_np": None,
    "alpha": 1.0,
    "start_time": 0,
}

_gpu_buf = {
    "idx_seq": None,
    "n_coords": 0,
}

_ANGLES = np.array([i * math.pi / 4.0 for i in range(8)], dtype=np.float32)
_COS_A = np.cos(_ANGLES)
_SIN_A = np.sin(_ANGLES)


def _get_or_build_idx_seq(n_coords):
    if _gpu_buf["n_coords"] == n_coords and _gpu_buf["idx_seq"] is not None:
        return _gpu_buf["idx_seq"]

    count = n_coords * 8 * 3
    idx = np.empty(count, dtype=np.int32)
    off = 0
    for i in range(n_coords):
        center = i * 9
        for j in range(8):
            p1 = center + 1 + j
            p2 = center + 1 + (j + 1) % 8
            idx[off] = center
            idx[off + 1] = p1
            idx[off + 2] = p2
            off += 3

    _gpu_buf["idx_seq"] = idx
    _gpu_buf["n_coords"] = n_coords
    return idx


def _find_rv3d():
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                return area.spaces.active.region_3d
    return None


def _draw_callback_px():
    coords_np = _preview_state.get("coords_np")
    colors_np = _preview_state.get("colors_np")
    if coords_np is None or colors_np is None or _preview_state["alpha"] <= 0:
        return

    rv3d = _find_rv3d()
    if not rv3d:
        return

    try:
        view_inv = rv3d.view_matrix.inverted()
        cam_right = np.array(view_inv.col[0].to_3d().normalized(), dtype=np.float32)
        cam_up = np.array(view_inv.col[1].to_3d().normalized(), dtype=np.float32)
        cam_pos = np.array(view_inv.translation, dtype=np.float32)

        n = len(coords_np)
        if rv3d.is_perspective:
            radii = np.linalg.norm(coords_np - cam_pos, axis=1, keepdims=True) * 0.002
        else:
            radii = np.full((n, 1), rv3d.view_distance * 0.002, dtype=np.float32)

        total = n * 9
        all_verts = np.empty((total, 3), dtype=np.float32)
        all_verts[0::9] = coords_np
        all_colors = np.empty((total, 4), dtype=np.float32)
        all_colors[0::9] = colors_np

        for i in range(8):
            direction = cam_right * _COS_A[i] + cam_up * _SIN_A[i]
            all_verts[i + 1::9] = coords_np + direction * radii
            all_colors[i + 1::9] = colors_np

        all_colors[:, 3] = _preview_state["alpha"]

        idx_seq = _get_or_build_idx_seq(n)
        shader = gpu.shader.from_builtin('SMOOTH_COLOR')
        batch = batch_for_shader(
            shader, 'TRIS',
            {"pos": all_verts, "color": all_colors},
            indices=idx_seq)

        is_xray = False
        if bpy.context.space_data and bpy.context.space_data.type == 'VIEW_3D':
            is_xray = bpy.context.space_data.shading.show_xray

        gpu.state.blend_set('ALPHA')
        if is_xray:
            gpu.state.depth_test_set('NONE')
        else:
            gpu.state.depth_test_set('LESS_EQUAL')

        shader.bind()
        batch.draw(shader)
    except ReferenceError:
        pass
    except Exception:
        import traceback
        traceback.print_exc()
    finally:
        gpu.state.blend_set('NONE')
        gpu.state.depth_test_set('LESS_EQUAL')


def _timer_fade_out():
    elapsed = time.time() - _preview_state["start_time"]

    if elapsed > 1.0:
        _remove_draw_handler()
        _tag_redraw_all_3dviews()
        return None

    _preview_state["alpha"] = 1.0 - elapsed
    _tag_redraw_all_3dviews()
    return 0.03


def _remove_draw_handler():
    if _preview_state["handler"]:
        bpy.types.SpaceView3D.draw_handler_remove(_preview_state["handler"], 'WINDOW')
        _preview_state["handler"] = None
        _preview_state["coords_np"] = None
        _preview_state["colors_np"] = None

    _gpu_buf["idx_seq"] = None
    _gpu_buf["n_coords"] = 0


def _tag_redraw_all_3dviews():
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()


def _collect_vertex_colors(obj, context):
    """收集全部顶点的世界坐标及其顶点色，返回 (coords, colors) 或 None"""
    mesh = obj.data
    active_color = mesh.color_attributes.active_color
    if not active_color:
        return None

    matrix_world = obj.matrix_world
    layer_name = active_color.name
    domain = active_color.domain

    coords = []
    colors = []

    if context.mode == 'EDIT_MESH':
        bm = bmesh.from_edit_mesh(mesh)
        if domain == 'POINT':
            color_layer = bm.verts.layers.color.get(layer_name)
            if color_layer is None:
                color_layer = bm.verts.layers.float_color.get(layer_name)
            if color_layer is None:
                return None
            for v in bm.verts:
                coords.append(matrix_world @ v.co.copy())
                colors.append(tuple(v[color_layer]))
        else:  # CORNER：取每个顶点的首个拐角颜色作为代表色
            color_layer = bm.loops.layers.color.get(layer_name)
            if color_layer is None:
                color_layer = bm.loops.layers.float_color.get(layer_name)
            if color_layer is None:
                return None
            vert_color_map = {}
            for face in bm.faces:
                for loop in face.loops:
                    vi = loop.vert.index
                    if vi not in vert_color_map:
                        vert_color_map[vi] = tuple(loop[color_layer])
            for v in bm.verts:
                if v.index in vert_color_map:
                    coords.append(matrix_world @ v.co.copy())
                    colors.append(vert_color_map[v.index])
    else:
        if domain == 'POINT':
            for i, v in enumerate(mesh.vertices):
                coords.append(matrix_world @ v.co.copy())
                colors.append(tuple(active_color.data[i].color))
        else:  # CORNER：取每个顶点的首个拐角颜色作为代表色
            vert_color_map = {}
            loops = mesh.loops
            for li, loop in enumerate(loops):
                vi = loop.vertex_index
                if vi not in vert_color_map:
                    vert_color_map[vi] = tuple(active_color.data[li].color)
            for v in mesh.vertices:
                if v.index in vert_color_map:
                    coords.append(matrix_world @ v.co.copy())
                    colors.append(vert_color_map[v.index])

    if not coords:
        return None
    return coords, colors


class BetterExperie_OT_PreviewVertexColor(bpy.types.Operator):
    bl_idname = "better_experie.preview_vertex_color"
    bl_label = "快速预览"
    bl_description = "在3D视图中按顶点色高亮显示全部顶点（1秒渐隐）"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj and obj.type == 'MESH'

    def execute(self, context):
        obj = context.active_object
        if not obj or obj.type != 'MESH':
            return {'CANCELLED'}

        result = _collect_vertex_colors(obj, context)
        if result is None:
            self.report({'INFO'}, "没有活动的颜色属性层")
            return {'CANCELLED'}

        coords, colors = result
        _remove_draw_handler()
        _preview_state["coords_np"] = np.array(coords, dtype=np.float32)
        _preview_state["colors_np"] = np.array(colors, dtype=np.float32)
        _preview_state["alpha"] = 1.0
        _preview_state["start_time"] = time.time()

        _preview_state["handler"] = bpy.types.SpaceView3D.draw_handler_add(
            _draw_callback_px, (), 'WINDOW', 'POST_VIEW'
        )

        if not bpy.app.timers.is_registered(_timer_fade_out):
            bpy.app.timers.register(_timer_fade_out)

        _tag_redraw_all_3dviews()
        return {'FINISHED'}


class BetterExperie_OT_MeshApplyVertexColor(bpy.types.Operator):
    bl_idname = "better_experie.mesh_apply_vertex_color"
    bl_label = "应用顶点颜色"
    bl_description = "将颜色应用到顶点"
    bl_options = {'REGISTER', 'UNDO'}

    only_selected: bpy.props.BoolProperty(
        name="仅应用所选",
        description="如果为True，则仅应用到选中的顶点；否则应用到全部",
        default=False
    )

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return (obj and obj.type == 'MESH' and context.mode == 'EDIT_MESH' and obj.data.color_attributes.active_color)

    def execute(self, context):
        obj = context.active_object
        mesh = obj.data
        settings = context.scene.better_experie_vertex_color_settings
        target_color = settings.color
        blend_mode = settings.blend_mode

        active_color_attr = mesh.color_attributes.active_color
        if not active_color_attr:
            self.report({'WARNING'}, "没有活动的颜色属性层！")
            return {'CANCELLED'}

        domain = active_color_attr.domain
        layer_name = active_color_attr.name

        bm = bmesh.from_edit_mesh(mesh)

        if domain == 'CORNER':
            color_layer = bm.loops.layers.color.get(layer_name)
            if not color_layer:
                self.report({'WARNING'}, "无法获取面拐角颜色层！")
                return {'CANCELLED'}

            for face in bm.faces:
                for loop in face.loops:
                    if not self.only_selected or loop.vert.select:
                        old_color = loop[color_layer]
                        loop[color_layer] = _blend_color(old_color, target_color, blend_mode)

        elif domain == 'POINT':
            color_layer = bm.verts.layers.color.get(layer_name)
            if not color_layer:
                color_layer = bm.verts.layers.float_color.get(layer_name)

            if not color_layer:
                self.report({'WARNING'}, "无法获取顶点颜色层！")
                return {'CANCELLED'}

            for vert in bm.verts:
                if not self.only_selected or vert.select:
                    old_color = vert[color_layer]
                    vert[color_layer] = _blend_color(old_color, target_color, blend_mode)
        else:
            self.report({'WARNING'}, f"不支持的颜色属性域: {domain}")
            return {'CANCELLED'}

        bmesh.update_edit_mesh(mesh)
        return {'FINISHED'}


class BetterExperie_OT_MeshSelectSimilarVertexColor(bpy.types.Operator):
    bl_idname = "better_experie.mesh_select_similar_vertex_color"
    bl_label = "选中相似颜色"
    bl_description = "选中颜色与当前设定颜色相近的顶点"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return (obj and obj.type == 'MESH' and context.mode == 'EDIT_MESH' and obj.data.color_attributes.active_color)

    def execute(self, context):
        obj = context.active_object
        mesh = obj.data
        settings = context.scene.better_experie_vertex_color_settings
        target_color = settings.color
        threshold = settings.threshold

        active_color_attr = mesh.color_attributes.active_color
        if not active_color_attr:
            self.report({'WARNING'}, "没有活动的颜色属性层！")
            return {'CANCELLED'}

        domain = active_color_attr.domain
        layer_name = active_color_attr.name

        # 强制切换到点模式，在点模式完成选取计算更稳定
        tool_settings = context.tool_settings
        original_select_mode = tuple(tool_settings.mesh_select_mode)
        tool_settings.mesh_select_mode = (True, True, True)

        bm = bmesh.from_edit_mesh(mesh)

        for v in bm.verts:
            v.select = False
        for e in bm.edges:
            e.select = False
        for f in bm.faces:
            f.select = False

        try:
            if domain == 'CORNER':
                color_layer = bm.loops.layers.color.get(layer_name)
                if not color_layer:
                    color_layer = bm.loops.layers.float_color.get(layer_name)

                if not color_layer:
                    self.report({'WARNING'}, "无法获取面拐角颜色层！")
                    return {'CANCELLED'}

                for face in bm.faces:
                    for loop in face.loops:
                        loop_color = loop[color_layer]
                        if _color_distance(loop_color, target_color) <= threshold:
                            loop.vert.select = True

            elif domain == 'POINT':
                color_layer = bm.verts.layers.color.get(layer_name)
                if not color_layer:
                    color_layer = bm.verts.layers.float_color.get(layer_name)

                if not color_layer:
                    self.report({'WARNING'}, "无法获取顶点颜色层！")
                    return {'CANCELLED'}

                for vert in bm.verts:
                    vert_color = vert[color_layer]
                    if _color_distance(vert_color, target_color) <= threshold:
                        vert.select = True

            bm.select_flush_mode()
        finally:
            # 选取完成后，还原至原始模式
            tool_settings.mesh_select_mode = original_select_mode
            bmesh.update_edit_mesh(mesh)
        return {'FINISHED'}


def draw_vertex_color_tool(self, context):
    if context.mode != 'EDIT_MESH':
        return

    layout = self.layout
    settings = context.scene.better_experie_vertex_color_settings

    box = layout.box()
    row = box.row(align=True)
    row.prop(settings, "color", text="")
    row.prop(settings, "blend_mode", text="")
    row.separator()
    row.prop(settings, "threshold", text="阈值")

    row = box.row(align=True)
    op_all = row.operator("better_experie.mesh_apply_vertex_color", text="写入全部", icon='SNAP_FACE')
    op_all.only_selected = False
    op_sel = row.operator("better_experie.mesh_apply_vertex_color", text="写入所选", icon='SNAP_FACE_CENTER')
    op_sel.only_selected = True
    row.separator()
    row.operator("better_experie.mesh_select_similar_vertex_color", text="选中颜色", icon='RESTRICT_SELECT_OFF')
    row.separator()
    row.operator("better_experie.preview_vertex_color", text="预览顶点色", icon='RESTRICT_VIEW_OFF')


classes = (
    BetterExperie_VertexColorSettings,
    BetterExperie_OT_MeshApplyVertexColor,
    BetterExperie_OT_MeshSelectSimilarVertexColor,
    BetterExperie_OT_PreviewVertexColor,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.better_experie_vertex_color_settings = bpy.props.PointerProperty(type=BetterExperie_VertexColorSettings)
    bpy.types.DATA_PT_vertex_colors.append(draw_vertex_color_tool)


def unregister():
    bpy.types.DATA_PT_vertex_colors.remove(draw_vertex_color_tool)
    _remove_draw_handler()
    if bpy.app.timers.is_registered(_timer_fade_out):
        bpy.app.timers.unregister(_timer_fade_out)
    del bpy.types.Scene.better_experie_vertex_color_settings
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
