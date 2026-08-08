# 镜像选中的物体对象

import bpy
import gpu
import time
from gpu_extras.batch import batch_for_shader
from bpy.types import Operator
from mathutils import Matrix, Vector


def _get_region_rv3d(context):
    region = getattr(context, "region", None)
    rv3d = getattr(context, "space_data", None)
    if rv3d and rv3d.type == 'VIEW_3D':
        rv3d = rv3d.region_3d
    return region, rv3d


class MirrorVisualizer:
    _handler = None
    _timer = None
    _start_time = 0.0
    _duration = 1.5
    _pivot = Vector()
    _rot = Matrix()
    _axis = '0'

    @classmethod
    def start(cls, context, pivot, rot, axis):
        cls.stop()
        cls._start_time = time.time()
        cls._pivot = pivot.copy()
        cls._rot = rot.copy()
        cls._axis = axis
        cls._handler = bpy.types.SpaceView3D.draw_handler_add(
            cls.draw, (context,), 'WINDOW', 'POST_VIEW'
        )
        cls._timer = bpy.app.timers.register(cls.tag_redraw)

    @classmethod
    def stop(cls):
        if cls._handler:
            bpy.types.SpaceView3D.draw_handler_remove(cls._handler, 'WINDOW')
            cls._handler = None
        if cls._timer and bpy.app.timers.is_registered(cls.tag_redraw):
            bpy.app.timers.unregister(cls.tag_redraw)
            cls._timer = None

    @classmethod
    def tag_redraw(cls):
        if time.time() - cls._start_time > cls._duration:
            cls.stop()
            return None
        for window in bpy.context.window_manager.windows:
            for area in window.screen.areas:
                if area.type == 'VIEW_3D':
                    area.tag_redraw()
        return 0.03

    @classmethod
    def draw(cls, context):
        elapsed = time.time() - cls._start_time
        if elapsed > cls._duration:
            return

        t = elapsed / cls._duration
        alpha = (1.0 - t) * 0.9

        gpu.state.blend_set('ALPHA')
        gpu.state.line_width_set(3.0)

        size = 2.0
        center = cls._pivot
        rot_mat = cls._rot.to_3x3()

        x_end = center + rot_mat @ Vector((size, 0, 0))
        y_end = center + rot_mat @ Vector((0, size, 0))
        z_end = center + rot_mat @ Vector((0, 0, size))

        x_start = center - rot_mat @ Vector((size, 0, 0))
        y_start = center - rot_mat @ Vector((0, size, 0))
        z_start = center - rot_mat @ Vector((0, 0, size))

        coords = [x_start, x_end, y_start, y_end, z_start, z_end]

        c_x = (1.0, 0.2, 0.2, alpha if cls._axis == '0' else alpha * 0.15)
        c_y = (0.2, 1.0, 0.2, alpha if cls._axis == '1' else alpha * 0.15)
        c_z = (0.2, 0.5, 1.0, alpha if cls._axis == '2' else alpha * 0.15)

        colors = [c_x, c_x, c_y, c_y, c_z, c_z]

        shader = gpu.shader.from_builtin('SMOOTH_COLOR')
        batch = batch_for_shader(shader, 'LINES', {"pos": coords, "color": colors})

        shader.bind()
        batch.draw(shader)

        gpu.state.blend_set('NONE')
        gpu.state.line_width_set(1.0)


class BetterExperie_OT_ObjectMirror(Operator):
    bl_idname = "better_experie.object_mirror"
    bl_label = "镜像选中的物体对象"
    bl_description = "以指定的坐标系和轴心，镜像选中的对象"
    bl_options = {'REGISTER', 'UNDO'}

    mirror_axis: bpy.props.EnumProperty(
        name="镜像轴向",
        description="选择进行镜像的轴向",
        items=[
            ('0', "X轴", "沿X轴镜像"),
            ('1', "Y轴", "沿Y轴镜像"),
            ('2', "Z轴", "沿Z轴镜像"),
        ],
        default='0'
    )

    coord_sys: bpy.props.EnumProperty(
        name="坐标系 (朝向)",
        description="决定镜像平面的旋转朝向",
        items=[
            ('GLOBAL', "全局坐标", "使用世界全局坐标系"),
            ('CURSOR', "3D游标", "使用3D游标的旋转朝向"),
            ('VIEW', "视图旋转", "使用当前视角的朝向"),
            None,
            ('LOCAL', "活动物体", "使用当前活动物体的旋转朝向"),
        ],
        default='CURSOR'
    )

    pivot_point: bpy.props.EnumProperty(
        name="镜像轴心 (位置)",
        description="决定镜像平面的中心位置",
        items=[
            ('GLOBAL', "全局原点", "以世界中心(0,0,0)为轴心"),
            ('CURSOR', "3D游标", "以3D游标的位置为轴心"),
            None,
            ('LOCAL', "活动物体", "以当前活动物体的位置为轴心"),
        ],
        default='CURSOR'
    )

    copy_mode: bpy.props.EnumProperty(
        name="复制方式",
        description="选择镜像副本的类型",
        items=[
            ('DUPLICATE', "复制", "创建独立副本，网格数据物理镜像"),
            ('LINKED', "关联复制", "共享数据块，通过变换实现镜像（保留原始数据关联）"),
        ],
        default='DUPLICATE'
    )

    exclude_active: bpy.props.BoolProperty(
        name="排除活动参考物体",
        description="当使用活动物体作为坐标系或轴心时，不镜像复制活动物体本身",
        default=True
    )

    @staticmethod
    def build_mirror_transform(pivot_loc, orient_rot, axis_index):
        m_pivot = Matrix.Translation(pivot_loc) @ orient_rot.to_4x4()
        m_pivot_inv = m_pivot.inverted()

        scale_world = [1.0, 1.0, 1.0, 1.0]
        scale_world[axis_index] = -1.0
        s_mirror = Matrix.Diagonal(scale_world)

        return m_pivot @ s_mirror @ m_pivot_inv

    @classmethod
    def poll(cls, context):
        area = getattr(context, "area", None)
        region, rv3d = _get_region_rv3d(context)
        return (
            area and area.type == 'VIEW_3D' and region and rv3d and
            context.mode == 'OBJECT'
        )

    def draw(self, context):
        layout = self.layout
        col = layout.column()

        col.prop(self, "mirror_axis")
        col.prop(self, "coord_sys")
        col.prop(self, "pivot_point")

        if self.coord_sys == 'LOCAL' or self.pivot_point == 'LOCAL':
            col.separator()
            col.prop(self, "exclude_active")

        col.separator()
        col.prop(self, "copy_mode")

    def execute(self, context):
        context.view_layer.update()

        area = getattr(context, "area", None)
        region, rv3d = _get_region_rv3d(context)
        if not (area and area.type == 'VIEW_3D' and region and rv3d):
            return {'PASS_THROUGH'}

        objs = [obj for obj in context.selected_objects if obj]
        original_active = context.active_object

        if not objs:
            self.report({'WARNING'}, "未选中任何对象")
            return {'CANCELLED'}

        if self.exclude_active and original_active in objs:
            if self.coord_sys == 'LOCAL' or self.pivot_point == 'LOCAL':
                objs.remove(original_active)

        if not objs:
            self.report({'WARNING'}, "只有参考物体被选中，没有需要镜像的其他对象")
            return {'CANCELLED'}

        if self.coord_sys == 'GLOBAL':
            orient_rot = Matrix.Identity(4)
        elif self.coord_sys == 'LOCAL':
            orient_rot = original_active.matrix_world.to_3x3().to_4x4() if original_active else Matrix.Identity(4)
        elif self.coord_sys == 'CURSOR':
            orient_rot = context.scene.cursor.matrix.to_3x3().to_4x4()
        elif self.coord_sys == 'VIEW':
            orient_rot = rv3d.view_matrix.inverted().to_3x3().to_4x4()

        if self.pivot_point == 'GLOBAL':
            pivot_loc = Vector((0.0, 0.0, 0.0))
        elif self.pivot_point == 'LOCAL':
            pivot_loc = original_active.matrix_world.translation if original_active else Vector((0.0, 0.0, 0.0))
        elif self.pivot_point == 'CURSOR':
            pivot_loc = context.scene.cursor.location

        MirrorVisualizer.start(context, pivot_loc, orient_rot, self.mirror_axis)

        for obj in list(context.selected_objects):
            try:
                obj.select_set(False)
            except Exception:
                pass

        axis_index = int(self.mirror_axis)
        t_mirror_world = self.build_mirror_transform(pivot_loc, orient_rot, axis_index)
        is_duplicate = self.copy_mode == 'DUPLICATE'

        new_objects = []

        for src in objs:
            src_matrix = src.matrix_world.copy()

            new_obj = src.copy()
            new_obj.name = src.name + "_镜像"

            if is_duplicate and src.data is not None:
                new_obj.data = src.data.copy()

            if src.users_collection:
                for coll in src.users_collection:
                    coll.objects.link(new_obj)
            else:
                context.scene.collection.objects.link(new_obj)

            new_obj.matrix_world = t_mirror_world @ src_matrix
            new_obj.select_set(True)
            new_objects.append(new_obj)

        if is_duplicate:
            saved_active = context.view_layer.objects.active
            for new_obj in new_objects:
                if new_obj.type != 'MESH':
                    continue
                context.view_layer.objects.active = new_obj
                bpy.ops.object.transform_apply(
                    location=False, rotation=True, scale=True,
                    isolate_users=False
                )
                bpy.ops.object.mode_set(mode='EDIT')
                bpy.ops.mesh.select_all(action='SELECT')
                bpy.ops.mesh.normals_make_consistent(inside=False)
                bpy.ops.object.mode_set(mode='OBJECT')
            context.view_layer.objects.active = saved_active

        if new_objects:
            if original_active:
                context.view_layer.objects.active = original_active
                if self.exclude_active and (self.coord_sys == 'LOCAL' or self.pivot_point == 'LOCAL'):
                    original_active.select_set(True)
            else:
                context.view_layer.objects.active = new_objects[-1]

            context.view_layer.update()
            self.report({'INFO'}, f"成功镜像了 {len(new_objects)} 个对象")

        return {'FINISHED'}


classes = (
    BetterExperie_OT_ObjectMirror,
)



def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    MirrorVisualizer.stop()
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
