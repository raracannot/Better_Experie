# 节点工具集

import bpy

class BetterExperie_OT_SetNodeTreeOrigin(bpy.types.Operator):
    bl_idname = "better_experie.set_node_tree_origin"
    bl_label = "设置原点"
    bl_description = "将选中节点位置设为视口原点"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        nodes = context.selected_nodes
        if not nodes:
            self.report({'INFO'}, "没有选中的节点")
            return {'FINISHED'}

        reference_node = nodes[0]

        ref_x = reference_node.location.x
        ref_y = reference_node.location.y
        node_p = reference_node.parent
        while node_p:
            ref_x += node_p.location.x
            ref_y += node_p.location.y
            node_p = node_p.parent

        all_nodes = context.space_data.edit_tree.nodes
        for node in all_nodes:
            if node.parent is None:
                node.location.x -= ref_x
                node.location.y -= ref_y

        bpy.ops.node.view_selected()
        self.report({'INFO'}, f"以节点 {reference_node.name} 为参考，将所有节点移动至原点")
        return {'FINISHED'}

classes = (
    BetterExperie_OT_SetNodeTreeOrigin,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
