# UV 编辑器相关算子子包

import bpy
import importlib

MODULE_NAMES = [
    "uv_mesh_select_nonmanifold_edge_loop",
    "uv_mesh_select_edge_ring",
]
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
    for ops in ops_module_list:  # 重载所有子模块
        importlib.reload(ops)
    register()
