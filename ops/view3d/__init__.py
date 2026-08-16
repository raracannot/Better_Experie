

import bpy
import importlib

MODULE_NAMES = [
    "view3d_cursor_to_selected",
    "view3d_edit_bbox",
    "view3d_empty_wireframe",
    "view3d_fix_applied_rotation",
    "view3d_obj_fix_rotation_by_face",
    "view3d_parent_transform",
    "view3d_mesh_filter_batch_selector", #筛查式选择卡
    "view3d_obj_apply_all_modifiers", #应用所有修改器
    "view3d_obj_create_new_camera", #创建新相机
    "view3d_obj_filter_batch_selector", #筛查式选择卡
    "view3d_obj_switch_to_nearest_orthogonal", #切换至最接近的透视视口
    "view3d_mesh_edge_loop_select",
    "view3d_mesh_face_loop_select",
    "view3d_mesh_smart_close_loop",
    "view3d_mesh_add_vertex_group",
    "view3d_obj_toggle_hidden",
    "view3d_mesh_select_region_by_loop",
    "view3d_obj_elements_clipboard",
    "view3d_obj_modifier_tools",
    "view3d_obj_clear_viewport_shading",
    "view3d_obj_clear_materials",
    "view3d_collection_visibility",
    "view3d_mesh_separate_edges_to_curve",
    "view3d_mesh_flip_normals_by_view",
    "view3d_mesh_align_view_to_normal",
    "view3d_mesh_topology_hud",
    "view3d_obj_import_lib_mesh",
    "view3d_mesh_weld_verts_to_edges",
    "view3d_obj_camera_background",
    "view3d_mesh_modal_weld",
    "view3d_obj_mirror",
    "view3d_mesh_attribute_tool",
    "view3d_mesh_vertex_color_tool",
    "view3d_mesh_vertex_group_stats",
    "view3d_obj_visual_uv_projection",
    "view3d_obj_preview_parent_vertices",
    "view3d_mesh_reset_local_normals",
    "view3d_mesh_select_ring_edges",
    "view3d_mesh_select_nonmanifold_edge_loop",
    "view3d_mesh_select_nonmanifold_face_loop",
    "view3d_mesh_select_sharp_chain",
    "view3d_mesh_select_face_region",
    "view3d_mesh_custom_island_expand",
    "view3d_mesh_edge_to_face",
    "view3d_mesh_intersect_edges",
    "view3d_mesh_weld_coplanar",
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