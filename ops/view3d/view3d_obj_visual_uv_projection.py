# 可视化 UV 投射：平面/三平面/球体/圆柱体，NumPy 加速 + GPU 视口边框提示
# 下拉菜单注册到 VIEW3D_MT_uv_map

import bpy
import gpu
import numpy as np
import mathutils
import math
import traceback
from gpu_extras.batch import batch_for_shader
from ...utils.modal_border import add_modal_border, remove_modal_border


# ═══════════════════════════════════════════════════════════════
# 投影引擎
# ═══════════════════════════════════════════════════════════════

class UVEngine:
    def create_gizmo(self): raise NotImplementedError
    def apply_scale(self, gizmo, size_local): raise NotImplementedError
    def calculate_uv(self, local_pos, local_normals): raise NotImplementedError


class PlaneEngine(UVEngine):
    def create_gizmo(self):
        bpy.ops.mesh.primitive_plane_add(size=2)
        bpy.context.active_object.rotation_euler[0] = math.radians(90)
    def apply_scale(self, gizmo, size_local):
        gizmo.scale = (max(size_local[0], 0.001), max(size_local[1], 0.001), 1.0)
    def calculate_uv(self, p, n):
        uvs = np.empty((len(p), 2), dtype=np.float32)
        uvs[:, 0] = p[:, 0] * 0.5 + 0.5
        uvs[:, 1] = p[:, 1] * 0.5 + 0.5
        return uvs


class CubeEngine(UVEngine):
    def create_gizmo(self):
        bpy.ops.mesh.primitive_cube_add(size=2)
    def apply_scale(self, gizmo, size_local):
        gizmo.scale = [max(s, 0.001) for s in size_local]
    def calculate_uv(self, p, n):
        max_axis = np.argmax(np.abs(n), axis=1)
        uvs = np.empty((len(p), 2), dtype=np.float32)
        x, y, z = p[:, 0], p[:, 1], p[:, 2]
        uvs[:, 0] = np.where(max_axis == 0, y, x)
        uvs[:, 1] = np.where(max_axis == 2, y, z)
        return uvs * 0.5 + 0.5


class SphereEngine(UVEngine):
    def create_gizmo(self):
        bpy.ops.mesh.primitive_uv_sphere_add(radius=1, segments=32, ring_count=16)
    def apply_scale(self, gizmo, size_local):
        val = max(np.max(size_local), 0.001)
        gizmo.scale = (val, val, val)
    def calculate_uv(self, p, n):
        norms = np.linalg.norm(p, axis=1, keepdims=True)
        p_norm = p / np.where(norms == 0, 1, norms)
        uvs = np.empty((len(p), 2), dtype=np.float32)
        uvs[:, 0] = np.arctan2(p_norm[:, 1], p_norm[:, 0]) / (2 * np.pi) + 0.5
        uvs[:, 1] = np.arcsin(np.clip(p_norm[:, 2], -1, 1)) / np.pi + 0.5
        return uvs


class CylinderEngine(UVEngine):
    def create_gizmo(self):
        bpy.ops.mesh.primitive_cylinder_add(radius=1, vertices=32, depth=2)
    def apply_scale(self, gizmo, size_local):
        radius = max(size_local[0], size_local[1], 0.001)
        gizmo.scale = (radius, radius, max(size_local[2], 0.001))
    def calculate_uv(self, p, n):
        uvs = np.empty((len(p), 2), dtype=np.float32)
        uvs[:, 0] = np.arctan2(p[:, 1], p[:, 0]) / (2 * np.pi) + 0.5
        uvs[:, 1] = p[:, 2] * 0.5 + 0.5
        return uvs


class UVEngineFactory:
    _engines = {
        'CUBE': CubeEngine,
        'PLANE': PlaneEngine,
        'SPHERE': SphereEngine,
        'CYLINDER': CylinderEngine,
    }

    @classmethod
    def get_engine(cls, mode):
        engine_cls = cls._engines.get(mode, CubeEngine)
        return engine_cls()


# ═══════════════════════════════════════════════════════════════
# GPU 视口边框
# ═══════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════
# 核心操作符
# ═══════════════════════════════════════════════════════════════

class BetterExperie_OT_VisualUVProjection(bpy.types.Operator):
    bl_idname = "better_experie.visual_uv_projection"
    bl_label = "可视化 UV 投射"
    bl_description = "通过 Gizmo 实时可视化 UV 投射：Tab切换模式 F适配物体 ESC退出"
    bl_options = {'REGISTER', 'UNDO'}

    _instance = None

    @classmethod
    def poll(cls, context):
        return (
            context.active_object is not None
            and context.active_object.type == 'MESH'
        )

    mode: bpy.props.EnumProperty(
        name="模式",
        items=[
            ('CUBE', "三平面", ""),
            ('PLANE', "平面", ""),
            ('SPHERE', "球体", ""),
            ('CYLINDER', "圆柱体", ""),
        ],
        default='CUBE')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.target_obj = None
        self.temp_gizmo = None
        self.engine = None
        self._depsgraph_handle = None
        self._modal_border_handle = None
        self.last_matrix = None
        self._prev_mode = None

    def _is_alive(self, context):
        try:
            if not self.target_obj or not self.temp_gizmo:
                return False
            _ = self.target_obj.name
            if context.mode != 'OBJECT':
                return False
            return True
        except Exception:
            return False

    def _update_engine(self, context, new_mode):
        try:
            old_rotation = None
            if self.temp_gizmo:
                try:
                    old_rotation = self.temp_gizmo.rotation_euler.copy()
                    bpy.data.objects.remove(self.temp_gizmo, do_unlink=True)
                except Exception:
                    pass

            self.mode = new_mode
            self.engine = UVEngineFactory.get_engine(new_mode)

            self.engine.create_gizmo()
            self.temp_gizmo = context.active_object
            self.temp_gizmo.name = f"UV_GIZMO_{self.mode}"

            if old_rotation is not None:
                self.temp_gizmo.rotation_euler = old_rotation

            self.temp_gizmo.display_type = 'WIRE'
            self.temp_gizmo.show_in_front = True
            self.temp_gizmo.hide_render = True

            context.view_layer.update()
            self._fit_to_object()
            self.last_matrix = None
            self.report({'INFO'}, f"引擎切换至: {new_mode}")
        except Exception:
            traceback.print_exc()

    def _fit_to_object(self):
        if not self._is_alive(bpy.context):
            return
        mesh = self.target_obj.data
        verts = np.empty(len(mesh.vertices) * 3, dtype=np.float32)
        mesh.vertices.foreach_get('co', verts)
        verts.shape = (-1, 3)

        gizmo_q = self.temp_gizmo.matrix_world.to_quaternion()
        rot_mat = gizmo_q.to_matrix().to_4x4()
        inv_rot_mat = rot_mat.inverted()
        mat = inv_rot_mat @ self.target_obj.matrix_world

        local_coords = (verts @ np.array(mat.to_3x3().transposed())) + np.array(mat.translation)
        min_p, max_p = np.min(local_coords, axis=0), np.max(local_coords, axis=0)

        self.temp_gizmo.location = rot_mat @ mathutils.Vector((min_p + max_p) / 2)
        self.engine.apply_scale(self.temp_gizmo, (max_p - min_p) / 2)

    def _update_uv(self, context):
        try:
            if not self._is_alive(context):
                return
            curr_mat = self.temp_gizmo.matrix_world.copy()
            if self.last_matrix is not None and curr_mat == self.last_matrix:
                return
            self.last_matrix = curr_mat

            mesh = self.target_obj.data
            uv_layer = mesh.uv_layers.active.data if mesh.uv_layers else mesh.uv_layers.new().data

            m_inv_gizmo = curr_mat.inverted()
            mat = m_inv_gizmo @ self.target_obj.matrix_world

            verts = np.empty(len(mesh.vertices) * 3, dtype=np.float32)
            mesh.vertices.foreach_get('co', verts)
            verts.shape = (-1, 3)

            loop_vert_idx = np.empty(len(mesh.loops), dtype=np.int32)
            mesh.loops.foreach_get('vertex_index', loop_vert_idx)

            p = (verts[loop_vert_idx] @ np.array(mat.to_3x3().transposed())) + np.array(mat.translation)

            mat_n = np.array((m_inv_gizmo.to_3x3() @ self.target_obj.matrix_world.to_3x3()).transposed())
            face_normals = np.empty(len(mesh.polygons) * 3, dtype=np.float32)
            mesh.polygons.foreach_get('normal', face_normals)
            face_normals.shape = (-1, 3)

            loop_totals = np.empty(len(mesh.polygons), dtype=np.int32)
            mesh.polygons.foreach_get('loop_total', loop_totals)
            n = np.repeat(face_normals @ mat_n, loop_totals, axis=0)

            uvs = self.engine.calculate_uv(p, n)
            uv_layer.foreach_set("uv", uvs.flatten())
            mesh.update()
        except ReferenceError:
            pass
        except Exception:
            traceback.print_exc()

    def invoke(self, context, event):
        try:
            if BetterExperie_OT_VisualUVProjection._instance:
                BetterExperie_OT_VisualUVProjection._instance._update_engine(context, self.mode)
                return {'CANCELLED'}

            if not context.active_object or context.active_object.type != 'MESH':
                self.report({'WARNING'}, "请先选中一个网格物体")
                return {'CANCELLED'}

            self._prev_mode = context.mode
            if context.mode != 'OBJECT':
                bpy.ops.object.mode_set(mode='OBJECT')

            self.target_obj = context.active_object
            BetterExperie_OT_VisualUVProjection._instance = self

            self._update_engine(context, self.mode)

            def cb(scene, dg):
                try:
                    self._update_uv(bpy.context)
                except Exception:
                    pass
            self._depsgraph_handle = cb
            bpy.app.handlers.depsgraph_update_post.append(self._depsgraph_handle)

            add_modal_border(self, context)

            context.window_manager.modal_handler_add(self)
            context.workspace.status_text_set("可视化 UV 投射 | Tab切换模式 | F适配物体 | ESC退出")
            return {'RUNNING_MODAL'}
        except Exception:
            self._cleanup(context)
            return {'CANCELLED'}

    def modal(self, context, event):
        try:
            if not self._is_alive(context):
                self._cleanup(context)
                return {'FINISHED'}

            context.area.tag_redraw()

            if event.type == 'TAB' and event.value == 'PRESS':
                modes = ['CUBE', 'PLANE', 'SPHERE', 'CYLINDER']
                try:
                    curr_idx = modes.index(self.mode)
                except ValueError:
                    curr_idx = 0
                next_mode = modes[(curr_idx + 1) % len(modes)]
                self._update_engine(context, next_mode)
                return {'RUNNING_MODAL'}

            elif event.type == 'F' and event.value == 'PRESS':
                self._fit_to_object()
                return {'RUNNING_MODAL'}

            elif event.type in {'ESC', 'RIGHTMOUSE'}:
                self._cleanup(context)
                return {'CANCELLED'}

            return {'PASS_THROUGH'}
        except Exception:
            traceback.print_exc()
            self._cleanup(context)
            return {'CANCELLED'}

    def _cleanup(self, context):
        BetterExperie_OT_VisualUVProjection._instance = None
        if self._depsgraph_handle and self._depsgraph_handle in bpy.app.handlers.depsgraph_update_post:
            bpy.app.handlers.depsgraph_update_post.remove(self._depsgraph_handle)
        remove_modal_border(self)
        if self.temp_gizmo:
            try:
                bpy.data.objects.remove(self.temp_gizmo, do_unlink=True)
            except Exception:
                pass
        if self.target_obj:
            try:
                context.view_layer.objects.active = self.target_obj
                if self._prev_mode and self._prev_mode != 'OBJECT':
                    bpy.ops.object.mode_set(mode=self._prev_mode)
            except Exception:
                pass
        if context and context.window:
            context.workspace.status_text_set(None)


# ═══════════════════════════════════════════════════════════════
# 下拉菜单
# ═══════════════════════════════════════════════════════════════

class BETTER_EXPERIE_MT_visual_uv_projection(bpy.types.Menu):
    bl_label = "可视化 UV 投射"
    bl_idname = "BETTER_EXPERIE_MT_visual_uv_projection"

    def draw(self, context):
        layout = self.layout
        for m_type, m_name, m_icon in [
            ('CUBE', "三平面", 'CUBE'),
            ('PLANE', "平面", 'MESH_PLANE'),
            ('SPHERE', "球体", 'MESH_UVSPHERE'),
            ('CYLINDER', "圆柱体", 'MESH_CYLINDER'),
        ]:
            op = layout.operator("better_experie.visual_uv_projection", text=m_name, icon=m_icon)
            op.mode = m_type


def draw_uv_menu(self, context):
    self.layout.separator()
    self.layout.menu("BETTER_EXPERIE_MT_visual_uv_projection")


classes = (
    BetterExperie_OT_VisualUVProjection,
    BETTER_EXPERIE_MT_visual_uv_projection,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.VIEW3D_MT_uv_map.append(draw_uv_menu)
    bpy.types.VIEW3D_MT_object.append(draw_uv_menu)

def unregister():
    bpy.types.VIEW3D_MT_uv_map.remove(draw_uv_menu)
    bpy.types.VIEW3D_MT_object.remove(draw_uv_menu)
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
