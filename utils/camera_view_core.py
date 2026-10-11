# 相机「平整 / 镜像」共用的几何算法（移轴 / Shift 原理）
# 参考自 Flatten View (平整视图) by DSH

import math

from bpy_extras.object_utils import world_to_camera_view
from mathutils import Matrix, Vector

REFERENCE_ITEMS = (
    ('WORLD_Z', "世界 Z（竖直）",
     "以世界 Z 轴为参考：产品立在水平面上时，它的竖直边在画面中平行"),
    ('CAMERA_UP', "相机 up",
     "以相机的 up 方向为参考：镜面 / 参考面随相机倾斜，产品相对相机保持竖直"),
    ('LOCAL_Z', "物体局部 Z",
     "以主物体的局部 Z 轴为参考：适合产品本身是倾斜摆放的情况"),
)


class FlattenError(Exception):
    """可以直接展示给用户的错误"""


# ============================== 场景取样 ==============================

def mesh_objects(context):
    """当前选中的网格物体（镜像 / 平整的轴心来源，必须至少选中一个）"""
    return [ob for ob in context.selected_objects if ob.type == 'MESH']


def primary_object(context):
    """取主物体（选中网格的第一个），用于提取局部轴"""
    meshes = mesh_objects(context)
    return meshes[0] if meshes else None


def bounds_of(objs):
    """所有物体世界包围盒的合并 (min, max)"""
    lo = Vector((math.inf, math.inf, math.inf))
    hi = Vector((-math.inf, -math.inf, -math.inf))
    found = False
    for ob in objs:
        matrix = ob.matrix_world
        for corner in ob.bound_box:
            point = matrix @ Vector(corner)
            for axis in range(3):
                if point[axis] < lo[axis]:
                    lo[axis] = point[axis]
                if point[axis] > hi[axis]:
                    hi[axis] = point[axis]
            found = True
    if not found:
        raise FlattenError("场景里没有网格物体，无法确定锚点")
    return lo, hi


def anchor_point(context):
    """轴心 = 选中网格物体包围盒的中心。返回 (点, 来源说明)；未选中网格则报错"""
    objs = mesh_objects(context)
    if not objs:
        raise FlattenError("请先选中至少一个网格物体作为轴心")
    lo, hi = bounds_of(objs)
    source = "选中物体" if len(objs) == 1 else "选中的 %d 个网格" % len(objs)
    return (lo + hi) * 0.5, source


def reference_direction(context, axis):
    """参考方向（世界空间单位向量）与来源说明"""
    if axis == 'CAMERA_UP':
        cam = context.scene.camera
        if cam is None:
            raise FlattenError("场景里没有活动相机")
        direction = cam.matrix_world.to_3x3() @ Vector((0.0, 1.0, 0.0))
        if direction.length < 1e-9:
            raise FlattenError("相机 up 方向长度为 0")
        return direction.normalized(), "相机 up"
    if axis == 'LOCAL_Z':
        ob = primary_object(context)
        if ob is None:
            raise FlattenError("没有选中的网格物体来取局部 Z 轴")
        direction = ob.matrix_world.to_3x3() @ Vector((0.0, 0.0, 1.0))
        if direction.length < 1e-9:
            raise FlattenError("主物体的局部 Z 轴长度为 0")
        return direction.normalized(), "物体「%s」的局部 Z" % ob.name
    return Vector((0.0, 0.0, 1.0)), "世界 Z（竖直）"


def horizontalize(vector, up):
    """把向量投影到 ⟂ up 的水平面；退化（与 up 近平行）时返回 None"""
    v = vector - up * up.dot(vector)
    return v.normalized() if v.length > 1e-6 else None


# ============================== 平整 ==============================

def optical_axis(cam_obj):
    """相机光轴（世界空间单位向量，指向拍摄方向）"""
    return (cam_obj.matrix_world.to_3x3() @ Vector((0.0, 0.0, -1.0))).normalized()


def optical_axis_angle(cam_obj, direction):
    """光轴与参考方向的夹角（度，0–90）。校正后应为 90°"""
    dot = abs(optical_axis(cam_obj).dot(direction.normalized()))
    return math.degrees(math.acos(max(-1.0, min(1.0, dot))))


def flatten_rotation(cam_obj, direction):
    """把光轴摆平到 ⟂ direction 之后，相机应有的 3x3 旋转"""
    axis = optical_axis(cam_obj)
    direction = direction.normalized()

    flattened = axis - direction * direction.dot(axis)
    if flattened.length < 1e-4:
        raise FlattenError("相机光轴几乎与参考方向平行（例如垂直俯拍），无法确定水平方向")
    forward = flattened.normalized()

    z_axis = -forward
    y_axis = direction
    x_axis = y_axis.cross(z_axis)
    if x_axis.length < 1e-6:
        raise FlattenError("参考方向与相机光轴几乎重合，无法构造相机朝向")
    x_axis.normalize()
    y_axis = z_axis.cross(x_axis).normalized()

    return Matrix((
        (x_axis.x, y_axis.x, z_axis.x),
        (x_axis.y, y_axis.y, z_axis.y),
        (x_axis.z, y_axis.z, z_axis.z),
    ))


_PROBE = 0.01


def solve_shift_for(scene, cam_obj, new_matrix, anchor, target):
    """给定相机的新变换矩阵，求 shift_x / shift_y 使 anchor 落在 target（NDC）；退出时相机保持原样"""
    cam_data = cam_obj.data
    original_matrix = cam_obj.matrix_world.copy()
    original_shift = (cam_data.shift_x, cam_data.shift_y)
    try:
        cam_obj.matrix_world = new_matrix
        cam_data.shift_x = 0.0
        cam_data.shift_y = 0.0
        u1, v1, _ = world_to_camera_view(scene, cam_obj, anchor)

        # 探测 shift 的灵敏度（数值法，避免手写投影公式带来的符号错误）
        cam_data.shift_x = _PROBE
        ux, _, _ = world_to_camera_view(scene, cam_obj, anchor)
        cam_data.shift_x = 0.0
        cam_data.shift_y = _PROBE
        _, vy, _ = world_to_camera_view(scene, cam_obj, anchor)
        cam_data.shift_y = 0.0

        kx = (ux - u1) / _PROBE
        ky = (vy - v1) / _PROBE
        if abs(kx) < 1e-9 or abs(ky) < 1e-9:
            raise FlattenError("相机参数异常，无法求解镜头偏移")
        return (target[0] - u1) / kx, (target[1] - v1) / ky
    finally:
        cam_obj.matrix_world = original_matrix
        cam_data.shift_x = original_shift[0]
        cam_data.shift_y = original_shift[1]


def solve_shift(scene, cam_obj, rotation, anchor):
    """在新旋转下求解 shift_x / shift_y，使锚点的画面坐标与原来一致"""
    original_matrix = cam_obj.matrix_world.copy()
    u0, v0, _ = world_to_camera_view(scene, cam_obj, anchor)
    new_matrix = Matrix.Translation(original_matrix.to_translation()) @ rotation.to_4x4()
    shift_x, shift_y = solve_shift_for(scene, cam_obj, new_matrix, anchor, (u0, v0))
    return shift_x, shift_y, new_matrix


def apply_flatten(context, axis):
    """执行平整。成功返回信息字典，失败抛 FlattenError"""
    scene = context.scene
    cam_obj = scene.camera
    if cam_obj is None:
        raise FlattenError("场景里没有活动相机")
    if cam_obj.data.type != 'PERSP':
        raise FlattenError("只支持透视相机：正交相机不会产生透视收敛")

    anchor, anchor_source = anchor_point(context)
    direction, axis_source = reference_direction(context, axis)
    angle_before = optical_axis_angle(cam_obj, direction)

    rotation = flatten_rotation(cam_obj, direction)
    shift_x, shift_y, new_matrix = solve_shift(scene, cam_obj, rotation, anchor)

    cam_obj.matrix_world = new_matrix
    cam_obj.data.shift_x = shift_x
    cam_obj.data.shift_y = shift_y

    return {
        "axis_source": axis_source,
        "anchor_source": anchor_source,
        "angle_before": angle_before,
    }


# ============================== 镜像 ==============================

# 反射会把右手系变成左手系，所以镜像朝向之后要把相机的右轴取反补回来
_FLIP_RIGHT = Matrix(((-1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)))


def reflection_matrix(normal):
    """关于「过原点、法线为 normal」的平面做镜像的 3x3 矩阵（Householder）"""
    x, y, z = normal.normalized()
    return Matrix((
        (1.0 - 2.0 * x * x, -2.0 * x * y, -2.0 * x * z),
        (-2.0 * y * x, 1.0 - 2.0 * y * y, -2.0 * y * z),
        (-2.0 * z * x, -2.0 * z * y, 1.0 - 2.0 * z * z),
    ))


def mirror_matrix(matrix, anchor, normal):
    """把相机变换关于「过 anchor、法线为 normal 的平面」镜像（位置与朝向一起，保持右手系）"""
    reflection = reflection_matrix(normal)
    location = anchor + reflection @ (matrix.to_translation() - anchor)
    rotation = reflection @ matrix.to_3x3() @ _FLIP_RIGHT
    return Matrix.Translation(location) @ rotation.to_4x4()


def apply_mirror(scene, cam_obj, base_matrix, base_shift, anchor, normal):
    """在 base 位姿基础上，按过 anchor、法线 normal 的平面镜像相机，使锚点画面左右对调

    返回 (new_matrix, shift_x, shift_y)；失败抛 FlattenError。调用后相机停在镜像结果上。
    """
    cam_data = cam_obj.data
    cam_obj.matrix_world = base_matrix
    cam_data.shift_x = base_shift[0]
    cam_data.shift_y = base_shift[1]
    u0, v0, _ = world_to_camera_view(scene, cam_obj, anchor)

    offset = base_matrix.to_translation() - anchor
    if abs(offset.dot(normal)) < 1e-4 * max(offset.length, 1e-6):
        raise FlattenError("相机正对镜面（左右方向几乎没有偏移），镜像后位置不变。请先把相机往左或往右挪一点")

    new_matrix = mirror_matrix(base_matrix, anchor, normal)
    shift_x, shift_y = solve_shift_for(scene, cam_obj, new_matrix, anchor, (1.0 - u0, v0))
    cam_obj.matrix_world = new_matrix
    cam_data.shift_x = shift_x
    cam_data.shift_y = shift_y
    return new_matrix, shift_x, shift_y
