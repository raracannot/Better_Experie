# 快速为活动相机设置纯色背景（白/黑），仅影响视口预览

import bpy


def get_or_create_color_image(img_name, color_rgba):
    img = bpy.data.images.get(img_name)
    if not img:
        size = 32
        img = bpy.data.images.new(img_name, width=size, height=size, alpha=True)
        pixels = color_rgba * (size * size)
        img.pixels.foreach_set(pixels)
        img.pack()
    return img


def set_camera_background_color(context, operator, img_name, color_rgba):
    camera = context.scene.camera
    if not camera or camera.type != 'CAMERA':
        operator.report({'WARNING'}, "当前场景没有活动相机！请先添加并设置一个活动相机。")
        return False

    img = get_or_create_color_image(img_name, color_rgba)
    cam_data = camera.data

    cam_data.show_background_images = True
    if len(cam_data.background_images) > 0:
        bg = cam_data.background_images[0]
    else:
        bg = cam_data.background_images.new()
        bg.show_expanded = False
    bg.source = 'IMAGE'
    bg.image = img
    bg.display_depth = 'BACK'
    bg.frame_method = 'CROP'
    bg.alpha = 1.0

    return True


class BetterExperie_OT_SetCameraBg(bpy.types.Operator):
    bl_idname = "better_experie.set_camera_bg"
    bl_label = "设置相机背景"
    bl_description = "为活动相机设置纯色视口背景（白/黑），仅相机覆盖，不影响最终渲染"
    bl_options = {'REGISTER', 'UNDO'}

    action: bpy.props.StringProperty()

    def execute(self, context):
        if self.action == 'WHITE':
            if set_camera_background_color(context, self, "White_BG", (1.0, 1.0, 1.0, 1.0)):
                self.report({'INFO'}, "已切换为白底")

        elif self.action == 'BLACK':
            if set_camera_background_color(context, self, "Black_BG", (0.0, 0.0, 0.0, 1.0)):
                self.report({'INFO'}, "已切换为黑底")

        elif self.action == 'CLEAR':
            camera = context.scene.camera
            if camera and camera.type == 'CAMERA':
                camera.data.show_background_images = False
                camera.data.background_images.clear()
                self.report({'INFO'}, "已清除相机背景")
            else:
                self.report({'WARNING'}, "没有找到活动相机！")

        return {'FINISHED'}



def view3d_mt_view_cameras_draw(self, context):
    layout = self.layout
    row = layout.row()
    op_white = row.operator("better_experie.set_camera_bg", text="快速设置白色背景", icon='KEY_RING_FILLED')
    op_white.action = 'WHITE'
    op_black = row.operator("better_experie.set_camera_bg", text="快速设置黑色背景", icon='KEY_RING')
    op_black.action = 'BLACK'


classes = (
    BetterExperie_OT_SetCameraBg,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.DATA_PT_camera_background_image.append(view3d_mt_view_cameras_draw)


def unregister():
    bpy.types.DATA_PT_camera_background_image.remove(view3d_mt_view_cameras_draw)
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
