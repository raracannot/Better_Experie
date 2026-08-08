# 单帧渲染自动保存

import bpy
import os
from bpy.app.handlers import persistent


def execute_deferred_save(scene_name, filepath):
    scene = bpy.data.scenes.get(scene_name)
    img = bpy.data.images.get('Render Result')

    if not scene or not img or not img.has_data:
        print("【Auto Save Render】保存失败: 找不到场景或渲染数据未就绪")
        return None

    try:
        img.save_render(filepath, scene=scene)
        print(f"【Auto Save Render】单帧渲染已自动保存至: {filepath}")

        if scene.render.image_settings.file_format == 'OPEN_EXR_MULTILAYER' and scene.render.image_settings.use_preview:
            orig_media = scene.render.image_settings.media_type
            orig_format = scene.render.image_settings.file_format
            orig_mode = scene.render.image_settings.color_mode
            orig_depth = scene.render.image_settings.color_depth
            try:
                scene.render.image_settings.media_type = 'IMAGE'
                scene.render.image_settings.file_format = 'PNG'
                scene.render.image_settings.color_mode = 'RGBA'
                scene.render.image_settings.color_depth = '16'

                png_path = os.path.splitext(filepath)[0] + ".png"
                img.save_render(png_path, scene=scene)
                print(f"【Auto Save Render】已自动生成 PNG 预览图至: {png_path}")
            except Exception as e:
                print(f"【Auto Save Render】PNG 预览保存失败: {e}")
            finally:
                scene.render.image_settings.media_type = orig_media
                if orig_media != 'MULTI_LAYER_IMAGE':
                    scene.render.image_settings.file_format = orig_format
                scene.render.image_settings.color_mode = orig_mode
                scene.render.image_settings.color_depth = orig_depth
    except Exception as e:
        print(f"【Auto Save Render】保存流程出错: {e}")

    return None


@persistent
def auto_save_render_handler(scene):
    if not scene.better_experie_auto_save_render:
        return

    filepath = scene.render.frame_path(frame=scene.frame_current)
    if not scene.render.use_overwrite and os.path.exists(filepath):
        base, ext = os.path.splitext(filepath)
        counter = 1
        while os.path.exists(f"{base}_{counter}{ext}"):
            counter += 1
        filepath = f"{base}_{counter}{ext}"

    os.makedirs(os.path.dirname(filepath), exist_ok=True)

    bpy.app.timers.register(
        lambda: execute_deferred_save(scene.name, filepath),
        first_interval=1.0)


class RENDER_PT_auto_save_panel(bpy.types.Panel):
    bl_label = "单帧自动保存"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "output"
    bl_parent_id = "RENDER_PT_output"

    @classmethod
    def poll(cls, context):
        return context.scene.render.image_settings.media_type != 'VIDEO'

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        scene = context.scene
        layout.prop(scene, "better_experie_auto_save_render", text="启用单帧自动保存")


classes = (
    RENDER_PT_auto_save_panel,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.better_experie_auto_save_render = bpy.props.BoolProperty(
        name="Auto Save", default = False, description = "勾选启用后，在渲染单帧图像时，也自动保存到输出目录" )
    if auto_save_render_handler not in bpy.app.handlers.render_post:
        bpy.app.handlers.render_post.append(auto_save_render_handler)


def unregister():
    if auto_save_render_handler in bpy.app.handlers.render_post:
        bpy.app.handlers.render_post.remove(auto_save_render_handler)
    del bpy.types.Scene.better_experie_auto_save_render
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
