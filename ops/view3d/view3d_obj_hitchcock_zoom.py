# 希区柯克变焦

import bpy
import traceback
from mathutils import Vector
from ...utils.modal_border import add_modal_border, remove_modal_border

_ZOOM_STEP = 0.1
_MIN_DIST = 0.1
_MIN_LENS = 1.0
_MAX_LENS = 5000.0


class BetterExperie_OT_HitchcockZoom(bpy.types.Operator):
    bl_idname = "better_experie.hitchcock_zoom"
    bl_label = "希区柯克变焦"
    bl_description = "模态变焦：鼠标滚轮调整相机位置与焦距（Shift 慢速 0.05 倍），保持目标物体构图不变"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        return bool(context.scene.camera and context.active_object)

    def invoke(self, context, event):
        try:
            cam = context.scene.camera
            obj = context.active_object
            if not cam or not obj:
                self.report({'WARNING'}, "需要活动相机和活动物体")
                return {'CANCELLED'}
            if cam == obj:
                self.report({'WARNING'}, "活动物体不得与活动相机相同")
                return {'CANCELLED'}
            if not context.area or context.area.type != 'VIEW_3D':
                self.report({'WARNING'}, "仅支持三维视口")
                return {'CANCELLED'}
            if context.space_data.region_3d.view_perspective != 'CAMERA':
                bpy.ops.view3d.view_camera()

            add_modal_border(self, context)
            context.window_manager.modal_handler_add(self)
            context.area.tag_redraw()
            context.workspace.status_text_set("希区柯克变焦：滚轮变焦，Shift 慢速，右键/ESC退出")
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

            if event.type in {'WHEELUPMOUSE', 'WHEELDOWNMOUSE'}:
                cam = context.scene.camera
                obj = context.active_object
                if not cam or not obj:
                    self.report({'WARNING'}, "丢失活动相机或活动物体")
                    self._cleanup(context)
                    return {'CANCELLED'}

                bbox_center = sum((Vector(b) for b in obj.bound_box), Vector()) / 8
                target_pos = obj.matrix_world @ bbox_center
                cam_vec = cam.location - target_pos
                current_dist = cam_vec.length

                step = _ZOOM_STEP * (0.05 if event.shift else 1.0)
                zoom_step = step if event.type == 'WHEELUPMOUSE' else -step
                new_dist = current_dist - zoom_step

                if new_dist < _MIN_DIST:
                    return {'RUNNING_MODAL'}

                ratio = new_dist / current_dist
                new_lens = cam.data.lens * ratio
                if _MIN_LENS <= new_lens <= _MAX_LENS:
                    cam.location = target_pos + cam_vec.normalized() * new_dist
                    cam.data.lens = new_lens

                context.area.tag_redraw()
            return {'RUNNING_MODAL'}
            
        except Exception:
            traceback.print_exc()
            self._cleanup(context)
            return {'CANCELLED'}

    def _cleanup(self, context):
        remove_modal_border(self)
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
    BetterExperie_OT_HitchcockZoom,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
