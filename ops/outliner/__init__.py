

import bpy
import importlib

MODULE_NAMES = [
    "outliner_convert_empty_collection",
    "outliner_create_empty_group",
    "outliner_collection_instance",
    "outliner_empty_and_lock",
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