
bl_info = {
    "name": "Better_Experie【更好的体验】",
    "author": "RARA(来一点咖啡吗)",
    "version": (1, 0, 5),
    "blender": (4, 5, 0),
    'doc_url': 'https://space.bilibili.com/27284213',
}

import bpy
# import importlib
from . import register_module


# 热重载操作符
class BetterExperie_OT_ReloadPlugin(bpy.types.Operator):
    bl_idname = "better_experie.reload_addon"
    bl_label = "重载子模块"
    bl_description = "重新加载所有子模块，用于插件开发期间的热更新"
    bl_options = {'REGISTER'}

    def execute(self, context):
        try:
            register_module.update()  # 调用下面的 update 函数
            self.report({'INFO'}, "插件重载完成")
        except Exception as e:
            self.report({'ERROR'}, f"重加载失败: {str(e)}")
            return {'CANCELLED'}
        return {'FINISHED'}

def register():
    # importlib.reload(register_module) #用于在插件开发期间热更新
    
    try: # 防止重复注册：先安全注销残留的旧注册
        register_module.unregister()
    except Exception:
        pass
    register_module.register()
    
    try:
        bpy.utils.unregister_class(BetterExperie_OT_ReloadPlugin)
    except Exception:
        pass
    bpy.utils.register_class(BetterExperie_OT_ReloadPlugin)

def unregister():
    try:
        bpy.utils.unregister_class(BetterExperie_OT_ReloadPlugin)
    except Exception:
        pass
    
    register_module.unregister()

if bpy.app.background:
    print("\n---------------------------------")
    print(f"{bl_info['name']}_V{bl_info['version']}后台模式忽略加载")
    print("---------------------------------\n")
    def register():
        pass
    def unregister():
        pass

if __name__ == "__main__":
    register()