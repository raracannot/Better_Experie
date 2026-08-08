

import bpy
import importlib

MODULE_NAMES = [
    "nodetree_compositor_add_output_node",
    "nodetree_compositor_bake_node",
    "nodetree_convert_image_to_gradient",
    "nodetree_developer_tool",
    "nodetree_image_and_clipboard",
    "nodetree_image_to_environment_node",
    "nodetree_open_in_external_editor",
    "nodetree_preview_selected_image",
    "nodetree_shader_bake_node",
    "nodetree_node_tools",
    "nodetree_color_ramp_tools",
    "nodetree_ramp_library",
    "nodetree_texture_tools",
    "nodetree_color_curve_tools",
    "nodetree_minimap_preview",
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