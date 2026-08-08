
import bpy


# ── 网格选择 → 循环/环/非流形 ──
def draw_edit_mesh_select_loops(self, context):
    select_mode = context.tool_settings.mesh_select_mode
    layout = self.layout
    layout.separator()
    layout.operator("better_experie.select_enclosed_regions", icon="STICKY_UVS_LOC")
    layout.operator("better_experie.mesh_smart_close_loop", icon="SELECT_SET")
    if select_mode[1]:
        layout.separator()
        layout.operator("better_experie.edge_loop_select", icon="EDGESEL")
    if select_mode[2]:
        layout.separator()
        layout.operator("better_experie.face_loop_select", icon="FACESEL")
    layout.separator()
    layout.menu("BETTER_EXPERIE_MT_nonmanifold_loop_select", text="非流形循环选取")


# ── 网格选择 → 特征 ──
def draw_select_by_trait(self, context):
    layout = self.layout
    layout.separator()
    sel_mode = context.tool_settings.mesh_select_mode
    if sel_mode[2]:
        # 面模式：以锐边为分界线的面区域选择
        layout.operator("better_experie.select_face_region", text="选择面区域（锐边分界）", icon='FACESEL')
    else:
        # 点/边模式：锐边连续链
        layout.operator("better_experie.select_sharp_chain", text="选择锐边/边界连续链")


# ── 网格选择 → 扩选/收缩 ──
def draw_select_more_less(self, context):
    layout = self.layout
    layout.separator()
    layout.operator("better_experie.custom_island_expand", text="自定义孤岛扩选", icon='SELECT_EXTEND')


# ── 网格法向（菜单顶部） ──
def draw_flip_normals_by_view(self, context):
    layout = self.layout
    layout.operator("better_experie.flip_normals_by_view")

# ── 网格法向（菜单底部） ──
def draw_reset_local_normals(self, context):
    layout = self.layout
    layout.separator()
    layout.operator("better_experie.reset_local_normals")


# ── 网格合并 ──
def draw_edit_mesh_merge(self, context):
    if context.mode == 'EDIT_MESH':
        layout = self.layout
        layout.separator()
        if context.tool_settings.mesh_select_mode[0]:
            layout.operator("better_experie.invoke_modal_weld", icon="CON_TRACKTO")
            layout.operator("better_experie.weld_verts_to_edges", icon="SNAP_MIDPOINT")
        if context.tool_settings.mesh_select_mode[1]:
            layout.separator()
            layout.operator("better_experie.weld_edges_to_faces", icon="MOD_EDGESPLIT")
            layout.operator("better_experie.intersect_edges", icon="OUTLINER_DATA_EMPTY")
        if context.tool_settings.mesh_select_mode[2]:
            layout.separator()
            layout.operator("better_experie.weld_coplanar", icon="SNAP_FACE")


# ── 网格拆分 ──
def draw_edit_mesh_split(self, context):
    layout = self.layout
    layout.separator()
    layout.operator("better_experie.separate_edges_to_curve")


# ── 顶点组 ──
def draw_vertex_group(self, context):
    layout = self.layout
    layout.operator("better_experie.mesh_add_vertex_group", text="智能顶点组", icon="GROUP_VERTEX")


# ── 显隐切换（编辑/物体共用）──
def draw_toggle_hidden(self, context):
    layout = self.layout
    layout.separator()
    layout.operator("better_experie.toggle_hidden", icon="UV_SYNC_SELECT")


# ── 添加网格 ──
def draw_mesh_add(self, context):
    if context.mode == 'OBJECT':
        layout = self.layout
        layout.menu("VIEW3D_MT_better_experie_more_meshes", icon='COLLECTION_COLOR_02')
        layout.separator()


# ── 视口方向 ──
def draw_view_viewpoint(self, context):
    layout = self.layout
    layout.separator()
    layout.operator("better_experie.align_view_to_normal")


# ── 视口对齐 → 对齐法向 ──
def draw_view_align(self, context):
    layout = self.layout
    layout.separator()
    layout.operator("better_experie.align_view_to_normal")


# ── 视口方向 → 最近正交 ──
def draw_nearest_orthogonal(self, context):
    layout = self.layout
    layout.separator(type="LINE")
    layout.operator("better_experie.switch_to_nearest_orthogonal")


# ── 视口相机 ──
def draw_view_cameras(self, context):
    layout = self.layout
    layout.separator(type="LINE")
    layout.operator("better_experie.create_new_camera_at_view")


# ── 物体镜像 ──
def draw_mirror(self, context):
    if context.mode == 'OBJECT':
        layout = self.layout
        layout.separator(type="LINE")
        layout.operator("better_experie.object_mirror", text="镜像物体", icon="MOD_MIRROR")


# ── 物体修改器 ──
def draw_object_modifiers(self, context):
    layout = self.layout
    layout.separator()
    layout.operator("better_experie.apply_all_modifiers", text="应用所有修改器")
    layout.separator()
    layout.operator("better_experie.batch_process_modifiers", text="批量处理修改器...", icon="MODIFIER")


# ── 物体清除变换 ──
def draw_object_clear(self, context):
    layout = self.layout
    layout.separator()
    layout.operator("better_experie.fix_applied_rotation", icon="DRIVER_ROTATIONAL_DIFFERENCE")
    layout.operator("better_experie.fix_applied_rotation_by_normals", icon="DRIVER_ROTATIONAL_DIFFERENCE")


# ── 物体应用变换 ──
def draw_object_apply(self, context):
    layout = self.layout
    layout.separator()
    op = layout.operator("better_experie.clear_delta_transform", text="增量 > 位置")
    op.mode = 'LOC'
    op = layout.operator("better_experie.clear_delta_transform", text="增量 > 旋转")
    op.mode = 'ROT'
    op = layout.operator("better_experie.clear_delta_transform", text="增量 > 缩放")
    op.mode = 'SCALE'
    op = layout.operator("better_experie.clear_delta_transform", text="增量 > 全部变换", icon='FILE_REFRESH')
    op.mode = 'ALL'


# ── 物体清理 ──
def draw_object_cleanup(self, context):
    layout = self.layout
    layout.separator()
    layout.operator("better_experie.clear_viewport_shading", text="清理视图着色", icon='SHADING_SOLID')
    layout.operator("mesh.customdata_custom_splitnormals_clear", text="清理自定义法向", icon='NORMALS_VERTEX')


# ── 编辑标题栏（复制粘贴元素）──
def draw_editor_menus(self, context):
    obj = context.active_object
    if not obj or obj.type not in {'MESH', 'CURVE', 'SURFACE', 'ARMATURE', 'GPENCIL'}:
        return
    if obj.mode not in {'EDIT', 'EDIT_GPENCIL'}:
        return
    layout = self.layout
    layout.separator()
    layout.operator("better_experie.copy_elements", text="", icon='COPYDOWN')
    layout.operator("better_experie.paste_elements", text="", icon='PASTEDOWN')


# ── 网格筛选式选取 ──
def draw_select_edit_mesh(self, context):
    layout = self.layout
    layout.separator(type="LINE")
    layout.operator("better_experie.mesh_filter_batch_selector", text="筛选式选取", icon='FILTER')

# ── 物体筛选式选取 ──
def draw_select_object(self, context):
    layout = self.layout
    layout.separator(type="LINE")
    layout.operator("better_experie.object_filter_batch_selector", text="筛选式选取", icon='FILTER')


# ── 节点视图 ──
def draw_node_view(self, context):
    layout = self.layout
    layout.operator("better_experie.set_node_tree_origin", text="设为视口原点", icon="VIEWZOOM")


# ── 顶栏渲染 ──
def draw_topbar_render(self, context):
    layout = self.layout
    layout.separator()
    layout.menu("BETTER_EXPERIE_MT_background_render")


# ── 顶栏文件清理 ──
def draw_topbar_file_cleanup(self, context):
    layout = self.layout
    layout.separator(type="LINE")
    layout.operator("better_experie.system_optimization", text="内存优化", icon="FILE_REFRESH")


# ── 注册 ──

def register():
    bpy.types.VIEW3D_MT_edit_mesh_select_loops.append(draw_edit_mesh_select_loops)
    bpy.types.VIEW3D_MT_edit_mesh_select_by_trait.append(draw_select_by_trait)
    bpy.types.VIEW3D_MT_edit_mesh_select_more_less.append(draw_select_more_less)
    bpy.types.VIEW3D_MT_edit_mesh_normals.prepend(draw_flip_normals_by_view)
    bpy.types.VIEW3D_MT_edit_mesh_normals.append(draw_reset_local_normals)
    bpy.types.VIEW3D_MT_edit_mesh_merge.append(draw_edit_mesh_merge)
    bpy.types.VIEW3D_MT_edit_mesh_split.append(draw_edit_mesh_split)
    bpy.types.VIEW3D_MT_vertex_group.append(draw_vertex_group)
    bpy.types.VIEW3D_MT_edit_mesh_showhide.append(draw_toggle_hidden)
    bpy.types.VIEW3D_MT_object_showhide.append(draw_toggle_hidden)
    bpy.types.VIEW3D_MT_mesh_add.prepend(draw_mesh_add)
    bpy.types.VIEW3D_MT_view_viewpoint.append(draw_view_viewpoint)
    bpy.types.VIEW3D_MT_view_viewpoint.append(draw_nearest_orthogonal)
    bpy.types.VIEW3D_MT_view_align.append(draw_view_align)
    bpy.types.VIEW3D_MT_view_cameras.append(draw_view_cameras)
    bpy.types.VIEW3D_MT_mirror.append(draw_mirror)
    bpy.types.VIEW3D_MT_object_modifiers.append(draw_object_modifiers)
    bpy.types.VIEW3D_MT_object_clear.append(draw_object_clear)
    bpy.types.VIEW3D_MT_object_apply.append(draw_object_apply)
    bpy.types.VIEW3D_MT_object_cleanup.append(draw_object_cleanup)
    bpy.types.VIEW3D_MT_editor_menus.append(draw_editor_menus)
    bpy.types.VIEW3D_MT_select_edit_mesh.append(draw_select_edit_mesh)
    bpy.types.VIEW3D_MT_select_object.append(draw_select_object)
    bpy.types.NODE_MT_view.append(draw_node_view)
    bpy.types.TOPBAR_MT_render.append(draw_topbar_render)
    bpy.types.TOPBAR_MT_file_cleanup.append(draw_topbar_file_cleanup)


def unregister():
    bpy.types.VIEW3D_MT_edit_mesh_select_loops.remove(draw_edit_mesh_select_loops)
    bpy.types.VIEW3D_MT_edit_mesh_select_by_trait.remove(draw_select_by_trait)
    bpy.types.VIEW3D_MT_edit_mesh_select_more_less.remove(draw_select_more_less)
    bpy.types.VIEW3D_MT_edit_mesh_normals.remove(draw_flip_normals_by_view)
    bpy.types.VIEW3D_MT_edit_mesh_normals.remove(draw_reset_local_normals)
    bpy.types.VIEW3D_MT_edit_mesh_merge.remove(draw_edit_mesh_merge)
    bpy.types.VIEW3D_MT_edit_mesh_split.remove(draw_edit_mesh_split)
    bpy.types.VIEW3D_MT_vertex_group.remove(draw_vertex_group)
    bpy.types.VIEW3D_MT_edit_mesh_showhide.remove(draw_toggle_hidden)
    bpy.types.VIEW3D_MT_object_showhide.remove(draw_toggle_hidden)
    bpy.types.VIEW3D_MT_mesh_add.remove(draw_mesh_add)
    bpy.types.VIEW3D_MT_view_viewpoint.remove(draw_view_viewpoint)
    bpy.types.VIEW3D_MT_view_viewpoint.remove(draw_nearest_orthogonal)
    bpy.types.VIEW3D_MT_view_align.remove(draw_view_align)
    bpy.types.VIEW3D_MT_view_cameras.remove(draw_view_cameras)
    bpy.types.VIEW3D_MT_mirror.remove(draw_mirror)
    bpy.types.VIEW3D_MT_object_modifiers.remove(draw_object_modifiers)
    bpy.types.VIEW3D_MT_object_clear.remove(draw_object_clear)
    bpy.types.VIEW3D_MT_object_apply.remove(draw_object_apply)
    bpy.types.VIEW3D_MT_object_cleanup.remove(draw_object_cleanup)
    bpy.types.VIEW3D_MT_editor_menus.remove(draw_editor_menus)
    bpy.types.VIEW3D_MT_select_edit_mesh.remove(draw_select_edit_mesh)
    bpy.types.VIEW3D_MT_select_object.remove(draw_select_object)
    bpy.types.NODE_MT_view.remove(draw_node_view)
    bpy.types.TOPBAR_MT_render.remove(draw_topbar_render)
    bpy.types.TOPBAR_MT_file_cleanup.remove(draw_topbar_file_cleanup)
