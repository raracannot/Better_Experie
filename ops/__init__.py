

import bpy
import importlib

MODULE_NAMES = [
    "filebrowser",
    "nodetree",
    "other",
    "outliner",
    "sequencer",
    "texteditor",
    "view3d",
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
    for ops in ops_module_list: # 执行所有子模块的刷新
        if hasattr(ops, "update"): 
            ops.update()
            
    unregister()
    for ops in ops_module_list: # 重载所有子模块
        importlib.reload(ops)
    register()
    
