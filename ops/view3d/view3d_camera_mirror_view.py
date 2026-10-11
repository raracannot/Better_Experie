# 镜像视口：把相机镜像到竖直镜面的另一侧（构图左右对调，产品本身保持真实，
# 文字 / logo 不会反）。镜面过轴心（选中网格的包围盒中心）、包含参考方向，
# 法线取「镜像轴」去掉参考方向分量后的水平方向。
# 一次性执行，可在 F9 重做面板里改「参考方向 / 镜像轴」实时微调。
# 参考自 Flatten View (平整视图) by DSH

import math
import time
import traceback

import bpy
import gpu
from mathutils import Matrix, Vector
from gpu_extras.batch import batch_for_shader
from bpy.props import EnumProperty, FloatVectorProperty

from ...utils.camera_view_core import (
    FlattenError, anchor_point, reference_direction, apply_mirror, horizontalize)
from ...utils.transform_orientation import slot_orientation

_FADE_DURATION = 0.9             # 镜像后镜面渐隐时长（秒）
_FADE_TICK = 1.0 / 60.0
_AXIS_COLORS = {'X': (1.0, 0.25, 0.25), 'Y': (0.3, 1.0, 0.3), 'Z': (0.35, 0.5, 1.0)}

# 渐隐镜面状态（模块级单例）
_plane = {"handle": None, "timer": None, "registered": False,
          "start": 0.0, "anchor": None, "up": None, "normal": None,
          "size": 1.0, "color": (1.0, 1.0, 1.0)}


def _plane_alpha():
    if _plane["anchor"] is None:
        return 0.0
    elapsed = (time.time() - _plane["start"]) / _FADE_DURATION
    return max(0.0, 1.0 - elapsed)


def _draw_plane():
    """POST_VIEW：绘制竖直镜面（半透明填充 + 描边）+ 法线箭头，alpha 随时间渐隐"""
    try:
        alpha = _plane_alpha()
        if alpha <= 0.0 or _plane["anchor"] is None:
            return
        anchor = _plane["anchor"]
        up = _plane["up"]
        normal = _plane["normal"]
        side = up.cross(normal)
        if side.length < 1e-6:
            return
        side = side.normalized()
        size = _plane["size"]
        color = _plane["color"]
        corners = [tuple(anchor + up * size + side * size), tuple(anchor + up * size - side * size),
                   tuple(anchor - up * size - side * size), tuple(anchor - up * size + side * size)]
        shader = gpu.shader.from_builtin('UNIFORM_COLOR')
        gpu.state.blend_set('ALPHA')
        gpu.state.depth_test_set('NONE')
        shader.bind()
        tris = [corners[0], corners[1], corners[2], corners[0], corners[2], corners[3]]
        fill = batch_for_shader(shader, 'TRIS', {"pos": tris})
        shader.uniform_float("color", (color[0], color[1], color[2], 0.16 * alpha))
        fill.draw(shader)
        gpu.state.line_width_set(2.0)
        outline = batch_for_shader(shader, 'LINE_LOOP', {"pos": corners})
        shader.uniform_float("color", (color[0], color[1], color[2], 0.9 * alpha))
        outline.draw(shader)
        arrow = batch_for_shader(shader, 'LINES', {"pos": [tuple(anchor), tuple(anchor + normal * size)]})
        shader.uniform_float("color", (color[0], color[1], color[2], 1.0 * alpha))
        arrow.draw(shader)
    except ReferenceError:
        pass
    except Exception:
        traceback.print_exc()
    finally:
        gpu.state.blend_set('NONE')
        gpu.state.depth_test_set('LESS_EQUAL')
        gpu.state.line_width_set(1.0)
        gpu.state.point_size_set(1.0)


def _plane_tick():
    if _plane_alpha() <= 0.0:
        teardown_plane()
        return None
    try:
        for window in bpy.context.window_manager.windows:
            for area in window.screen.areas:
                if area.type == 'VIEW_3D':
                    area.tag_redraw()
    except Exception:
        pass
    return _FADE_TICK


def _show_plane(anchor, up, normal, color, size):
    _plane["anchor"] = anchor.copy()
    _plane["up"] = up.copy()
    _plane["normal"] = normal.copy()
    _plane["color"] = tuple(color)
    _plane["size"] = size
    _plane["start"] = time.time()
    if _plane["handle"] is None:
        try:
            _plane["handle"] = bpy.types.SpaceView3D.draw_handler_add(_draw_plane, (), 'WINDOW', 'POST_VIEW')
        except Exception:
            _plane["handle"] = None
    if not _plane["registered"]:
        try:
            bpy.app.timers.register(_plane_tick, first_interval=_FADE_TICK)
            _plane["registered"] = True
        except Exception:
            _plane["registered"] = False


def teardown_plane():
    """移除渐隐镜面的绘制句柄与计时器（幂等）"""
    if _plane["handle"] is not None:
        try:
            bpy.types.SpaceView3D.draw_handler_remove(_plane["handle"], 'WINDOW')
        except Exception:
            pass
        _plane["handle"] = None
    if _plane["registered"]:
        try:
            bpy.app.timers.unregister(_plane_tick)
        except Exception:
            pass
        _plane["registered"] = False
    _plane["anchor"] = None

_MIRROR_AXIS_ITEMS = (
    ('WORLD_X', "世界 X", "以世界 X 轴为左右轴"),
    ('WORLD_Y', "世界 Y", "以世界 Y 轴为左右轴"),
    ('ORIENT_X', "朝向 X", "以当前变换朝向的 X 轴为左右轴"),
    ('ORIENT_Y', "朝向 Y", "以当前变换朝向的 Y 轴为左右轴"),
)
_AXIS_VECTORS = {
    'WORLD_X': Vector((1.0, 0.0, 0.0)),
    'WORLD_Y': Vector((0.0, 1.0, 0.0)),
}


def _reference_items(self, context):
    # 运行时读取，避免热重载后 utils 子模块未刷新导致枚举陈旧
    from ...utils.camera_view_core import REFERENCE_ITEMS
    return [tuple(item) for item in REFERENCE_ITEMS]


class BetterExperie_OT_CameraMirrorView(bpy.types.Operator):
    bl_idname = "better_experie.mirror_view"
    bl_label = "镜像视口"
    bl_description = ("把相机绕到竖直镜面的另一侧：构图左右对调，但产品本身保持真实"
                      "（文字、logo 不会反）。需先选中网格物体作轴心；仰角、距离、焦距都不变，可用 Ctrl+Z 撤销")
    bl_options = {'REGISTER', 'UNDO'}

    ref_axis: EnumProperty(name="参考方向", items=_reference_items, default=0,
                           description="镜面包含该方向（决定「竖直」的基准）")
    mirror_axis: EnumProperty(name="镜像轴（左右方向）", items=_MIRROR_AXIS_ITEMS, default=0,
                              description="镜面法线 = 该轴去掉参考方向分量后的水平方向")

    # 首次执行时记录基准，供 F9 重做精确复现（每次点按都是新实例，不受影响）
    stored_matrix: FloatVectorProperty(size=16, options={'HIDDEN'})
    stored_shift: FloatVectorProperty(size=2, options={'HIDDEN'})
    stored_anchor: FloatVectorProperty(size=3, options={'HIDDEN'})

    @classmethod
    def poll(cls, context):
        scene = getattr(context, "scene", None)
        cam_obj = scene.camera if scene is not None else None
        return (cam_obj is not None and cam_obj.data.type == 'PERSP'
                and any(ob.type == 'MESH' for ob in context.selected_objects))

    def _candidates(self, context, up):
        orient = slot_orientation(context, view=getattr(context, 'region_data', None))
        out = []
        for identifier, vector in (('WORLD_X', Vector((1.0, 0.0, 0.0))),
                                   ('WORLD_Y', Vector((0.0, 1.0, 0.0))),
                                   ('ORIENT_X', orient @ Vector((1.0, 0.0, 0.0))),
                                   ('ORIENT_Y', orient @ Vector((0.0, 1.0, 0.0)))):
            horizontal = horizontalize(vector, up)
            if horizontal is not None:
                out.append((identifier, horizontal))
        return out

    def execute(self, context):
        scene = context.scene
        cam = scene.camera
        if cam is None or cam.data.type != 'PERSP':
            self.report({'ERROR'}, "需要透视相机")
            return {'CANCELLED'}

        for warning in self._preflight(cam):
            self.report({'WARNING'}, warning)

        try:
            if any(self.stored_matrix):
                base = Matrix((tuple(self.stored_matrix[0:4]), tuple(self.stored_matrix[4:8]),
                               tuple(self.stored_matrix[8:12]), tuple(self.stored_matrix[12:16])))
                base_shift = (self.stored_shift[0], self.stored_shift[1])
                anchor = Vector(tuple(self.stored_anchor))
                up, _ = reference_direction(context, self.ref_axis)
            else:
                anchor, _ = anchor_point(context)
                up, _ = reference_direction(context, self.ref_axis)
                base = cam.matrix_world.copy()
                base_shift = (cam.data.shift_x, cam.data.shift_y)
                # 首次执行：自动选「横向偏移最大」的镜像轴，保证镜像幅度明显
                candidates = self._candidates(context, up)
                if candidates:
                    offset = base.to_translation() - anchor
                    self.mirror_axis = max(candidates, key=lambda item: abs(offset.dot(item[1])))[0]
                self.stored_matrix = [value for row in base for value in row]
                self.stored_shift = [base_shift[0], base_shift[1]]
                self.stored_anchor = [anchor.x, anchor.y, anchor.z]

            normal = None
            for identifier, vector in self._candidates(context, up):
                if identifier == self.mirror_axis:
                    normal = vector
                    break
            if normal is None:
                fallback = _AXIS_VECTORS.get(self.mirror_axis)
                if fallback is None:
                    fallback = Vector((1.0, 0.0, 0.0))
                normal = horizontalize(fallback, up)
            if normal is None:
                raise FlattenError("无法确定水平镜面方向")

            apply_mirror(scene, cam, base, base_shift, anchor, normal)
            color = _AXIS_COLORS.get('X' if 'X' in self.mirror_axis else 'Y', (1.0, 1.0, 1.0))
            size = max((base.to_translation() - anchor).length * 0.35, 1e-3)
            _show_plane(anchor, up, normal, color, size)
        except FlattenError as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}

        self.report({'INFO'}, "已镜像视口：构图左右对调，产品保持真实")
        return {'FINISHED'}

    def _preflight(self, cam):
        warnings = []
        if any(cam.lock_location) or any(cam.lock_rotation):
            warnings.append("相机锁定位置 / 旋转：镜像可能不生效")
        if len(cam.constraints) > 0:
            warnings.append("相机受约束：镜像结果可能被约束覆盖")
        return warnings


classes = (
    BetterExperie_OT_CameraMirrorView,
)


def register():
    for cls in classes:
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    teardown_plane()
    for cls in reversed(classes):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass
