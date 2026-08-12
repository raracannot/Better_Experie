# 锐边/边界/UV缝合边连续链选择（交互式模态），支持Tab切换模式、Alt切换分叉行为，带GPU实时预览与左下角操作说明

import bpy
import bmesh
import gpu
import traceback
from gpu_extras.batch import batch_for_shader
from mathutils.bvhtree import BVHTree
from bpy_extras import view3d_utils
from ...utils.modal_border import add_modal_border, remove_modal_border

MODE_ORDER = ('SHARP', 'BOUNDARY', 'UV_SEAM')
MODE_NAMES = {
    'SHARP': '锐边',
    'BOUNDARY': '边界',
    'UV_SEAM': 'UV缝合边',
}


def _is_target(edge, mode):
    if mode == 'SHARP':
        return not edge.smooth
    if mode == 'BOUNDARY':
        return len(edge.link_faces) == 1
    if mode == 'UV_SEAM':
        return edge.seam
    return False


def _get_continuous_chain(start_edge, mode, stop_at_junctions):
    chain = {start_edge}
    stack = [start_edge]
    while stack:
        curr_e = stack.pop()
        for v in curr_e.verts:
            neighbors = [e for e in v.link_edges if _is_target(e, mode)]
            if stop_at_junctions and len(neighbors) > 2:
                continue
            for next_e in neighbors:
                if next_e not in chain:
                    chain.add(next_e)
                    stack.append(next_e)
    return chain


def _draw_callback_3d(self, context):
    try:
        if not self.shader or not context.object:
            return
        matrix = context.object.matrix_world
        self.shader.bind()
        is_xray = False
        if context.space_data and hasattr(context.space_data.shading, 'show_xray'):
            is_xray = context.space_data.shading.show_xray

        depth_mode = 'ALWAYS' if is_xray else 'LESS_EQUAL'

        try:
            gpu.matrix.push()
            gpu.matrix.multiply_matrix(matrix)

            if self.batch_unsel:
                gpu.state.depth_test_set(depth_mode)
                gpu.state.line_width_set(3.0)
                color = {
                    'SHARP': (0.0, 0.4, 1.0, 0.5),
                    'BOUNDARY': (0.1, 1.0, 0.2, 0.6),
                    'UV_SEAM': (0.9, 0.4, 0.0, 0.7),
                }[self.mode]
                self.shader.uniform_float("color", color)
                self.batch_unsel.draw(self.shader)

            if self.batch_sel:
                gpu.state.depth_test_set(depth_mode)
                gpu.state.line_width_set(3.0)
                self.shader.uniform_float("color", (1.0, 0.8, 0.0, 0.8))
                self.batch_sel.draw(self.shader)

            if self.batch_hover:
                gpu.state.depth_test_set('ALWAYS')
                gpu.state.line_width_set(6.0)
                self.shader.uniform_float("color", (1.0, 1.0, 1.0, 1.0))
                self.batch_hover.draw(self.shader)

            gpu.matrix.pop()
        finally:
            gpu.state.depth_test_set('LESS_EQUAL')
            gpu.state.line_width_set(1.0)
    except ReferenceError:
        pass
    except Exception:
        traceback.print_exc()


class BetterExperie_OT_SelectSharpChain(bpy.types.Operator):
    bl_idname = "better_experie.select_sharp_chain"
    bl_label = "选择锐边/边界/UV缝合边连续链"
    bl_description = "交互式选择锐边、边界或UV缝合边连续链：按住左键刷选，支持Shift加选Ctrl减选、Tab切换模式、Alt切换分叉行为"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return (
            context.active_object is not None
            and context.active_object.type == 'MESH'
            and context.mode == 'EDIT_MESH'
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._handle_3d = None
        self._modal_border_handle = None
        self.face_bvhtree = None
        self.mode = 'SHARP'
        self.is_alt_pressed = False
        self.shader = gpu.shader.from_builtin('UNIFORM_COLOR')
        self.batch_unsel = None
        self.batch_sel = None
        self.batch_hover = None
        self.last_edge_idx = -1
        self.target_chain_indices = []
        self._brushing = False
        self._last_applied_edge = None
        self._last_applied_alt = None

    def _refresh_gpu_data(self, context):
        obj = context.edit_object
        bm = bmesh.from_edit_mesh(obj.data)
        bm.edges.ensure_lookup_table()

        unsel_coords = []
        sel_coords = []
        for e in bm.edges:
            target = _is_target(e, self.mode)
            if not target and not e.select:
                continue
            co1, co2 = e.verts[0].co.copy(), e.verts[1].co.copy()
            if e.select:
                sel_coords.extend([co1, co2])
            elif target:
                unsel_coords.extend([co1, co2])

        if unsel_coords:
            self.batch_unsel = batch_for_shader(self.shader, 'LINES', {"pos": unsel_coords})
        else:
            self.batch_unsel = None
        if sel_coords:
            self.batch_sel = batch_for_shader(self.shader, 'LINES', {"pos": sel_coords})
        else:
            self.batch_sel = None

        self.face_bvhtree = BVHTree.FromBMesh(bm)

    def _update_status_text(self, context):
        """左下角操作说明"""
        mode_name = MODE_NAMES[self.mode]
        fork_name = '全选' if self.is_alt_pressed else '断开'
        text = (
            f"选择{mode_name}连续链 | "
            f"模式:{mode_name}(Tab) | 分叉:{fork_name}(Alt) | "
            "左键按住刷选 | Shift加选 Ctrl减选 | 右键退出"
        )
        try:
            context.workspace.status_text_set(text)
        except Exception:
            pass

    def invoke(self, context, event):
        try:
            if not self.poll(context):
                self.report({'WARNING'}, "请在3D视图的编辑模式下运行")
                return {'CANCELLED'}

            self._refresh_gpu_data(context)
            self._handle_3d = bpy.types.SpaceView3D.draw_handler_add(
                _draw_callback_3d, (self, context), 'WINDOW', 'POST_VIEW')
            add_modal_border(self, context)
            self._update_status_text(context)
            context.window_manager.modal_handler_add(self)
            return {'RUNNING_MODAL'}
        except Exception:
            self._cleanup(context)
            return {'CANCELLED'}

    def modal(self, context, event):
        try:
            context.area.tag_redraw()
            if self.is_alt_pressed != event.alt:
                self.is_alt_pressed = event.alt
                self._update_status_text(context)

            if event.type == 'MOUSEMOVE':
                self._update_hover(context, event)
                if self._brushing:
                    self._apply_brush(context, event)
                return {'PASS_THROUGH'}

            elif event.type == 'TAB' and event.value == 'PRESS':
                self.mode = MODE_ORDER[(MODE_ORDER.index(self.mode) + 1) % len(MODE_ORDER)]
                self._refresh_gpu_data(context)
                self._update_hover(context, event)
                self._update_status_text(context)
                return {'RUNNING_MODAL'}

            elif event.type == 'LEFTMOUSE' and event.value == 'PRESS':
                self._start_brush(context, event)
                return {'RUNNING_MODAL'}

            elif event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
                self._brushing = False
                self._refresh_gpu_data(context)
                return {'RUNNING_MODAL'}

            elif event.type in {'RIGHTMOUSE', 'ESC'}:
                self._cleanup(context)
                return {'FINISHED'}

            return {'PASS_THROUGH'}
        except Exception:
            traceback.print_exc()
            self._cleanup(context)
            return {'CANCELLED'}

    def _start_brush(self, context, event):
        """按下左键：初始化刷选状态，替换模式仅在按下瞬间清空一次"""
        self._brushing = True
        if not event.shift and not event.ctrl:
            bpy.ops.mesh.select_all(action='DESELECT')
        self._apply_brush(context, event)
        self._refresh_gpu_data(context)

    def _apply_brush(self, context, event):
        """刷选：对当前悬停链应用选择。节流——仅当悬停链或修饰键变化时执行"""
        if self.last_edge_idx == -1 or not self.target_chain_indices:
            return
        if (self._last_applied_edge == self.last_edge_idx
                and self._last_applied_alt == getattr(self, '_last_alt', None)):
            return

        target_state = not event.ctrl
        obj = context.edit_object
        bm = bmesh.from_edit_mesh(obj.data)
        bm.edges.ensure_lookup_table()
        for idx in self.target_chain_indices:
            bm.edges[idx].select = target_state
        bmesh.update_edit_mesh(obj.data)

        self._last_applied_edge = self.last_edge_idx
        self._last_applied_alt = getattr(self, '_last_alt', None)
        self._refresh_gpu_data(context)

    def _update_hover(self, context, event):
        obj = context.edit_object
        bm = bmesh.from_edit_mesh(obj.data)
        is_xray = False
        if context.space_data and hasattr(context.space_data.shading, 'show_xray'):
            is_xray = context.space_data.shading.show_xray

        coord = event.mouse_region_x, event.mouse_region_y
        region, rv3d = context.region, context.region_data
        view_vector = view3d_utils.region_2d_to_vector_3d(region, rv3d, coord)
        ray_origin = view3d_utils.region_2d_to_origin_3d(region, rv3d, coord)
        matrix_inv = obj.matrix_world.inverted()
        origin_local = matrix_inv @ ray_origin
        direction_local = (matrix_inv @ (ray_origin + view_vector) - origin_local).normalized()

        hit_points = []
        curr_origin = origin_local
        for _ in range(6):
            loc, norm, face_idx, dist = self.face_bvhtree.ray_cast(curr_origin, direction_local)
            if loc is None:
                break
            hit_points.append((loc, face_idx))
            if not is_xray:
                break
            curr_origin = loc + direction_local * 0.0005

        best_edge = None
        min_dist = float('inf')
        bm.faces.ensure_lookup_table()
        for loc, f_idx in hit_points:
            face = bm.faces[f_idx]
            search_faces = {face} | {f for e in face.edges for f in e.link_faces}
            for f in search_faces:
                for e in f.edges:
                    if _is_target(e, self.mode):
                        d = self._dist_to_edge(loc, e)
                        if d < min_dist:
                            min_dist = d
                            best_edge = e

        if best_edge:
            if best_edge.index != self.last_edge_idx or getattr(self, '_last_alt', None) != event.alt:
                self.last_edge_idx = best_edge.index
                self._last_alt = event.alt
                chain = _get_continuous_chain(best_edge, self.mode, not event.alt)
                self.target_chain_indices = [e.index for e in chain]
                hover_coords = []
                for e in chain:
                    hover_coords.extend([e.verts[0].co.copy(), e.verts[1].co.copy()])
                self.batch_hover = batch_for_shader(self.shader, 'LINES', {"pos": hover_coords})
        else:
            self.batch_hover = None
            self.last_edge_idx = -1

    @staticmethod
    def _dist_to_edge(point, edge):
        v1, v2 = edge.verts[0].co, edge.verts[1].co
        line_vec = v2 - v1
        l2 = line_vec.length_squared
        if l2 == 0:
            return (point - v1).length
        t = max(0.0, min(1.0, (point - v1).dot(line_vec) / l2))
        return (point - (v1 + t * line_vec)).length

    def _cleanup(self, context):
        try:
            if self._handle_3d:
                bpy.types.SpaceView3D.draw_handler_remove(self._handle_3d, 'WINDOW')
                self._handle_3d = None
        except Exception:
            pass
        remove_modal_border(self)
        try:
            if context and context.workspace:
                context.workspace.status_text_set(None)
        except Exception:
            pass
        if context and context.area:
            context.area.tag_redraw()



classes = (
    BetterExperie_OT_SelectSharpChain,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
