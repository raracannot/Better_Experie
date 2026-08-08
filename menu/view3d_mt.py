
import bpy

class BETTER_EXPERIE_MT_view3d_submenu_object(bpy.types.Menu):
    bl_label = "更好的体验"
    bl_idname = "VIEW3D_MT_rara_submenu_object"

    def draw(self, context):
        layout = self.layout

        layout.operator("better_experie.import_clipboard_image_view3d", text="导入剪贴板图像为空物体")
        layout.label(text="功能补充中")

     
class BETTER_EXPERIE_MT_view3d_submenu_mesh(bpy.types.Menu):
    bl_label = "更好的体验"
    bl_idname = "VIEW3D_MT_rara_submenu_mesh"

    def draw(self, context):
        layout = self.layout
        layout.operator("better_experie.copy_elements", text="复制选中元素", icon='COPYDOWN')
        layout.operator("better_experie.paste_elements", text="粘贴并合并", icon='PASTEDOWN')


# 在 VIEW3D_MT_object_context_menu 面板后添加自定义内容
def draw_view3d_submenu(self, context):
    layout = self.layout
    layout.separator()
    if context.mode == 'EDIT_MESH':
        layout.menu("VIEW3D_MT_rara_submenu_mesh")
    elif context.mode == 'OBJECT':
        layout.menu("VIEW3D_MT_rara_submenu_object")

# 需要注册的类列表
classes = (
    BETTER_EXPERIE_MT_view3d_submenu_object,
    BETTER_EXPERIE_MT_view3d_submenu_mesh,
)

def register():
    # 注册所有自定义类
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.VIEW3D_MT_object_context_menu.append(draw_view3d_submenu)#对象模式用
    bpy.types.VIEW3D_MT_edit_mesh_context_menu.append(draw_view3d_submenu)#网格编辑用
    
def unregister():
    bpy.types.VIEW3D_MT_object_context_menu.remove(draw_view3d_submenu)
    bpy.types.VIEW3D_MT_edit_mesh_context_menu.remove(draw_view3d_submenu)
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)