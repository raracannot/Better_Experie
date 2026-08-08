
import bpy
import importlib

MODULE_NAMES = [
    "fix_console",
]
# 动态导入所有模块
mt_module_list = [importlib.import_module(f".{name}", __package__) for name in MODULE_NAMES]

def register():
    for module in mt_module_list:
        if hasattr(module, "register"): 
            module.register()

def unregister():
    for module in reversed(mt_module_list):
        if hasattr(module, "unregister"): 
            module.unregister()

def update():
    unregister()
    for module in mt_module_list: # 重载所有子模块
        importlib.reload(module)
    register()