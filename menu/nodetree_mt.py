# NODE_MT_context_menu 节点编辑面板
import bpy
from ..utils.node_tree import get_image_from_selected_node, get_selected_ramp_nodes, get_selected_curve_nodes

def get_selected_texture_nodes(context):
    results = get_image_from_selected_node(context)
    return list({item[0] for item in results})


# ═══════════════════════════════════════════════════════════
# 主菜单：更好的体验
# ═══════════════════════════════════════════════════════════

class BETTER_EXPERIE_MT_nodetree_submenu(bpy.types.Menu):
    bl_label = "更好的体验"
    bl_idname = "NODETREE_MT_rara_submenu"

    def draw(self, context):
        layout = self.layout
        if context.space_data.type != 'NODE_EDITOR':
            return
        node_tree = context.space_data.edit_tree
        if not node_tree:
            return

        if context.preferences.view.show_developer_ui:
            layout.operator("better_experie.developer_read_node_info", text="【开发者工具】获取活动节点详情信息")

        layout.operator("better_experie.import_clipboard_image_nodeeditor", text="导入剪贴板图像到节点视口")

        selected_nodes = [node for node in node_tree.nodes if node.select]
        if not selected_nodes:
            return

        if get_image_from_selected_node(context):
            layout.menu(BETTER_EXPERIE_MT_texture_tools.bl_idname)
        if get_selected_ramp_nodes(context):
            layout.menu(BETTER_EXPERIE_MT_color_ramp_tools.bl_idname)
        if get_selected_curve_nodes(context):
            layout.menu(BETTER_EXPERIE_MT_curve_submenu.bl_idname)

        if context.space_data.tree_type == 'CompositorNodeTree':
            if context.scene.compositing_node_group is not None and context.active_node is not None:
                layout.separator(type="LINE")
                layout.operator("better_experie.compositor_add_file_output", text="快速生成输出节点", icon="OUTPUT")
                op_bake = layout.operator("better_experie.compositor_bake_node", text="快速烘焙活动节点", icon='MEMORY')
                op_bake.action_type = 'BAKE'
                op_export = layout.operator("better_experie.compositor_bake_node", text="快速导出活动节点", icon='EXPORT')
                op_export.action_type = 'EXPORT'

        if context.space_data.tree_type == 'ShaderNodeTree':
            layout.operator("better_experie.bake_a_node", text="快速烘焙所选节点", icon="OUTPUT")


# ═══════════════════════════════════════════════════════════
# 纹理节点工具菜单
# ═══════════════════════════════════════════════════════════

class BETTER_EXPERIE_MT_texture_tools(bpy.types.Menu):
    bl_label = "纹理节点工具"
    bl_idname = "NODETREE_MT_texture_tools"

    @classmethod
    def poll(cls, context):
        return bool(get_selected_texture_nodes(context))

    def draw(self, context):
        layout = self.layout
        nodes = get_selected_texture_nodes(context)
        if not nodes:
            return

        layout.operator("better_experie.preview_image_modal", text="预览图像节点", icon="IMAGE_RGB")
        layout.operator("better_experie.copy_node_image_to_clipboard", text="复制选中节点图像到剪贴板", icon="COPYDOWN")
        layout.operator("better_experie.import_clipboard_image_nodeeditor", text="从剪贴板粘贴图像到所选节点", icon="PASTEDOWN")
        layout.separator()
        layout.operator("better_experie.open_in_blender_editor", text="在内部编辑器打开图像", icon="MODIFIER")
        layout.operator("better_experie.open_in_external_editor", text="在外部编辑器打开图像", icon="MODIFIER")
        layout.operator("better_experie.reload_image", text="重载图像", icon="FILE_REFRESH")
        layout.operator("better_experie.open_image_folder", text="打开文件夹", icon="FILE_FOLDER")

        node_idnames = {node.bl_idname for node in nodes}
        if {'ShaderNodeTexEnvironment', 'ShaderNodeTexImage'} & node_idnames:
            layout.separator()
            layout.operator("better_experie.convert_environment_and_image", text="转换【图像/环境纹理】", icon="ARROW_LEFTRIGHT")

        layout.separator()
        layout.operator("better_experie.convert_image_to_gradient", text="转换图像为渐变条", icon="SEQ_SPLITVIEW")


# ═══════════════════════════════════════════════════════════
# 颜色渐变工具菜单
# ═══════════════════════════════════════════════════════════

class BETTER_EXPERIE_MT_color_ramp_tools(bpy.types.Menu):
    bl_label = "颜色渐变工具"
    bl_idname = "NODETREE_MT_color_ramp_tools"

    @classmethod
    def poll(cls, context):
        return bool(get_selected_ramp_nodes(context))

    def draw(self, context):
        layout = self.layout
        nodes = get_selected_ramp_nodes(context)
        if not nodes:
            layout.label(text="请选中至少一个颜色渐变条节点", icon='INFO')
            return

        layout.operator("better_experie.color_ramp_copy", text="复制渐变", icon='COPYDOWN')
        layout.operator("better_experie.color_ramp_paste", text="粘贴渐变", icon='PASTEDOWN')
        layout.separator()
        layout.operator("better_experie.color_ramp_flip_positions", text="翻转色标位置", icon="ARROW_LEFTRIGHT")
        layout.operator("better_experie.color_ramp_even_distribution", text="等距色标位置", icon="CENTER_ONLY")
        layout.operator("better_experie.color_ramp_normalize_positions", text="归一色标位置", icon="COLLAPSEMENU")
        layout.operator("better_experie.color_ramp_invert_colors", text="反色色标颜色", icon="IMAGE_ALPHA")
        layout.operator("better_experie.color_ramp_double", text="双色标", icon="NLA_PUSHDOWN")
        layout.operator("better_experie.color_ramp_resample", text="色标重采样", icon="SEQ_LUMA_WAVEFORM")
        layout.operator("better_experie.color_ramp_clean", text="色标清理", icon="PARTICLE_POINT")
        layout.separator()
        layout.operator("better_experie.color_ramp_randomize", text="渐变随机", icon="RNDCURVE")
        layout.operator("better_experie.color_ramp_smooth_contrast", text="渐变平滑", icon="SMOOTHCURVE")
        layout.operator("better_experie.color_ramp_color_mix", text="渐变染色", icon="IMAGE")
        layout.separator()
        layout.operator("better_experie.ramp_lib_popup", text="渐变库", icon="COLOR")


# ═══════════════════════════════════════════════════════════
# 曲线节点工具菜单
# ═══════════════════════════════════════════════════════════

class BETTER_EXPERIE_MT_curve_submenu(bpy.types.Menu):
    bl_label = "曲线节点工具"
    bl_idname = "NODETREE_MT_curve_submenu"

    @classmethod
    def poll(cls, context):
        return bool(get_selected_curve_nodes(context))

    def draw(self, context):
        layout = self.layout
        nodes = get_selected_curve_nodes(context)
        if not nodes:
            layout.label(text="请选中至少一个曲线节点", icon='INFO')
            return

        layout.operator("better_experie.copy_curve", text="复制曲线", icon='COPYDOWN')
        layout.operator("better_experie.paste_curve", text="粘贴曲线", icon='PASTEDOWN')

        layout.separator()
        layout.operator("better_experie.reset_curve_channel", text="重置通道", icon='FILE_REFRESH')
        layout.operator("better_experie.apply_curve_preset", text="应用预设", icon='CURVE_DATA')
        layout.operator("better_experie.simplify_curve", text="精简控制点", icon='PARTICLE_POINT')
        layout.operator("better_experie.subdivide_curve", text="细分控制点", icon='MOD_SUBSURF')
        layout.operator("better_experie.randomize_curve", text="随机控制点", icon='RNDCURVE')
        layout.operator("better_experie.smooth_curve", text="平滑控制点", icon='SMOOTHCURVE')
        layout.operator("better_experie.convert_handle_type", text="转换控制点", icon='IPO_BEZIER')

        layout.separator()
        layout.operator("better_experie.transform_curve", text="水平翻转", icon="RIGHTARROW").action = 'FLIP_X'
        layout.operator("better_experie.transform_curve", text="垂直翻转", icon="DOWNARROW_HLT").action = 'FLIP_Y'
        layout.operator("better_experie.transform_curve", text="高级变换", icon="DRIVER_TRANSFORM").action = 'TRANSFORM'


# ═══════════════════════════════════════════════════════════
# 上下文菜单钩子
# ═══════════════════════════════════════════════════════════

def draw_nodetree_submenu(self, context):
    layout = self.layout
    layout.separator()
    layout.menu(BETTER_EXPERIE_MT_nodetree_submenu.bl_idname)


def texture_tools_draw(self, context):
    if not get_selected_texture_nodes(context):
        return
    self.layout.menu(BETTER_EXPERIE_MT_texture_tools.bl_idname)


def color_ramp_context_draw(self, context):
    if not get_selected_ramp_nodes(context):
        return
    self.layout.menu(BETTER_EXPERIE_MT_color_ramp_tools.bl_idname)


def draw_curve_submenu(self, context):
    if not get_selected_curve_nodes(context):
        return
    self.layout.menu(BETTER_EXPERIE_MT_curve_submenu.bl_idname)


# ═══════════════════════════════════════════════════════════
# 注册
# ═══════════════════════════════════════════════════════════

classes = (
    BETTER_EXPERIE_MT_nodetree_submenu,
    BETTER_EXPERIE_MT_texture_tools,
    BETTER_EXPERIE_MT_color_ramp_tools,
    BETTER_EXPERIE_MT_curve_submenu,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.NODE_MT_context_menu.append(draw_nodetree_submenu)
    bpy.types.NODE_MT_editor_menus.append(texture_tools_draw)
    bpy.types.NODE_MT_editor_menus.append(color_ramp_context_draw)
    bpy.types.NODE_MT_editor_menus.append(draw_curve_submenu)


def unregister():
    bpy.types.NODE_MT_editor_menus.remove(draw_curve_submenu)
    bpy.types.NODE_MT_editor_menus.remove(color_ramp_context_draw)
    bpy.types.NODE_MT_editor_menus.remove(texture_tools_draw)
    bpy.types.NODE_MT_context_menu.remove(draw_nodetree_submenu)
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
