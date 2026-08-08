
import bpy
import sys
from ..utils import get_pref


IS_WINDOWS = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"
IS_LINUX = sys.platform == "linux"

class BETTER_EXPERIE_MT_filebrowser_submenu(bpy.types.Menu):
    bl_label = "更好的体验"
    bl_idname = "FILEBROWSER_MT_rara_submenu"

    def draw(self, context):
        layout = self.layout
        if context.space_data.params.recursion_level != 'NONE':
            layout.operator( "better_experie.jump_to_file_location", text="跳转到文件所在层级")
        
        layout.operator( "better_experie.jump_selected_folder", text="打开所选文件夹")
        layout.separator()
        op = layout.operator( "better_experie.open_and_jump_to_folder", text="打开工程文件夹")
        op.open_folder = "PROJECT"
        op.open_mode = "OPEN"
        op = layout.operator( "better_experie.open_and_jump_to_folder", text="跳转工程文件夹")
        op.open_folder = "PROJECT"
        op.open_mode = "JUMP"
        op = layout.operator( "better_experie.open_and_jump_to_folder", text="打开输出文件夹")
        op.open_folder = "OUTPUT"
        op.open_mode = "OPEN"
        op = layout.operator( "better_experie.open_and_jump_to_folder", text="跳转输出文件夹")
        op.open_folder = "OUTPUT"
        op.open_mode = "JUMP"
        
        layout.separator()
        
        layout.operator( "better_experie.batch_rename", text="重命名文件夹")
        layout.operator( "better_experie.generate_file_tree", text="生成文件树")

        if (IS_WINDOWS or IS_MAC):
            prefs = get_pref()

            if not prefs.filebrowser_show_explorer_heder:
                layout.separator()
                layout.operator( "better_experie.toggle_explorer_header", text="启用WIN文件夹快速跳转栏")#emboss = True

def draw_filebrowser_submenu(self, context):
    layout = self.layout
    layout.separator()
    layout.menu(BETTER_EXPERIE_MT_filebrowser_submenu.bl_idname)
       
classes = (
    BETTER_EXPERIE_MT_filebrowser_submenu,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.FILEBROWSER_MT_context_menu.append(draw_filebrowser_submenu)

def unregister():
    bpy.types.FILEBROWSER_MT_context_menu.remove(draw_filebrowser_submenu)
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)