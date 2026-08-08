# 移动游标到所选，并支持保存和管理游标快照

import bpy
import bmesh
from mathutils import Vector, Matrix


def _get_selected_points(context):
    mode = context.mode
    points = []
    single_rot = None

    if mode == 'OBJECT':
        for obj in context.selected_objects:
            points.append(obj.matrix_world.translation.copy())
        if len(points) == 1:
            single_rot = context.selected_objects[0].matrix_world.to_quaternion()
        return points, single_rot

    if mode == 'EDIT_MESH':
        obj = context.active_object
        if not obj or obj.type != 'MESH':
            return points, None
        bm = bmesh.from_edit_mesh(obj.data)
        for v in bm.verts:
            if v.select:
                points.append(obj.matrix_world @ v.co.copy())
        return points, None

    if mode == 'EDIT_CURVE':
        obj = context.active_object
        if not obj or obj.type not in ('CURVE', 'SURFACE'):
            return points, None
        for spline in obj.data.splines:
            for bp in spline.bezier_points:
                if bp.select_control_point or bp.select_left_handle or bp.select_right_handle:
                    points.append(obj.matrix_world @ bp.co.copy())
            for pt in spline.points:
                if pt.select:
                    points.append(obj.matrix_world @ pt.co.to_3d())
        return points, None

    if mode == 'EDIT_ARMATURE':
        obj = context.active_object
        if not obj or obj.type != 'ARMATURE':
            return points, None
        for bone in obj.data.edit_bones:
            if bone.select_head:
                points.append(obj.matrix_world @ bone.head.copy())
            elif bone.select:
                points.append(obj.matrix_world @ bone.head.copy())
        return points, None

    if mode == 'EDIT_METABALL':
        obj = context.active_object
        if not obj or obj.type != 'META':
            return points, None
        for elem in obj.data.elements:
            if elem.select:
                points.append(obj.matrix_world @ elem.co.copy())
        return points, None

    if mode == 'EDIT_LATTICE':
        obj = context.active_object
        if not obj or obj.type != 'LATTICE':
            return points, None
        for pt in obj.data.points:
            if pt.select:
                points.append(obj.matrix_world @ pt.co_deform.copy())
        return points, None

    return points, None


def _compute_cursor_rotation(points):
    if len(points) == 0:
        return None, None

    if len(points) == 1:
        return Vector((0, 0, 0)), 'XYZ'

    if len(points) == 2:
        z = (points[1] - points[0]).normalized()
        if z.length < 0.0001:
            return Vector((0, 0, 0)), 'XYZ'
        ref = Vector((0, 0, 1))
        if abs(z.dot(ref)) > 0.999:
            ref = Vector((1, 0, 0))
        x = z.cross(ref).normalized()
        y = z.cross(x)
        rot_mat = Matrix((x, y, z)).transposed().to_4x4()
        return rot_mat.to_euler('XYZ'), 'XYZ'

    # >= 3 points：Z 对齐到平面法线
    normal = Vector((0, 0, 0))
    p0 = points[0]
    p1 = points[1]
    for i in range(2, len(points)):
        normal += (points[i] - p0).cross(points[i] - p1)
    if normal.length < 0.0001:
        return Vector((0, 0, 0)), 'XYZ'
    z = normal.normalized()
    ref = Vector((0, 0, 1))
    if abs(z.dot(ref)) > 0.999:
        ref = Vector((1, 0, 0))
    x = z.cross(ref).normalized()
    y = z.cross(x)
    rot_mat = Matrix((x, y, z)).transposed().to_4x4()
    return rot_mat.to_euler('XYZ'), 'XYZ'


class BetterExperie_CursorSnapshotItem(bpy.types.PropertyGroup):
    name: bpy.props.StringProperty(name="名称", default="游标快照")
    location: bpy.props.FloatVectorProperty(name="位置", size=3)
    rotation_mode: bpy.props.StringProperty(name="旋转模式", default='XYZ')
    rotation_euler: bpy.props.FloatVectorProperty(name="欧拉旋转", size=3)
    rotation_quaternion: bpy.props.FloatVectorProperty(name="四元数旋转", size=4)


class BetterExperie_OT_CursorToSelected(bpy.types.Operator):
    bl_idname = "better_experie.cursor_to_selected"
    bl_label = "移动游标到所选"
    bl_description = "将 3D 游标移动到选中元素的中心位置，并根据选中数量自动对齐旋转方向"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.area.type == 'VIEW_3D'

    def execute(self, context):
        points, single_rot = _get_selected_points(context)
        if not points:
            self.report({'WARNING'}, "未选中任何元素")
            return {'CANCELLED'}

        center = sum(points, Vector((0, 0, 0))) / len(points)
        context.scene.cursor.location = center

        if single_rot is not None:
            context.scene.cursor.rotation_mode = 'QUATERNION'
            context.scene.cursor.rotation_quaternion = single_rot
        else:
            euler, mode = _compute_cursor_rotation(points)
            if euler is not None:
                context.scene.cursor.rotation_mode = mode
                context.scene.cursor.rotation_euler = euler

        self.report({'INFO'}, f"游标已移至 {len(points)} 个元素的中心")
        return {'FINISHED'}


class BetterExperie_OT_ManageCursorSnapshot(bpy.types.Operator):
    bl_idname = "better_experie.manage_cursor_snapshot"
    bl_label = "管理游标快照"
    bl_description = "保存、恢复或移除 3D 游标快照"
    bl_options = {'UNDO'}

    action: bpy.props.EnumProperty(
        items=[
            ('SAVE', "保存", "保存当前游标状态"),
            ('RESTORE', "恢复", "恢复到此快照"),
            ('REMOVE', "移除", "删除此快照"),
        ],
        name="操作类型"
    )

    index: bpy.props.IntProperty(default=-1)

    def execute(self, context):
        cursor = context.scene.cursor
        snapshots = context.scene.better_experie_cursor_snapshots

        if self.action == 'SAVE':
            new_snap = snapshots.add()
            new_snap.name = f"游标快照 {len(snapshots)}"
            new_snap.location = cursor.location.copy()
            new_snap.rotation_mode = cursor.rotation_mode
            new_snap.rotation_euler = cursor.rotation_euler.copy()
            new_snap.rotation_quaternion = cursor.rotation_quaternion.copy()
            self.report({'INFO'}, f"已保存: {new_snap.name}")

        elif self.action == 'RESTORE':
            if 0 <= self.index < len(snapshots):
                snap = snapshots[self.index]
                cursor.location = snap.location
                cursor.rotation_mode = snap.rotation_mode
                if snap.rotation_mode == 'QUATERNION':
                    cursor.rotation_quaternion = snap.rotation_quaternion
                else:
                    cursor.rotation_euler = snap.rotation_euler
                self.report({'INFO'}, f"已恢复: {snap.name}")

        elif self.action == 'REMOVE':
            if 0 <= self.index < len(snapshots):
                name = snapshots[self.index].name
                snapshots.remove(self.index)
                self.report({'INFO'}, f"已移除: {name}")

        return {'FINISHED'}


def cursor_draw(self, context):
    layout = self.layout
    col = layout.column(align=True)
    row = col.row(align=True)
    row.operator("better_experie.cursor_to_selected", icon='PIVOT_CURSOR')
    op = row.operator("better_experie.manage_cursor_snapshot", text="", icon='ADD')
    op.action = 'SAVE'

    snapshots = context.scene.better_experie_cursor_snapshots
    if len(snapshots) > 0:
        box = layout.box()
        col = box.column(align=True)
        for i, snap in enumerate(snapshots):
            row = col.row(align=True)
            op = row.operator("better_experie.manage_cursor_snapshot", text=snap.name, icon='CURSOR')
            op.action = 'RESTORE'
            op.index = i
            op = row.operator("better_experie.manage_cursor_snapshot", text="", icon='X')
            op.action = 'REMOVE'
            op.index = i


classes = (
    BetterExperie_CursorSnapshotItem,
    BetterExperie_OT_CursorToSelected,
    BetterExperie_OT_ManageCursorSnapshot,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    bpy.types.Scene.better_experie_cursor_snapshots = bpy.props.CollectionProperty(type=BetterExperie_CursorSnapshotItem)
    bpy.types.VIEW3D_PT_view3d_cursor.append(cursor_draw)


def unregister():
    bpy.types.VIEW3D_PT_view3d_cursor.remove(cursor_draw)
    del bpy.types.Scene.better_experie_cursor_snapshots

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
