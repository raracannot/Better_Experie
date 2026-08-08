# 模态持续融并顶点工具，GPU可视化预览，Tab切换融并模式

import bpy
import gpu
import math
import bmesh
import mathutils
import traceback
import datetime
from bpy_extras import view3d_utils
from gpu_extras.batch import batch_for_shader
from ...utils.modal_border import add_modal_border, remove_modal_border

class BetterExperie_OT_ModalWeld(bpy.types.Operator):
    bl_idname = "better_experie.modal_weld"
    bl_label = "持续顶点融并"
    bl_description = "可视化持续融并距离最近的顶点，支持Tab切换模式（中心/A→B/B→A）"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        obj = context.edit_object
        return obj and obj.type == 'MESH' and context.mode == 'EDIT_MESH'

    def invoke(self, context, event):

        try:
            if not self.poll(context):
                self.report({'WARNING'}, "必须在网格编辑模式下运行")
                return {'CANCELLED'}

            obj = context.edit_object

            self.draw_handle = None
            self._modal_border_handle = None
            self.vert_closest = None
            self.vert_target = None
            self.mouse_pos = (0, 0)
            self.merge_mode = 0
            self.mode_names = ["中心", "A -> B (最近到次近)", "B -> A (次近到最近)"]

            self.obj = obj
            self.bm = bmesh.from_edit_mesh(obj.data)

            # 初始化历史记录列表
            self.history = []
            self.redo_history = []
            
            if not self.bm.faces:
                self.report({'WARNING'}, "网格没有面，无法进行融并操作")
                return {'CANCELLED'}

            self._update_trees()

            args = (self, context)
            self.draw_handle = bpy.types.SpaceView3D.draw_handler_add(
                self._draw_callback, args, 'WINDOW', 'POST_PIXEL'
            )
            add_modal_border(self, context)

            context.window_manager.modal_handler_add(self)
            context.workspace.status_text_set(
                "顶点融并 | Tab切换模式 | 左键融并 | Ctrl+Z撤销 Ctrl+Shift+Z重做 | 右键/ESC退出")
            self.report({'INFO'}, f"进入顶点融并模态 | 当前模式: {self.mode_names[self.merge_mode]} | Tab切换 | ESC退出")
            return {'RUNNING_MODAL'}
        except Exception:
            self.report({'ERROR'}, traceback.format_exc())
            try:
                self._cleanup(context)
            except Exception:
                pass
            return {'CANCELLED'}

    def _update_trees(self):
        self.bm.verts.ensure_lookup_table()
        self.bm.faces.ensure_lookup_table()
        self.bvh = mathutils.bvhtree.BVHTree.FromBMesh(self.bm)
        visible_verts = [v for v in self.bm.verts if not v.hide]
        size = len(visible_verts)
        self.kdtree = mathutils.kdtree.KDTree(size)
        for v in visible_verts:
            self.kdtree.insert(v.co, v.index)
        self.kdtree.balance()

    def _create_mesh_backup(self):
        """直接从当前的 BMesh 生成一个全新的 Mesh 数据块作为备份"""
        now = datetime.datetime.now()
        backup_name = f"{self.obj.data.name}_bak_{now.strftime('%Y%m%d_%H%M%S_%f')}"
        
        # 新建一个空的网格数据块
        backup_mesh = bpy.data.meshes.new(backup_name)
        
        # 将当前真实的 BMesh 状态直接写入这个新网格中（完美保留所有数据）
        self.bm.to_mesh(backup_mesh)
        
        return backup_mesh


    def _restore_mesh_backup(self, backup_mesh):
        """使用底层from_mesh完美恢复所有数据(包含UV/权重等)"""
        self.bm.clear()
        self.bm.from_mesh(backup_mesh)
        self.bm.normal_update()
        bmesh.update_edit_mesh(self.obj.data, loop_triangles=True, destructive=True)
        self.obj.data.update()
        self._update_trees()

    def _delete_backup_mesh(self, mesh):
        """安全删除备份数据块"""
        if mesh and mesh.name in bpy.data.meshes:
            bpy.data.meshes.remove(mesh)



    def modal(self, context, event):
        try:
            if context.area:
                context.area.tag_redraw()

            # Ctrl + Z
            if (event.type == 'Z' and event.value == 'PRESS' and event.ctrl and not event.shift):
                if self.history:
                    redo_backup = self._create_mesh_backup()
                    self.redo_history.append(redo_backup)
                    if len(self.redo_history) > 5:
                        old = self.redo_history.pop(0)
                        self._delete_backup_mesh(old)
                    undo_backup = self.history.pop()
                    self._restore_mesh_backup(undo_backup)
                    # 注意：这里绝对不能 delete undo_backup，否则会撤回过头或崩溃
                    self.vert_closest = None
                    self.vert_target = None
                    self.report({'INFO'}, "模态内撤销成功")
                else:
                    self.report({'WARNING'}, "没有更多撤销记录")
                return {'RUNNING_MODAL'}


            # Ctrl + Shift + Z
            if (event.type == 'Z' and event.value == 'PRESS' and event.ctrl and event.shift):
                if self.redo_history:
                    undo_backup = self._create_mesh_backup()
                    self.history.append(undo_backup)
                    if len(self.history) > 5:
                        old = self.history.pop(0)
                        self._delete_backup_mesh(old)
                    redo_backup = self.redo_history.pop()
                    self._restore_mesh_backup(redo_backup)
                    # 注意：这里绝对不能 delete redo_backup
                    self.vert_closest = None
                    self.vert_target = None
                    self.report({'INFO'}, "模态内重做成功")
                else:
                    self.report({'WARNING'}, "没有更多重做记录")
                return {'RUNNING_MODAL'}



            if event.type in {'ESC', 'RIGHTMOUSE'}:
                self._cleanup(context)
                self.report({'INFO'}, "退出融并模态")
                return {'CANCELLED'}

            if event.type == 'TAB' and event.value == 'PRESS':
                self.merge_mode = (self.merge_mode + 1) % 3
                self.report({'INFO'}, f"当前融并模式: {self.mode_names[self.merge_mode]}，红色为位置预览")
                return {'RUNNING_MODAL'}

            if event.type == 'MOUSEMOVE':
                self.mouse_pos = (event.mouse_region_x, event.mouse_region_y)
                self._find_targets(context)
                return {'PASS_THROUGH'}

            elif event.type == 'LEFTMOUSE' and event.value == 'PRESS':
                if self.vert_closest and self.vert_target:

                    # --- 融并前记录历史 ---
                    # --- 融并前记录历史 ---
                    backup_mesh = self._create_mesh_backup()
                    self.history.append(backup_mesh)
                    if len(self.history) > 5:
                        old = self.history.pop(0)
                        self._delete_backup_mesh(old)
                    for mesh in self.redo_history:
                        self._delete_backup_mesh(mesh)
                    self.redo_history.clear()

                    if self.merge_mode == 0:
                        target_co = (self.vert_closest.co + self.vert_target.co) / 2.0
                        self.vert_closest.co = target_co
                        self.vert_target.co = target_co
                    elif self.merge_mode == 1:
                        self.vert_closest.co = self.vert_target.co
                    elif self.merge_mode == 2:
                        self.vert_target.co = self.vert_closest.co

                    bmesh.ops.remove_doubles(self.bm, verts=[self.vert_closest, self.vert_target], dist=0.0001)
                    bmesh.update_edit_mesh(self.obj.data)
                    self._update_trees()
                    self.vert_closest = None
                    self.vert_target = None
                return {'RUNNING_MODAL'}

            return {'PASS_THROUGH'}

        except Exception as e:
            self.report({'ERROR'}, f"模态运行出错，已安全退出: {str(e)}")
            print(traceback.format_exc())
            self._cleanup(context)
            return {'CANCELLED'}


    def _find_targets(self, context):
        region = context.region
        rv3d = context.region_data

        ray_origin = view3d_utils.region_2d_to_origin_3d(region, rv3d, self.mouse_pos)
        ray_direction = view3d_utils.region_2d_to_vector_3d(region, rv3d, self.mouse_pos)

        matrix_inv = self.obj.matrix_world.inverted()
        ray_origin_local = matrix_inv @ ray_origin
        ray_direction_local = matrix_inv.to_3x3() @ ray_direction

        self.vert_closest = None
        self.vert_target = None

        if self.bvh and self.bm.faces:
            location, normal, index, distance = self.bvh.ray_cast(ray_origin_local, ray_direction_local)
            if location is not None:
                hit_face = self.bm.faces[index]
                min_dist = float('inf')
                for v in hit_face.verts:
                    if v.hide:
                        continue
                    dist = (v.co - location).length
                    if dist < min_dist:
                        min_dist = dist
                        self.vert_closest = v

                if self.vert_closest:
                    closest_points = self.kdtree.find_n(self.vert_closest.co, 2)
                    for co, idx, dist in closest_points:
                        if idx != self.vert_closest.index:
                            self.vert_target = self.bm.verts[idx]
                            break

    def _draw_callback(self, op, context):
        try:
            if not self.vert_closest and not self.vert_target:
                return

            matrix = self.obj.matrix_world
            region = context.region
            rv3d = context.region_data

            gpu.state.blend_set('ALPHA')

            coord_closest_2d = None
            coord_target_2d = None
            coord_merge_2d = None

            if self.vert_closest:
                coord_closest_2d = view3d_utils.location_3d_to_region_2d(region, rv3d, matrix @ self.vert_closest.co)

            if self.vert_target:
                coord_target_2d = view3d_utils.location_3d_to_region_2d(region, rv3d, matrix @ self.vert_target.co)

            if self.vert_closest and self.vert_target:
                if self.merge_mode == 0:
                    merge_co = matrix @ ((self.vert_closest.co + self.vert_target.co) / 2.0)
                elif self.merge_mode == 1:
                    merge_co = matrix @ self.vert_target.co
                else:
                    merge_co = matrix @ self.vert_closest.co
                coord_merge_2d = view3d_utils.location_3d_to_region_2d(region, rv3d, merge_co)

            if coord_closest_2d and coord_target_2d:
                shader = gpu.shader.from_builtin('SMOOTH_COLOR')
                batch = batch_for_shader(shader, 'LINES', {
                    "pos": [coord_closest_2d, coord_target_2d],
                    "color": [(0.0, 1.0, 1.0, 0.6), (0.0, 1.0, 1.0, 0.6)]
                })
                gpu.state.line_width_set(2.0)
                shader.bind()
                batch.draw(shader)

            blue_color = (0.0, 1.0, 1.0, 1.0)
            red_color = (1.0, 0.0, 0.0, 1.0)

            for coord, color in [(coord_target_2d, blue_color), (coord_closest_2d, blue_color), (coord_merge_2d, red_color)]:
                if coord:
                    vertices = []
                    colors = []
                    segments = 8
                    radius = 6
                    for i in range(segments):
                        a1 = i * (2 * math.pi / segments)
                        a2 = (i + 1) * (2 * math.pi / segments)
                        x1 = coord[0] + radius * math.cos(a1)
                        y1 = coord[1] + radius * math.sin(a1)
                        x2 = coord[0] + radius * math.cos(a2)
                        y2 = coord[1] + radius * math.sin(a2)
                        vertices.extend([coord, (x1, y1), (x2, y2)])
                        colors.extend([color, color, color])
                    shader = gpu.shader.from_builtin('SMOOTH_COLOR')
                    batch = batch_for_shader(shader, 'TRIS', {"pos": vertices, "color": colors})
                    shader.bind()
                    batch.draw(shader)

            gpu.state.blend_set('NONE')
            
        except Exception as e:
            print(f"绘制回调出错: {e}")
            if op.draw_handle:
                bpy.types.SpaceView3D.draw_handler_remove(op.draw_handle, 'WINDOW')
                op.draw_handle = None


    def _cleanup(self, context=None):
        """安全清理绘制句柄、视口边框、状态栏和备份网格内存"""
        if self.draw_handle:
            try:
                bpy.types.SpaceView3D.draw_handler_remove(self.draw_handle, 'WINDOW')
            except Exception:
                pass
            self.draw_handle = None
        remove_modal_border(self)
        if context and getattr(context, 'workspace', None):
            try:
                context.workspace.status_text_set(None)
            except Exception:
                pass
        if hasattr(self, 'history'):
            for mesh in self.history:
                self._delete_backup_mesh(mesh)
            self.history.clear()
        if hasattr(self, 'redo_history'):
            for mesh in self.redo_history:
                self._delete_backup_mesh(mesh)
            self.redo_history.clear()


class BetterExperie_OT_InvokeModalWeld(bpy.types.Operator):
    bl_idname = "better_experie.invoke_modal_weld"
    bl_label = "持续顶点融并"
    bl_description = "可视化持续融并距离最近的顶点，支持Tab切换模式（中心/A→B/B→A）"
    bl_options = {'REGISTER'}
    
    #MT不支持直接启用底层带模态的ops，我们需要用一个普通ops包裹带模态ops
    def execute(self, context):
        bpy.ops.better_experie.modal_weld('INVOKE_DEFAULT')
        return {'FINISHED'}



classes = (
    BetterExperie_OT_ModalWeld,
    BetterExperie_OT_InvokeModalWeld,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
