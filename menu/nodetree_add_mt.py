# NODE_MT_context_menu 节点编辑面板
import bpy

class BETTER_EXPERIE_MT_nodetree_add_submenu(bpy.types.Menu):
    bl_label = "更好的体验"
    bl_idname = "NODETREE_ADD_MT_rara_submenu"

    def draw(self, context):
        layout = self.layout
        # 确保在节点编辑界面
        if context.space_data.type != 'NODE_EDITOR':
            return 
        # 确保有有效的节点树
        node_tree = context.space_data.edit_tree
        if not node_tree:
            return 

        # 粘贴图像节点到节点树内
        layout.label(text="请确保剪贴板存在图像数据",icon="IMAGE_DATA")
        layout.separator()
        layout.operator("better_experie.import_clipboard_image_nodeeditor", text="导入剪贴板图像到节点视口")
        layout.operator("better_experie.import_clipboard_to_gradient", text="从剪贴板创建颜色渐变条")
        

def draw_nodetree_submenu(self, context):
    layout = self.layout
    # layout.separator()
    layout.menu(BETTER_EXPERIE_MT_nodetree_add_submenu.bl_idname)


# 需要注册的类列表
classes = (
    BETTER_EXPERIE_MT_nodetree_add_submenu,
)

def register():
    # 注册所有自定义类
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.NODE_MT_add.append(draw_nodetree_submenu)
    
def unregister():
    bpy.types.NODE_MT_add.remove(draw_nodetree_submenu)
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


