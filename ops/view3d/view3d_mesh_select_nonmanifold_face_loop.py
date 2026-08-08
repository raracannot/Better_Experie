# 并排面环选取（交互式模态）：点击网格后沿 Ring 方向自动选中整条面环，
# 支持方向/次数/角度限制/锐边停止/三角面停止，带GPU实时预览高亮

import bpy
import bmesh
import math
import gpu
import traceback
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from bpy_extras import view3d_utils
from gpu_extras.batch import batch_for_shader
from ...utils.modal_border import add_modal_border, remove_modal_border


def _dist_to_edge(point, edge_v1, edge_v2):
    line_vec = edge_v2 - edge_v1
    p_vec = point - edge_v1
    line_len_sq = line_vec.length_squared
    if line_len_sq == 0:
        return p_vec.length
    t = max(0.0, min(1.0, p_vec.dot(line_vec) / line_len_sq))
    closest_point = edge_v1 + t * line_vec
    return (point - closest_point).length


def _get_opposite_edge_geometric(face, edge, parallel_factor):
    if len(face.edges) < 3:
        return None
    v1, v2 = edge.verts[0].co, edge.verts[1].co
    mid_point = (v1 + v2) / 2
    edge_vec = (v2 - v1).normalized()
    perp_dir = edge_vec.cross(face.normal).normalized()
    best_edge = None
    max_alignment = -1.0
    for other_edge in face.edges:
        if other_edge == edge or other_edge.hide:
            continue
        other_mid = (other_edge.verts[0].co + other_edge.verts[1].co) / 2
        target_vec = (other_mid - mid_point).normalized()
        alignment = abs(target_vec.dot(perp_dir))
        if alignment > max_alignment:
            max_alignment = alignment
            best_edge = other_edge
    return best_edge if max_alignment >= parallel_factor else None


def _draw(self, context):
    try:
        if not self.preview_edge:
            return
        shader = gpu.shader.from_builtin('UNIFORM_COLOR')
        try:
            gpu.state.line_width_set(3.0)
            matrix = context.object.matrix_world
            v1 = matrix @ self.preview_edge[0]
            v2 = matrix @ self.preview_edge[1]
            batch = batch_for_shader(shader, 'LINES', {"pos": [v1, v2]})
            shader.bind()
            shader.uniform_float("color", (1.0, 0.5, 0.0, 1.0))
            batch.draw(shader)
        finally:
            gpu.state.line_width_set(1.0)
    except ReferenceError:
        pass
    except Exception:
        traceback.print_exc()


class BetterExperie_FaceRingSettings(bpy.types.PropertyGroup):
    """非流形循环面选取的参数设置（挂载到 Scene，跨 operator 实例稳定）"""
    direction: bpy.props.EnumProperty(
        name="扩选方向",
        items=[('BOTH', "双向", ""), ('DIR_A', "方向 A", ""), ('DIR_B', "方向 B", "")],
        default='BOTH')
    count: bpy.props.IntProperty(
        name="扩选次数", default=100, min=1, max=1000)
    parallel_factor: bpy.props.FloatProperty(
        name="平行系数", description="对边匹配的严格程度，越大越严格", default=0.5, min=0.0, max=1.0)
    angle_limit: bpy.props.FloatProperty(
        name="角度限制", description="相邻面法线夹角超过此值则停止",
        default=math.radians(30.0), min=0.0, max=math.radians(180.0), unit='ROTATION')
    stop_at_sharp: bpy.props.BoolProperty(
        name="在锐边处停止", default=False)
    stop_at_triangles: bpy.props.BoolProperty(
        name="在三角面前停止", default=False)


def _get_settings(context):
    return context.scene.better_experie_face_ring_settings


class BetterExperie_OT_SelectFaceRingModal(bpy.types.Operator):
    bl_idname = "better_experie.select_face_ring_modal"
    bl_label = "选择非流形循环面"
    bl_description = "点击网格后沿并排（Ring）方向选中整条面环，支持方向/次数/角度/锐边/三角面限制，Shift加选Ctrl减选"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return (
            context.active_object is not None
            and context.active_object.type == 'MESH'
            and context.mode == 'EDIT_MESH'
        )

    face_index: bpy.props.IntProperty(default=-1, options={'HIDDEN'})
    hit_location: bpy.props.FloatVectorProperty(options={'HIDDEN'})
    select_mode: bpy.props.EnumProperty(
        items=[('SET', "设置", ""), ('ADD', "加选", ""), ('SUB', "减选", "")],
        default='SET', options={'HIDDEN'})

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._handle = None
        self._modal_border_handle = None
        self.preview_edge = None
        self.bvhtree = None
        self._modal_started = False

    def invoke(self, context, event):
        try:
            if not self.poll(context):
                self.report({'WARNING'}, "请在3D视图的编辑模式下运行")
                return {'CANCELLED'}
            return self._start_modal(context)
        except Exception:
            traceback.print_exc()
            self._cleanup(context)
            return {'CANCELLED'}

    def _start_modal(self, context):
        """启动持续模态：注册绘制、边框、状态栏、事件处理"""
        try:
            bm = bmesh.from_edit_mesh(context.edit_object.data)
            self.bvhtree = BVHTree.FromBMesh(bm)

            args = (self, context)
            self._handle = bpy.types.SpaceView3D.draw_handler_add(
                _draw, args, 'WINDOW', 'POST_VIEW')

            add_modal_border(self, context)
            context.window.cursor_modal_set('CROSSHAIR')
            self._update_status_text(context)
            context.window_manager.modal_handler_add(self)
            self._modal_started = True
            return {'RUNNING_MODAL'}
        except Exception:
            traceback.print_exc()
            self._cleanup(context)
            return {'CANCELLED'}

    def modal(self, context, event):
        try:
            context.area.tag_redraw()

            if event.type == 'MOUSEMOVE':
                obj = context.edit_object
                bm = bmesh.from_edit_mesh(obj.data)

                coord = event.mouse_region_x, event.mouse_region_y
                region = context.region
                rv3d = context.region_data
                view_vector = view3d_utils.region_2d_to_vector_3d(region, rv3d, coord)
                ray_origin = view3d_utils.region_2d_to_origin_3d(region, rv3d, coord)

                matrix_inv = obj.matrix_world.inverted()
                local_origin = matrix_inv @ ray_origin
                local_direction = (matrix_inv @ (ray_origin + view_vector) - local_origin).normalized()

                loc, norm, face_idx, dist = self.bvhtree.ray_cast(local_origin, local_direction)

                if loc is not None and not bm.faces[face_idx].hide:
                    hit_face = bm.faces[face_idx]
                    min_d = float('inf')
                    best_e = None
                    for e in hit_face.edges:
                        d = _dist_to_edge(loc, e.verts[0].co, e.verts[1].co)
                        if d < min_d:
                            min_d = d
                            best_e = e
                    if best_e:
                        self.preview_edge = (best_e.verts[0].co.copy(), best_e.verts[1].co.copy())
                    else:
                        self.preview_edge = None
                else:
                    self.preview_edge = None

            elif event.type == 'LEFTMOUSE' and event.value == 'PRESS':
                if self.preview_edge:
                    obj = context.edit_object
                    bm = bmesh.from_edit_mesh(obj.data)
                    coord = event.mouse_region_x, event.mouse_region_y
                    region = context.region
                    rv3d = context.region_data
                    view_vector = view3d_utils.region_2d_to_vector_3d(region, rv3d, coord)
                    ray_origin = view3d_utils.region_2d_to_origin_3d(region, rv3d, coord)
                    matrix_inv = obj.matrix_world.inverted()
                    loc, norm, face_idx, dist = self.bvhtree.ray_cast(
                        matrix_inv @ ray_origin,
                        (matrix_inv @ (ray_origin + view_vector) - (matrix_inv @ ray_origin)).normalized()
                    )

                    if loc is not None:
                        if event.shift:
                            self.select_mode = 'ADD'
                        elif event.ctrl:
                            self.select_mode = 'SUB'
                        else:
                            self.select_mode = 'SET'

                        self.face_index = face_idx
                        self.hit_location = loc
                        self.execute(context)
                        # 持续选取：不退出，等待 Esc/右键
                        return {'RUNNING_MODAL'}

            elif event.type == 'S' and event.value == 'PRESS':
                # S 调用独立设置面板（编辑场景属性组），确认后返回当前模态继续
                self._update_status_text(context)
                bpy.ops.better_experie.face_ring_settings('INVOKE_DEFAULT')
                return {'RUNNING_MODAL'}

            elif event.type in {'RIGHTMOUSE', 'ESC'}:
                self._cleanup(context)
                return {'CANCELLED'}

            # 放行视口导航事件（中键旋转、滚轮缩放、触控板等），避免拦截
            if event.type in {
                'MIDDLEMOUSE', 'WHEELUPMOUSE', 'WHEELDOWNMOUSE',
                'TRACKPADPAN', 'TRACKPADZOOM', 'NDOF_MOTION',
                'INBETWEEN_MOUSEMOVE',
            }:
                return {'PASS_THROUGH'}

            return {'RUNNING_MODAL'}
        except Exception:
            traceback.print_exc()
            self._cleanup(context)
            return {'CANCELLED'}

    def _update_status_text(self, context):
        """刷新左下角状态栏，展示当前参数与快捷键"""
        s = _get_settings(context)
        dir_name = {'BOTH': '双向', 'DIR_A': '方向A', 'DIR_B': '方向B'}.get(s.direction, s.direction)
        text = (
            f"扩选:{dir_name} 次数:{s.count} "
            f"平行:{s.parallel_factor:.2f} "
            f"锐停:{'开' if s.stop_at_sharp else '关'} "
            f"三角停:{'开' if s.stop_at_triangles else '关'} | "
            "S设置参数 | 左键扩选 Shift加选 Ctrl减选 | 右键/ESC退出"
        )
        try:
            context.workspace.status_text_set(text)
        except Exception:
            pass

    def execute(self, context):
        if self.face_index == -1:
            return {'FINISHED'}

        s = _get_settings(context)

        obj = context.edit_object
        bm = bmesh.from_edit_mesh(obj.data)
        bm.faces.ensure_lookup_table()

        if self.face_index >= len(bm.faces):
            return {'FINISHED'}
        hit_face = bm.faces[self.face_index]
        if hit_face.hide:
            return {'FINISHED'}
        loc = Vector(self.hit_location)

        min_dist = float('inf')
        start_edge = None
        for edge in hit_face.edges:
            if edge.hide:
                continue
            d = _dist_to_edge(loc, edge.verts[0].co, edge.verts[1].co)
            if d < min_dist:
                min_dist = d
                start_edge = edge
        if not start_edge:
            return {'FINISHED'}

        if self.select_mode == 'SET':
            bpy.ops.mesh.select_all(action='DESELECT')
        target_state = False if self.select_mode == 'SUB' else True
        context.tool_settings.mesh_select_mode = (False, False, True)

        def expand(start_f, from_edge, steps):
            curr_f = start_f
            curr_e = from_edge
            processed = {start_f}
            for _ in range(steps):
                curr_f.select = target_state
                next_e = _get_opposite_edge_geometric(curr_f, curr_e, s.parallel_factor)
                if not next_e:
                    break
                if s.stop_at_sharp and not next_e.smooth:
                    break
                next_faces = [f for f in next_e.link_faces if f != curr_f and not f.hide]
                if not next_faces:
                    break
                next_f = next_faces[0]
                if next_f in processed:
                    break
                if s.stop_at_triangles and len(next_f.verts) == 3:
                    break
                if curr_f.normal.angle(next_f.normal) > s.angle_limit:
                    break
                curr_f, curr_e = next_f, next_e
                processed.add(curr_f)

        if s.direction in {'BOTH', 'DIR_A'}:
            expand(hit_face, start_edge, s.count)
        if s.direction in {'BOTH', 'DIR_B'}:
            neighbor_faces = [f for f in start_edge.link_faces if f != hit_face and not f.hide]
            for nf in neighbor_faces:
                if s.stop_at_triangles and len(nf.verts) == 3:
                    continue
                expand(nf, start_edge, s.count)

        bmesh.update_edit_mesh(obj.data)
        # 选择已生效、网格已刷新，重建 BVH 使后续射线检测引用最新网格
        self._rebuild_bvhtree(context)
        return {'FINISHED'}

    def _rebuild_bvhtree(self, context):
        try:
            obj = context.edit_object
            if obj and obj.type == 'MESH':
                bm = bmesh.from_edit_mesh(obj.data)
                self.bvhtree = BVHTree.FromBMesh(bm)
        except Exception:
            traceback.print_exc()

    def _cleanup(self, context):
        self._modal_started = False
        try:
            if self._handle:
                bpy.types.SpaceView3D.draw_handler_remove(self._handle, 'WINDOW')
                self._handle = None
        except Exception:
            pass
        remove_modal_border(self)
        if context and context.window:
            context.window.cursor_modal_restore()
            context.workspace.status_text_set(None)


class BetterExperie_OT_FaceRingSettings(bpy.types.Operator):
    """非流形循环面选取参数设置面板：编辑场景属性组"""
    bl_idname = "better_experie.face_ring_settings"
    bl_label = "循环面选取设置"
    bl_description = "设置非流形循环面选取参数"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        return (
            context.active_object is not None
            and context.active_object.type == 'MESH'
            and context.mode == 'EDIT_MESH'
        )

    def draw(self, context):
        s = _get_settings(context)
        layout = self.layout
        col = layout.column(align=True)
        col.prop(s, "direction", expand=True)
        col.prop(s, "count")
        col.separator()
        col.prop(s, "parallel_factor", slider=True)
        col.prop(s, "angle_limit", slider=True)
        col.separator()
        col.prop(s, "stop_at_sharp")
        col.prop(s, "stop_at_triangles")

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=320)

    def execute(self, context):
        return {'FINISHED'}


class BetterExperie_OT_SelectFaceRingBatch(bpy.types.Operator):
    """非流形循环面批处理选取：无模态，从当前选中面出发扩选，参数走 undo 面板"""
    bl_idname = "better_experie.select_face_ring_batch"
    bl_label = "选择非流形循环面（批处理）"
    bl_description = "从当前选中的面出发，沿并排（Ring）方向自动选中整条面环"
    bl_options = {'REGISTER', 'UNDO'}

    direction: bpy.props.EnumProperty(
        name="扩选方向",
        items=[('BOTH', "双向", ""), ('DIR_A', "方向 A", ""), ('DIR_B', "方向 B", "")],
        default='BOTH')
    count: bpy.props.IntProperty(
        name="扩选次数", default=100, min=1, max=1000)
    parallel_factor: bpy.props.FloatProperty(
        name="平行系数", description="对边匹配的严格程度，越大越严格", default=0.5, min=0.0, max=1.0)
    angle_limit: bpy.props.FloatProperty(
        name="角度限制", description="相邻面法线夹角超过此值则停止",
        default=math.radians(30.0), min=0.0, max=math.radians(180.0), unit='ROTATION')
    stop_at_sharp: bpy.props.BoolProperty(
        name="在锐边处停止", default=False)
    stop_at_triangles: bpy.props.BoolProperty(
        name="在三角面前停止", default=False)

    @classmethod
    def poll(cls, context):
        return (
            context.active_object is not None
            and context.active_object.type == 'MESH'
            and context.mode == 'EDIT_MESH'
        )

    def draw(self, context):
        layout = self.layout
        col = layout.column(align=True)
        col.prop(self, "direction", expand=True)
        col.prop(self, "count")
        col.separator()
        col.prop(self, "parallel_factor", slider=True)
        col.prop(self, "angle_limit", slider=True)
        col.separator()
        col.prop(self, "stop_at_sharp")
        col.prop(self, "stop_at_triangles")

    def execute(self, context):
        obj = context.edit_object
        bm = bmesh.from_edit_mesh(obj.data)
        bm.faces.ensure_lookup_table()

        # 从当前选中的面出发
        seed_faces = [f for f in bm.faces if f.select and not f.hide]
        if not seed_faces:
            self.report({'WARNING'}, "请先选择至少一个面")
            return {'CANCELLED'}

        def expand(start_f, from_edge, steps, target_state):
            curr_f = start_f
            curr_e = from_edge
            processed = {start_f}
            for _ in range(steps):
                curr_f.select = target_state
                next_e = _get_opposite_edge_geometric(curr_f, curr_e, self.parallel_factor)
                if not next_e:
                    break
                if self.stop_at_sharp and not next_e.smooth:
                    break
                next_faces = [f for f in next_e.link_faces if f != curr_f and not f.hide]
                if not next_faces:
                    break
                next_f = next_faces[0]
                if next_f in processed:
                    break
                if self.stop_at_triangles and len(next_f.verts) == 3:
                    break
                if curr_f.normal.angle(next_f.normal) > self.angle_limit:
                    break
                curr_f, curr_e = next_f, next_e
                processed.add(curr_f)

        for sf in seed_faces:
            # 取面的第一条非隐藏边作为起始边
            start_edge = next((e for e in sf.edges if not e.hide), None)
            if not start_edge:
                continue

            if self.direction in {'BOTH', 'DIR_A'}:
                expand(sf, start_edge, self.count, True)
            if self.direction in {'BOTH', 'DIR_B'}:
                neighbor_faces = [f for f in start_edge.link_faces if f != sf and not f.hide]
                for nf in neighbor_faces:
                    if self.stop_at_triangles and len(nf.verts) == 3:
                        continue
                    expand(nf, start_edge, self.count, True)

        bmesh.update_edit_mesh(obj.data)
        return {'FINISHED'}


classes = (
    BetterExperie_FaceRingSettings,
    BetterExperie_OT_FaceRingSettings,
    BetterExperie_OT_SelectFaceRingBatch,
    BetterExperie_OT_SelectFaceRingModal,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.better_experie_face_ring_settings = bpy.props.PointerProperty(
        type=BetterExperie_FaceRingSettings)


def unregister():
    if hasattr(bpy.types.Scene, "better_experie_face_ring_settings"):
        del bpy.types.Scene.better_experie_face_ring_settings
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
