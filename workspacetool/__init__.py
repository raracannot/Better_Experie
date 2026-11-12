# 工作区工具（T 面板）子包

import bpy
import importlib

MODULE_NAMES = [
    "curvature_slide",
]
tool_module_list = [importlib.import_module(f".{name}", __package__) for name in MODULE_NAMES]


def register():
    for module in tool_module_list:
        if hasattr(module, "register"):
            module.register()


def unregister():
    for module in reversed(tool_module_list):
        if hasattr(module, "unregister"):
            module.unregister()


def update():
    unregister()
    for module in tool_module_list:  # 重载所有子模块
        importlib.reload(module)
    register()
