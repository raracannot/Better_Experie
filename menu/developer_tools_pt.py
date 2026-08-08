#可以存放到Better_Experie\menu\下，作为developer_tools_pt

import bpy
from ..utils import get_pref

class BETTER_EXPERIE_PT_developer_debug_panel(bpy.types.Panel):
    bl_space_type = 'PREFERENCES'
    bl_region_type = 'WINDOW'
    bl_context = "developer_tools" # 关键：指定到开发者工具上下文
    bl_label = "开发者工具"     # 你的面板名称

    @classmethod
    def poll(cls, context):
        # 保持与原生面板一致，只有开启开发者UI时才显示
        return context.preferences.view.show_developer_ui

    def draw(self, context):
        prefs = get_pref()
        layout = self.layout
        # layout.operator("wm.console_toggle", text="打开控制台")

        box = layout.box()
        box.label(text="提取blender面板详细信息")
        box.operator("better_experie.developer_panel_picker", text="面板提取")
        
        box = layout.box()
        box.label(text="打包插件为发行包")
        box.prop(prefs, "output_path")
        row = box.row()
        row.operator("better_experie.generate_addon_manifest", text="生成 manifest")
        row.operator("better_experie.pack_addon", text="一键打包")
            
def register():
    bpy.utils.register_class(BETTER_EXPERIE_PT_developer_debug_panel)

def unregister():
    bpy.utils.unregister_class(BETTER_EXPERIE_PT_developer_debug_panel)

if __name__ == "__main__":
    register()

