

import bpy
import importlib

MODULE_NAMES = [
    "other_active_camera_dropdown",
    "other_addon_filter",
    "other_addon_pack",
    "other_auto_save_render",
    "other_deferred_transparent",
    "other_developer_panel_picker",
    "other_show_manual",
    "other_system_optimization",
    "other_background_render",
    "nodetree_aov_rescan",
    "other_object_dye_tool",
    "other_material_dye_tool",
]
# 动态导入所有模块
ops_module_list = [importlib.import_module(f".{name}", __package__) for name in MODULE_NAMES]

def register():
    for ops in ops_module_list:
        if hasattr(ops, "register"): 
            ops.register()

def unregister():
    for ops in reversed(ops_module_list):
        if hasattr(ops, "unregister"): 
            ops.unregister()

def update():
    unregister()
    for ops in ops_module_list: # 重载所有子模块
        importlib.reload(ops)
    register()