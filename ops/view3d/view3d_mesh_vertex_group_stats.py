# 顶点组面板优化

import bpy
import bmesh
import gpu
from gpu_extras.batch import batch_for_shader
import numpy as np
import time
import math
from bpy.app.handlers import persistent

_stats_cache = {}

_preview_state = {
    "handler": None,
    "batch": None,
    "alpha": 1.0,
    "start_time": 0,
    "coords_np": None,
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


@persistent
def _clear_vg_cache_on_depsgraph(scene, depsgraph):
    for update in depsgraph.updates:
        if isinstance(update.id, bpy.types.Object) and update.id.type == 'MESH':
            if update.is_updated_geometry:
                _stats_cache.pop(update.id.name, None)


@persistent
def _cleanup_on_load(dummy):
    _remove_draw_handler()
    if bpy.app.timers.is_registered(_timer_fade_out):
        bpy.app.timers.unregister(_timer_fade_out)
    _stats_cache.clear()


def _find_rv3d():
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                return area.spaces.active.region_3d
    return None


def _draw_callback_px():
    coords_np = _preview_state.get("coords_np")
    if coords_np is None or _preview_state["alpha"] <= 0:
        return

    rv3d = _find_rv3d()
    if not rv3d:
        return

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

    for i in range(8):
        direction = cam_right * _COS_A[i] + cam_up * _SIN_A[i]
        all_verts[i + 1::9] = coords_np + direction * radii

    idx_seq = _get_or_build_idx_seq(n)
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    batch = batch_for_shader(shader, 'TRIS', {"pos": all_verts}, indices=idx_seq)

    is_xray = False
    if bpy.context.space_data and bpy.context.space_data.type == 'VIEW_3D':
        is_xray = bpy.context.space_data.shading.show_xray

    gpu.state.blend_set('ALPHA')
    if is_xray:
        gpu.state.depth_test_set('NONE')
    else:
        gpu.state.depth_test_set('LESS_EQUAL')

    shader.bind()
    shader.uniform_float("color", (1.0, 0.0, 0.0, _preview_state["alpha"]))
    batch.draw(shader)

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
        _preview_state["batch"] = None
        _preview_state["coords_np"] = None

    _gpu_buf["idx_seq"] = None
    _gpu_buf["n_coords"] = 0


def _tag_redraw_all_3dviews():
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()


class BetterExperie_OT_PreviewVertexGroup(bpy.types.Operator):
    bl_idname = "better_experie.preview_vertex_group"
    bl_label = "快速预览"
    bl_description = "在3D视图中高亮显示该顶点组的顶点（1秒渐隐）"
    bl_options = {'REGISTER'}

    def execute(self, context):
        obj = context.active_object
        if not obj or obj.type != 'MESH':
            return {'CANCELLED'}

        active_vg = obj.vertex_groups.active
        if not active_vg:
            return {'CANCELLED'}

        vg_index = active_vg.index
        coords = []
        matrix_world = obj.matrix_world

        if context.mode == 'EDIT_MESH':
            bm = bmesh.from_edit_mesh(obj.data)
            deform_layer = bm.verts.layers.deform.active
            if deform_layer:
                coords = [matrix_world @ v.co.copy() for v in bm.verts if vg_index in v[deform_layer]]
        else:
            coords = [matrix_world @ v.co.copy() for v in obj.data.vertices if any(g.group == vg_index for g in v.groups)]

        if not coords:
            self.report({'INFO'}, "该顶点组为空")
            return {'CANCELLED'}

        _remove_draw_handler()
        _preview_state["coords_np"] = np.array(coords, dtype=np.float32)
        _preview_state["alpha"] = 1.0
        _preview_state["start_time"] = time.time()

        _preview_state["handler"] = bpy.types.SpaceView3D.draw_handler_add(
            _draw_callback_px, (), 'WINDOW', 'POST_VIEW'
        )

        if not bpy.app.timers.is_registered(_timer_fade_out):
            bpy.app.timers.register(_timer_fade_out)

        _tag_redraw_all_3dviews()
        return {'FINISHED'}


def draw_vertex_group_stats(self, context):
    obj = context.active_object
    if not obj or obj.type != 'MESH':
        return
    active_vg = obj.vertex_groups.active
    if not active_vg:
        return

    vg_index = active_vg.index
    verts_in_group = 0
    total_mesh_verts = 0

    if context.mode == 'EDIT_MESH':
        bm = bmesh.from_edit_mesh(obj.data)
        total_mesh_verts = len(bm.verts)
        deform_layer = bm.verts.layers.deform.active
        if deform_layer:
            for v in bm.verts:
                if vg_index in v[deform_layer]:
                    verts_in_group += 1
    else:
        total_mesh_verts = len(obj.data.vertices)
        for v in obj.data.vertices:
            for g in v.groups:
                if g.group == vg_index:
                    verts_in_group += 1
                    break

    layout = self.layout
    box = layout.box()
    row = box.row()
    row.label(text=f"{active_vg.name}: {verts_in_group}/{total_mesh_verts}", icon='GROUP_VERTEX')
    row.operator("better_experie.preview_vertex_group", text="快速预览", icon='RESTRICT_VIEW_OFF')


classes = (
    BetterExperie_OT_PreviewVertexGroup,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    if _clear_vg_cache_on_depsgraph not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(_clear_vg_cache_on_depsgraph)
    if _cleanup_on_load not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(_cleanup_on_load)
    bpy.types.DATA_PT_vertex_groups.append(draw_vertex_group_stats)


def unregister():
    bpy.types.DATA_PT_vertex_groups.remove(draw_vertex_group_stats)
    _remove_draw_handler()
    if bpy.app.timers.is_registered(_timer_fade_out):
        bpy.app.timers.unregister(_timer_fade_out)

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    if _clear_vg_cache_on_depsgraph in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(_clear_vg_cache_on_depsgraph)
    if _cleanup_on_load in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_cleanup_on_load)
    _stats_cache.clear()
