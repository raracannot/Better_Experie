# 对齐视图到面法线

import bpy
import gpu
import math
import traceback
from gpu_extras.batch import batch_for_shader
from mathutils import Vector, Matrix
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


class BetterExperie_OT_AlignViewToNormal(bpy.types.Operator):
    bl_idname = "better_experie.align_view_to_normal"
    bl_label = "对齐视图到面法线"
    bl_description = "悬停鼠标于网格面上预览法线方向，左键应用将视图正交对齐到该面"
    bl_options = {'REGISTER'}

    _draw_handle = None
    _hit_location = None
    _hit_normal = None
    _region = None
    _rv3d = None

    @classmethod
    def poll(cls, context):
        return context.area.type == 'VIEW_3D'

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
                "悬停网格面预览法线 | 左键应用对齐 | 右键/ESC退出")

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
                    rv3d = context.space_data.region_3d
                    was_camera_view = (rv3d.view_perspective == 'CAMERA')
                    cam = context.scene.camera

                    view_rot = (-self._hit_normal).to_track_quat('-Z', 'Y')
                    rv3d.view_rotation = view_rot
                    rv3d.view_perspective = 'ORTHO'
                    rv3d.view_location = self._hit_location

                    # 游标移至命中点 + 对齐旋转（取对齐后的视口方向）
                    context.scene.cursor.location = self._hit_location
                    normal = self._hit_normal.normalized()
                    view_right = view_rot @ Vector((1, 0, 0))
                    z = -normal
                    x = view_right - view_right.dot(z) * z
                    if x.length < 0.0001:
                        x = Vector((1, 0, 0)) - Vector((1, 0, 0)).dot(z) * z
                    x.normalize()
                    y = z.cross(x)
                    rot_mat = Matrix((x, y, z)).transposed().to_4x4()
                    context.scene.cursor.rotation_euler = rot_mat.to_euler('XYZ')

                    if was_camera_view and cam:
                        cam.rotation_euler = view_rot.to_euler()
                        cam.location = self._hit_location + self._hit_normal * rv3d.view_distance
                    self._cleanup(context)
                    self.report({'INFO'}, "视图已对齐到面法线")
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
    BetterExperie_OT_AlignViewToNormal,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
