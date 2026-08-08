#--------------------python--------------------
import bpy

class BETTER_EXPERIE_MT_outliner_submenu(bpy.types.Menu):
    bl_label = "更好的体验"
    bl_idname = "BETTER_EXPERIE_MT_outliner_submenu"

    def draw(self, context):
        layout = self.layout
        layout.operator("better_experie.create_empty_group", text="创建空物体组", icon='EMPTY_AXIS')
        layout.operator("better_experie.dissolve_empty_group", text="解散空物体组", icon='UNLINKED')
        layout.separator()
        layout.operator("better_experie.empties_to_collections", text="空对象转集合")
        layout.operator("better_experie.collections_to_empties", text="集合转空对象")
        layout.operator("better_experie.clear_empty_collections", text="清除为空集合")
        layout.operator("better_experie.clear_useless_empties", text="清除无用空物体")
        layout.separator()
        layout.operator("better_experie.collection_to_instance", text="打包为实例", icon='GROUP')
        layout.operator("better_experie.instance_to_collection", text="实例解包为集合", icon='OUTLINER_COLLECTION')
        layout.menu("BETTER_EXPERIE_MT_collection_instance_settings", icon='PIVOT_CURSOR')
     

def draw_outliner_submenu(self, context):
    layout = self.layout
    layout.separator()
    layout.menu(BETTER_EXPERIE_MT_outliner_submenu.bl_idname)

# 需要注册的类列表
classes = (
    BETTER_EXPERIE_MT_outliner_submenu,
)

def register():
    # 注册所有自定义类
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.OUTLINER_MT_context_menu.append(draw_outliner_submenu)
    bpy.types.OUTLINER_MT_collection.append(draw_outliner_submenu)
    bpy.types.OUTLINER_MT_object.append(draw_outliner_submenu)
    
def unregister():
    bpy.types.OUTLINER_MT_context_menu.remove(draw_outliner_submenu)
    bpy.types.OUTLINER_MT_collection.remove(draw_outliner_submenu)
    bpy.types.OUTLINER_MT_object.remove(draw_outliner_submenu)
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

