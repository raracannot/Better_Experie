# 显示说明书

import os
import bpy


class BetterExperie_OT_ShowManual(bpy.types.Operator):
    bl_idname = "better_experie.show_manual"
    bl_label = "显示说明书"
    bl_description = "在弹出窗口中打开指定的说明书文本文件"
    bl_options = {'REGISTER', 'UNDO'}

    file_path: bpy.props.StringProperty(
        name="File Path",
        default="",
        options={'HIDDEN'}
    )
    data: bpy.props.StringProperty(options={'SKIP_SAVE'})

    @classmethod
    def description(cls, context, properties):
        return properties.data

    def execute(self, context):
        target_width = 1200
        target_height = 600
        raw_path = self.file_path.strip()

        addon_dir = os.path.dirname(__file__)
        abs_path = os.path.join(addon_dir, raw_path)
        abs_path = os.path.normpath(abs_path)

        if not os.path.exists(abs_path):
            self.report({"ERROR"}, f"说明书文件不存在: {abs_path}")
            return {"CANCELLED"}

        try:
            with open(abs_path, 'r', encoding='utf-8') as f:
                file_content = f.read()
        except Exception as e:
            self.report({"ERROR"}, f"读取说明书文件失败: {e}")
            return {"CANCELLED"}

        text_name = os.path.splitext(os.path.basename(abs_path))[0]

        old_res_x = context.scene.render.resolution_x
        old_res_y = context.scene.render.resolution_y

        context.scene.render.resolution_x = target_width
        context.scene.render.resolution_y = target_height

        bpy.ops.render.view_show('INVOKE_DEFAULT')

        context.scene.render.resolution_x = old_res_x
        context.scene.render.resolution_y = old_res_y

        new_window = context.window_manager.windows[-1]
        target_area = None
        for area in new_window.screen.areas:
            target_area = area
            break

        target_area.type = 'TEXT_EDITOR'

        for space in target_area.spaces:
            if space.type == 'TEXT_EDITOR':
                if text_name in bpy.data.texts:
                    text_block = bpy.data.texts[text_name]
                    text_block.clear()
                else:
                    text_block = bpy.data.texts.new(text_name)
                text_block.write(file_content)
                text_block.cursor_set(0, character=0)
                space.text = text_block
                bpy.ops.text.jump(line=0)
                space.show_word_wrap = True
                space.show_line_numbers = True
                space.show_region_header = False
                target_area.tag_redraw()
                break

        self.report({"INFO"}, f"已打开说明书窗口 ({target_width}x{target_height}) 文件: {text_name}")
        return {"FINISHED"}


classes = (
    BetterExperie_OT_ShowManual,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
