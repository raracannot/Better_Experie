# 以指定面修复旋转

import bpy
import bmesh
import gpu
import math
import traceback
from gpu_extras.batch import batch_for_shader
from mathutils import Vector
from bpy_extras.view3d_utils import region_2d_to_origin_3d, region_2d_to_vector_3d, location_3d_to_region_2d
from ...utils.modal_border import add_modal_border, remove_modal_border

CIRCLE_SEGMENTS = 32
PIXEL_RADIUS = 30


def _make_circle_basis(normal):
    ref = Vector((0, 0, 1))
    if abs(normal.dot(ref)) > 0.999:
        ref = Vector((1, 0, 0))
    v = normal.cross(ref).normalized()
    u = v.cross(normal).normalized()
    return u, v


def _align_object_to_normal(obj, normal):
    normal = normal.normalized()

    if obj.parent:
        parent_q = obj.parent.matrix_world.decompose()[1]
        target_local = parent_q.to_matrix().inverted() @ normal
    else:
        target_local = normal.copy()
    target_local.normalize()

    cur_q = obj.matrix_basis.to_quaternion()
    basis_mat = cur_q.to_matrix()
    target_basis = basis_mat.inverted() @ target_local
    if target_basis.length < 1e-8:
        target_basis = Vector((0, 0, 1))
    target_basis.normalize()
    delta_q = Vector((0, 0, 1)).rotation_difference(target_basis)
    delta_mat = delta_q.to_matrix()

    if obj.type == 'MESH' and obj.data and len(obj.data.vertices) > 0:
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        bmesh.ops.transform(bm, matrix=delta_mat.inverted().to_4x4(), verts=bm.verts)
        bm.to_mesh(obj.data)
        obj.data.update()
        bm.free()

    new_q = cur_q @ delta_q
    mode = obj.rotation_mode
    if mode == 'QUATERNION':
        obj.rotation_quaternion = new_q
    elif mode == 'AXIS_ANGLE':
        obj.rotation_axis_angle = new_q.to_axis_angle()
    else:
        order = mode if mode in {'XYZ', 'XZY', 'YXZ', 'YZX', 'ZXY', 'ZYX'} else 'XYZ'
        obj.rotation_euler = new_q.to_euler(order)


def _pixel_to_world_radius(region, rv3d, center_3d, pixel_radius):
    coord = location_3d_to_region_2d(region, rv3d, center_3d)
    if coord is None:
        return 0.05 * pixel_radius

    screen_right = Vector((coord.x + pixel_radius, coord.y))
    ray_origin = region_2d_to_origin_3d(region, rv3d, screen_right)
    ray_dir = region_2d_to_vector_3d(region, rv3d, screen_right)

    coord_center = (coord.x, coord.y)
    view_dir = region_2d_to_vector_3d(region, rv3d, coord_center)

    denom = ray_dir.dot(view_dir)
    if abs(denom) < 0.0001:
        return 0.05 * pixel_radius

    t = (center_3d - ray_origin).dot(view_dir) / denom
    return (ray_origin + t * ray_dir - center_3d).length


def _build_circle_verts(center, u, v, radius):
    verts = []
    step = 2 * math.pi / CIRCLE_SEGMENTS
    for i in range(CIRCLE_SEGMENTS):
        angle = step * i
        p = center + (u * math.cos(angle) + v * math.sin(angle)) * radius
        verts.append((p.x, p.y, p.z))
    return verts


def _build_circle_indices(n):
    return [(i, (i + 1) % n) for i in range(n)]


def _draw_circle_gpu(center, normal, world_radius):
    gpu.state.blend_set('ALPHA')
    gpu.state.depth_test_set('LESS_EQUAL')
    gpu.state.line_width_set(2.0)

    u, v = _make_circle_basis(normal)

    circle_verts = _build_circle_verts(center, u, v, world_radius)
    circle_indices = _build_circle_indices(CIRCLE_SEGMENTS)

    shader = gpu.shader.from_builtin('UNIFORM_COLOR')

    batch_circle = batch_for_shader(shader, 'LINES', {"pos": circle_verts}, indices=circle_indices)
    shader.bind()
    shader.uniform_float("color", (1.0, 1.0, 1.0, 0.9))
    batch_circle.draw(shader)

    normal_len = world_radius * 0.6
    up_offset = world_radius * 0.2
    up_start = center + normal * up_offset
    up_end = center + normal * (up_offset + normal_len) * 2
    up_batch = batch_for_shader(shader, 'LINES', {
        "pos": [(up_start.x, up_start.y, up_start.z), (up_end.x, up_end.y, up_end.z)]
    })
    shader.bind()
    shader.uniform_float("color", (1.0, 1.0, 1.0, 0.9))
    up_batch.draw(shader)


class BetterExperie_OT_FixRotationByFace(bpy.types.Operator):
    bl_idname = "better_experie.fix_rotation_by_face"
    bl_label = "以指定面修复旋转"
    bl_description = "悬停鼠标于网格面上预览法线，左键应用将所选物体的旋转对齐到该面法线方向"
    bl_options = {'REGISTER', 'UNDO'}

    _draw_handle = None
    _hit_location = None
    _hit_normal = None
    _region = None
    _rv3d = None

    @classmethod
    def poll(cls, context):
        return context.area.type == 'VIEW_3D' and bool(context.selected_objects)

    def _raycast(self, context, event):
        region = context.region
        rv3d = context.space_data.region_3d
        coord = (event.mouse_region_x, event.mouse_region_y)

        origin = region_2d_to_origin_3d(region, rv3d, coord)
        direction = region_2d_to_vector_3d(region, rv3d, coord)

        depsgraph = context.view_layer.depsgraph
        result, location, normal, index, obj, matrix = context.scene.ray_cast(
            depsgraph, origin, direction
        )

        if result and obj.type == 'MESH':
            return location, normal
        return None, None

    def _start_draw(self):
        if self._draw_handle is not None:
            return

        def draw():
            self._draw_callback()

        self._draw_handle = bpy.types.SpaceView3D.draw_handler_add(
            draw, (), 'WINDOW', 'POST_VIEW')

    def _stop_draw(self):
        if self._draw_handle is not None:
            bpy.types.SpaceView3D.draw_handler_remove(self._draw_handle, 'WINDOW')
            self._draw_handle = None

    def _draw_callback(self):
        if self._hit_location is None or self._hit_normal is None:
            return
        if self._region is None or self._rv3d is None:
            return
        world_radius = _pixel_to_world_radius(self._region, self._rv3d, self._hit_location, PIXEL_RADIUS)
        _draw_circle_gpu(self._hit_location, self._hit_normal, world_radius)

    def _apply_rotation(self, context):
        normal = self._hit_normal

        processed = 0
        for obj in context.selected_objects:
            if obj.type != 'MESH':
                continue
            _align_object_to_normal(obj, normal)
            processed += 1

        if processed > 0:
            self.report({'INFO'}, f"已将 {processed} 个对象的旋转修复到面法线方向")

    def invoke(self, context, event):
        try:
            if context.area.type != 'VIEW_3D':
                self.report({'WARNING'}, "请在三维视图中运行")
                return {'CANCELLED'}

            self._hit_location = None
            self._hit_normal = None
            self._region = context.region
            self._rv3d = context.space_data.region_3d
            self._start_draw()
            add_modal_border(self, context)

            context.window.cursor_set('CROSSHAIR')
            context.window_manager.modal_handler_add(self)
            context.area.tag_redraw()
            context.workspace.status_text_set(
                "悬停网格面预览法线 | 左键应用修复旋转 | 右键/ESC退出")

            return {'RUNNING_MODAL'}
        except Exception:
            traceback.print_exc()
            self._cleanup(context)
            return {'CANCELLED'}

    def modal(self, context, event):
        try:
            if event.type in {'RIGHTMOUSE', 'ESC'} and event.value == 'PRESS':
                self._cleanup(context)
                return {'CANCELLED'}

            if event.type == 'LEFTMOUSE' and event.value == 'PRESS':
                if self._hit_normal is not None and self._hit_location is not None:
                    self._apply_rotation(context)
                    self._cleanup(context)
                    return {'FINISHED'}

            if event.type == 'MOUSEMOVE':
                self._region = context.region
                self._rv3d = context.space_data.region_3d
                loc, norm = self._raycast(context, event)
                if norm is not None:
                    self._hit_location = loc
                    self._hit_normal = norm
                    context.area.tag_redraw()

            return {'RUNNING_MODAL'}
        except Exception:
            traceback.print_exc()
            self._cleanup(context)
            return {'CANCELLED'}

    def _cleanup(self, context):
        try:
            self._stop_draw()
        except Exception:
            pass
        remove_modal_border(self)
        try:
            context.window.cursor_set('DEFAULT')
        except Exception:
            pass
        try:
            if context and context.workspace:
                context.workspace.status_text_set(None)
        except Exception:
            pass
        try:
            if context and context.area:
                context.area.tag_redraw()
        except Exception:
            pass


classes = (
    BetterExperie_OT_FixRotationByFace,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
