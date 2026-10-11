# 平整视图：把相机光轴摆平到垂直于参考方向（移轴 / Shift 原理），
# 使产品竖直边在画面中平行，并保持产品在画面中的位置不变。
# 相机位置、焦距、构图均不变，可用 Ctrl+Z 撤销。
# 参考自 Flatten View (平整视图) by DSH

import bpy
from bpy.props import EnumProperty

from ...utils.camera_view_core import FlattenError, apply_flatten


def _reference_items(self, context):
    # 运行时读取，避免热重载后 utils 子模块未刷新导致枚举陈旧
    from ...utils.camera_view_core import REFERENCE_ITEMS
    return [tuple(item) for item in REFERENCE_ITEMS]


class BetterExperie_OT_CameraFlattenView(bpy.types.Operator):
    bl_idname = "better_experie.flatten_view"
    bl_label = "平整视图"
    bl_description = (
        "把相机光轴摆平到垂直于参考方向，使产品竖直边在画面中平行（移轴 / Shift 原理），"
        "并保持产品在画面中的位置不变。需先选中网格物体作轴心；相机位置、焦距、构图都不动，可用 Ctrl+Z 撤销")
    bl_options = {'REGISTER', 'UNDO'}

    ref_axis: EnumProperty(name="参考方向", items=_reference_items, default=0)

    @classmethod
    def poll(cls, context):
        scene = getattr(context, "scene", None)
        cam_obj = scene.camera if scene is not None else None
        return (cam_obj is not None and cam_obj.data.type == 'PERSP'
                and any(ob.type == 'MESH' for ob in context.selected_objects))

    def execute(self, context):
        try:
            info = apply_flatten(context, self.ref_axis)
        except FlattenError as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        self.report(
            {'INFO'},
            "已平整：光轴与%s的夹角 %.1f° → 90°，产品在画面中的位置保持不变"
            % (info["axis_source"], info["angle_before"]))
        return {'FINISHED'}


classes = (
    BetterExperie_OT_CameraFlattenView,
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
    for cls in reversed(classes):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass
