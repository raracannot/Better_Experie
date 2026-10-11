# 变换朝向工具：读取场景当前变换朝向槽（transform_orientation_slots[0]）并转为 3x3 矩阵
# 供多个算子 / 模态共用

import bmesh
from mathutils import Matrix, Vector


def local_orientation(obj):
    """物体局部朝向（3x3）；无物体时返回单位矩阵"""
    if obj is not None:
        return obj.matrix_world.to_3x3().normalized()
    return Matrix.Identity(3)


def normal_orientation(context):
    """从选中面 / 顶点法线构建 Normal 朝向（近似原生）"""
    try:
        obj = context.edit_object
        if obj and obj.type == 'MESH':
            bm = bmesh.from_edit_mesh(obj.data)
            normals = [f.normal for f in bm.faces if f.select]
            if not normals:
                normals = [v.normal for v in bm.verts if v.select]
            if normals:
                normal = Vector()
                for item in normals:
                    normal = normal + item
                normal.normalize()
                if normal.length > 1e-6:
                    world3 = obj.matrix_world.to_3x3()
                    normal = (world3.inverted().transposed() @ normal).normalized()
                    up = Vector((0.0, 0.0, 1.0))
                    if abs(normal.dot(up)) > 0.99:
                        up = Vector((0.0, 1.0, 0.0))
                    axis_x = up.cross(normal).normalized()
                    axis_y = normal.cross(axis_x)
                    return Matrix((axis_x, axis_y, normal)).transposed()
    except Exception:
        pass
    return Matrix.Identity(3)


def slot_orientation(context, obj=None, view=None):
    """读取场景当前变换朝向（transform_orientation_slots[0]）并转成 3x3 矩阵

    obj  : 用于 LOCAL / GIMBAL / PARENT 的物体；None 时自动取活动/编辑物体
    view : RegionView3D（VIEW 朝向优先用它）；None 时回退到扫描 VIEW_3D 区域
    """
    try:
        slot = context.scene.transform_orientation_slots[0]
        if obj is None:
            obj = getattr(context, "active_object", None) or getattr(context, "edit_object", None)
        orient_type = slot.type

        if orient_type == 'GLOBAL':
            return Matrix.Identity(3)
        if orient_type in {'LOCAL', 'GIMBAL'}:
            return local_orientation(obj)
        if orient_type == 'NORMAL':
            return normal_orientation(context)
        if orient_type == 'VIEW':
            if view is not None:
                return view.view_rotation.to_matrix()
            screen = getattr(context, "screen", None)
            if screen is not None:
                for area in screen.areas:
                    if area.type == 'VIEW_3D':
                        return area.spaces[0].region_3d.view_matrix.inverted().to_3x3()
            return Matrix.Identity(3)
        if orient_type == 'CURSOR':
            return context.scene.cursor.matrix.to_3x3()
        if orient_type == 'PARENT':
            return obj.parent.matrix_world.to_3x3().normalized() if (obj and obj.parent) else Matrix.Identity(3)

        custom = slot.custom_orientation
        if custom is not None:
            return custom.matrix.to_3x3()
    except Exception:
        return Matrix.Identity(3)
    return Matrix.Identity(3)
