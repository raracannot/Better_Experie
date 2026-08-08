#--------------------python--------------------
import bpy
import datetime

class BETTER_EXPERIE_MT_text_timestamp(bpy.types.Menu):
    bl_label = "时间戳"
    bl_idname = "TEXTEDITOR_MT_rara_text_timestamp"

    def draw(self, context):
        layout = self.layout
        now = datetime.datetime.now()
        # op = layout.operator("better_experie.text_insert_datetime",text=now.strftime("%Y-%m-%d"))
        # op.format_string="%Y-%m-%d"
        layout.operator("better_experie.text_insert_datetime",text=now.strftime("%Y-%m-%d")).format_string="%Y-%m-%d"
        layout.operator("better_experie.text_insert_datetime",text=now.strftime("%Y/%m/%d")).format_string="%Y/%m/%d"
        layout.operator("better_experie.text_insert_datetime",text=now.strftime("%Y.%m.%d")).format_string="%Y.%m.%d"
        layout.separator()
        layout.operator("better_experie.text_insert_datetime",text=now.strftime("%Y-%m-%d %H:%M:%S")).format_string="%Y-%m-%d %H:%M:%S"
        layout.operator("better_experie.text_insert_datetime",text=now.strftime("%Y/%m/%d %H:%M:%S")).format_string="%Y/%m/%d %H:%M:%S"
        layout.operator("better_experie.text_insert_datetime",text=now.strftime("%Y.%m.%d %H:%M:%S")).format_string="%Y.%m.%d %H:%M:%S"

class BETTER_EXPERIE_MT_texteditor_submenu(bpy.types.Menu):
    bl_label = "更好的体验"
    bl_idname = "TEXTEDITOR_MT_rara_submenu"

    def draw(self, context):
        layout = self.layout
 
        layout.label(text="大小写编辑")
        op = layout.operator("better_experie.text_capitalization_editor", text="转换为大写")
        op.text_capitalization = 'UPPER'
        op = layout.operator("better_experie.text_capitalization_editor", text="转换为小写")
        op.text_capitalization = 'LOWER'
        op = layout.operator("better_experie.text_capitalization_editor", text="首字母大写")
        op.text_capitalization = 'TITLE'
        op = layout.operator("better_experie.text_capitalization_editor", text="大小写反转")
        op.text_capitalization = 'SWAPCASE'
        
        layout.separator()
        layout.label(text="文本行编辑")
        layout.operator("better_experie.text_remove_trailing_space", text="去除行尾空白")
        layout.operator("better_experie.text_remove_empty_lines", text="移除空白行")
        layout.operator("better_experie.text_sort_selected_lines", text="选区内行排序")

        layout.separator()
        layout.label(text="便捷工具")
        layout.menu("TEXTEDITOR_MT_rara_text_timestamp")
        layout.operator("better_experie.text_multi_language_input", text="多语言输入")
        layout.operator("better_experie.text_word_count", text="字数统计")

 
def draw_texteditor_submenu(self, context):
    layout = self.layout
    layout.separator()
    layout.menu("TEXTEDITOR_MT_rara_submenu")

# 需要注册的类列表
classes = (
    BETTER_EXPERIE_MT_text_timestamp,
    BETTER_EXPERIE_MT_texteditor_submenu,
)

def register():
    # 注册所有自定义类
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.TEXT_MT_edit.append(draw_texteditor_submenu)
    bpy.types.TEXT_MT_context_menu.append(draw_texteditor_submenu)
    
def unregister():
    bpy.types.TEXT_MT_edit.remove(draw_texteditor_submenu)
    bpy.types.TEXT_MT_context_menu.remove(draw_texteditor_submenu)
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
