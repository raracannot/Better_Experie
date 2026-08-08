# 面区域选择：以锐边作为分界线划分网格为多个面区域，交互式点击选取整片区域
# 交互/配色参考 select_sharp_chain，区域划分（flood fill）参考 select_region_by_loop

import bpy
import bmesh
import gpu
import mathutils
import traceback
from gpu_extras.batch import batch_for_shader
from mathutils.bvhtree import BVHTree
from bpy_extras import view3d_utils
from ...utils.modal_border import add_modal_border, remove_modal_border


def _is_barrier(edge):
    """锐边作为分界线"""
    return not edge.smooth


def _split_regions(bm, barrier_edges):
    """flood fill 划分面区域，返回 (regions_by_index, face_index_to_region)
    区域以面索引列表存储，避免 bmesh 对象引用跨刷新失效"""
    regions = []
    face_to_region = {}
    visited = set()

    for f in bm.faces:
        if f.hide or f in visited:
            continue
        current = []
        queue = [f]
        visited.add(f)
        while queue:
            curr_f = queue.pop(0)
            current.append(curr_f)
            for loop in curr_f.loops:
                edge = loop.edge
                if edge in barrier_edges:
                    continue
                adj_face = loop.link_loop_radial_next.face if loop.link_loop_radial_next else None
                if adj_face and adj_face != curr_f and adj_face not in visited and not adj_face.hide:
                    visited.add(adj_face)
                    queue.append(adj_face)
        if current:
            idx = len(regions)
            regions.append([f.index for f in current])
            for rf in current:
                face_to_region[rf.index] = idx
    return regions, face_to_region


class BetterExperie_OT_SelectFaceRegion(bpy.types.Operator):
    bl_idname = "better_experie.select_face_region"
    bl_label = "选择面区域（锐边分界）"
    bl_description = "以锐边作为分界线划分面区域，点击选中整片区域（Shift加选 Ctrl减选）"
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
        self.shader = gpu.shader.from_builtin('UNIFORM_COLOR')
        self.batch_barrier = None
        self.batch_hover = None
        self.regions = []
        self.face_to_region = {}
        self.barrier_edges = set()
        self._brushing = False
        self._last_applied_region = -1

    def _refresh_gpu_data(self, context):
        obj = context.edit_object
        bm = bmesh.from_edit_mesh(obj.data)
        bm.edges.ensure_lookup_table()
        bm.faces.ensure_lookup_table()

        # 收集锐边分界线
        self.barrier_edges = set(e for e in bm.edges if _is_barrier(e))
        barrier_coords = []
        for e in self.barrier_edges:
            barrier_coords.extend([e.verts[0].co.copy(), e.verts[1].co.copy()])
        if barrier_coords:
            self.batch_barrier = batch_for_shader(self.shader, 'LINES', {"pos": barrier_coords})
        else:
            self.batch_barrier = None

        # 划分面区域
        self.regions, self.face_to_region = _split_regions(bm, self.barrier_edges)

        self.face_bvhtree = BVHTree.FromBMesh(bm)

    def _update_status_text(self, context):
        text = (
            f"面区域选择（锐边分界） | 区域数:{len(self.regions)} | "
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
            traceback.print_exc()
            self._cleanup(context)
            return {'CANCELLED'}

    def modal(self, context, event):
        try:
            context.area.tag_redraw()

            if event.type == 'MOUSEMOVE':
                self._update_hover(context, event)
                if self._brushing:
                    self._apply_brush(context, event)

            elif event.type == 'LEFTMOUSE' and event.value == 'PRESS':
                self._start_brush(context, event)

            elif event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
                self._brushing = False

            elif event.type in {'RIGHTMOUSE', 'ESC'}:
                self._cleanup(context)
                return {'FINISHED'}

            # 放行视口导航
            if event.type in {
                'MIDDLEMOUSE', 'WHEELUPMOUSE', 'WHEELDOWNMOUSE',
                'TRACKPADPAN', 'TRACKPADZOOM', 'NDOF_MOTION',
            }:
                return {'PASS_THROUGH'}

            return {'RUNNING_MODAL'}
        except Exception:
            traceback.print_exc()
            self._cleanup(context)
            return {'CANCELLED'}

    def _start_brush(self, context, event):
        """按下左键：进入刷选态，替换模式仅在按下瞬间清空一次"""
        self._brushing = True
        if not event.shift and not event.ctrl:
            bpy.ops.mesh.select_all(action='DESELECT')
        self._apply_brush(context, event)

    def _apply_brush(self, context, event):
        """刷选：对当前悬停区域应用选择。节流——仅当悬停区域变化时执行"""
        obj = context.edit_object
        bm = bmesh.from_edit_mesh(obj.data)
        coord = event.mouse_region_x, event.mouse_region_y
        region, rv3d = context.region, context.region_data
        view_vector = view3d_utils.region_2d_to_vector_3d(region, rv3d, coord)
        ray_origin = view3d_utils.region_2d_to_origin_3d(region, rv3d, coord)
        matrix_inv = obj.matrix_world.inverted()
        loc, norm, face_idx, dist = self.face_bvhtree.ray_cast(
            matrix_inv @ ray_origin,
            (matrix_inv @ (ray_origin + view_vector) - (matrix_inv @ ray_origin)).normalized()
        )
        if loc is None:
            return
        bm.faces.ensure_lookup_table()
        hit_face = bm.faces[face_idx]
        if hit_face.hide:
            return
        region_idx = self.face_to_region.get(hit_face.index, -1)
        if region_idx == -1:
            return

        # 节流：悬停区域变化时才应用
        if region_idx == getattr(self, '_last_applied_region', -1):
            return
        self._last_applied_region = region_idx

        target_state = not event.ctrl
        for fidx in self.regions[region_idx]:
            bm.faces[fidx].select = target_state
        bmesh.update_edit_mesh(obj.data)

    def _update_hover(self, context, event):
        obj = context.edit_object
        bm = bmesh.from_edit_mesh(obj.data)
        coord = event.mouse_region_x, event.mouse_region_y
        region, rv3d = context.region, context.region_data
        view_vector = view3d_utils.region_2d_to_vector_3d(region, rv3d, coord)
        ray_origin = view3d_utils.region_2d_to_origin_3d(region, rv3d, coord)
        matrix_inv = obj.matrix_world.inverted()
        loc, norm, face_idx, dist = self.face_bvhtree.ray_cast(
            matrix_inv @ ray_origin,
            (matrix_inv @ (ray_origin + view_vector) - (matrix_inv @ ray_origin)).normalized()
        )
        if loc is not None:
            bm.faces.ensure_lookup_table()
            hit_face = bm.faces[face_idx]
            if hit_face.hide:
                self.batch_hover = None
                return
            region_idx = self.face_to_region.get(hit_face.index, -1)
            if region_idx != -1:
                region_indices = self.regions[region_idx]
                coords = []
                for fidx in region_indices:
                    f = bm.faces[fidx]
                    if len(f.verts) == 3:
                        coords.extend([v.co.copy() for v in f.verts])
                    else:
                        for tri in mathutils.geometry.tessellate_polygon([[v.co for v in f.verts]]):
                            for i in tri:
                                coords.append(f.verts[i].co.copy())
                if coords:
                    self.batch_hover = batch_for_shader(self.shader, 'TRIS', {"pos": coords})
                else:
                    self.batch_hover = None
        else:
            self.batch_hover = None

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

            # 分界线（锐边）— 蓝色
            if self.batch_barrier:
                gpu.state.depth_test_set(depth_mode)
                gpu.state.line_width_set(3.0)
                self.shader.uniform_float("color", (0.0, 0.4, 1.0, 0.5))
                self.batch_barrier.draw(self.shader)

            # 悬停区域 — 半透明填充
            if self.batch_hover:
                gpu.state.depth_test_set('ALWAYS')
                gpu.state.blend_set('ALPHA')
                self.shader.uniform_float("color", (1.0, 1.0, 1.0, 0.35))
                self.batch_hover.draw(self.shader)
                gpu.state.blend_set('NONE')

            gpu.matrix.pop()
        finally:
            gpu.state.depth_test_set('LESS_EQUAL')
            gpu.state.line_width_set(1.0)
    except ReferenceError:
        pass
    except Exception:
        traceback.print_exc()


classes = (
    BetterExperie_OT_SelectFaceRegion,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
