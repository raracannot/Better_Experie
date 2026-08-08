# 扫描材质中的AOV节点并自动添加到视图层

import bpy


def find_aov_nodes_in_tree(node_tree, aov_name=None):
    found_nodes = []
    for node in node_tree.nodes:
        if node.bl_idname == 'ShaderNodeGroup' and node.node_tree:
            found_nodes.extend(find_aov_nodes_in_tree(node.node_tree, aov_name))
        if node.bl_idname == 'ShaderNodeOutputAOV' and hasattr(node, 'aov_name'):
            if aov_name is None or node.aov_name == aov_name:
                found_nodes.append(node)
    return found_nodes


class BetterExperie_OT_RescanAOV(bpy.types.Operator):
    bl_idname = "better_experie.rescan_aov"
    bl_label = "自动查找并添加AOV"
    bl_description = "扫描所有材质中的AOV节点，并将缺失的AOV自动加入到视图层列表中"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        view_layer = context.view_layer

        aov_names = set()
        for obj in bpy.data.objects:
            for slot in obj.material_slots:
                mat = slot.material
                if mat and mat.use_nodes and mat.node_tree:
                    for node in find_aov_nodes_in_tree(mat.node_tree, None):
                        if hasattr(node, "aov_name") and node.aov_name:
                            aov_names.add(node.aov_name)

        existing_names = {aov.name for aov in view_layer.aovs}
        added_count = 0

        for name in aov_names:
            if name not in existing_names:
                new_aov = view_layer.aovs.add()
                new_aov.name = name
                added_count += 1

        self.report({'INFO'}, f"已自动查找到并添加了 {added_count} 个 AOV")
        return {'FINISHED'}


def draw_aov_rescan_button(self, context):
    self.layout.operator("better_experie.rescan_aov", icon='FILE_REFRESH')


classes = (
    BetterExperie_OT_RescanAOV,
)

# Cycles 与 EEVEE 各自使用独立的 AOV 面板，仅在对应引擎启用时才存在于 bpy.types
PANEL_TYPES = [
    "CYCLES_RENDER_PT_passes_aov",
    "VIEWLAYER_PT_layer_passes_aov",
]


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    for panel_name in PANEL_TYPES:
        panel_cls = getattr(bpy.types, panel_name, None)
        if panel_cls:
            try:
                panel_cls.append(draw_aov_rescan_button)
            except Exception:
                pass


def unregister():
    for panel_name in PANEL_TYPES:
        panel_cls = getattr(bpy.types, panel_name, None)
        if panel_cls:
            try:
                panel_cls.remove(draw_aov_rescan_button)
            except Exception:
                pass
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
