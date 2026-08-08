# 一键文件输出

import bpy

class BetterExperie_OT_CompositorAddFileOutput(bpy.types.Operator):
    bl_idname = "better_experie.compositor_add_file_output"
    bl_label = "一键文件输出"
    bl_description = "为选中节点生成【文件输出】节点并连线"

    @classmethod
    def poll(cls, context):
        space = context.space_data
        return (space.type == 'NODE_EDITOR' and
                space.tree_type == 'CompositorNodeTree' and
                context.scene.compositing_node_group is not None and
                context.active_node is not None)

    def execute(self, context):
        ntree = context.scene.compositing_node_group
        # 只取第一个被选中的节点作为目标
        selected_nodes = [n for n in ntree.nodes if n.select]
        if not selected_nodes:
            self.report({'WARNING'}, "请先选中一个节点")
            return {'CANCELLED'}
        node = selected_nodes[0]

        outputs = [out for out in node.outputs if out.enabled]
        if not outputs:
            self.report({'WARNING'}, "所选节点没有可用的输出端口")
            return {'CANCELLED'}

        # 创建文件输出节点
        file_output = ntree.nodes.new('CompositorNodeOutputFile')
        file_output.location.x = node.location.x + 300
        file_output.location.y = node.location.y
        file_output.label = f"{node.name}_文件输出"

        # 设置输出目录和文件名
        render_path = bpy.path.abspath(context.scene.render.filepath)
        base_path = bpy.path.ensure_ext(render_path, "")
        # node_dir = node.name
        if not base_path.endswith("\\"):
            base_path += "\\"
        # base_path = base_path + node_dir + "\\"
        file_output.directory = base_path
        file_output.file_name = node.name

        # 清空 file_output_items（新API，避免崩溃！）
        while len(file_output.file_output_items) > 0:
            file_output.file_output_items.remove(file_output.file_output_items[0])

        # 为每个输出自动添加 file_output_item，并连线
        for i, out in enumerate(outputs):
            item = file_output.file_output_items.new(name=(out.name if out.name else f"Slot_{i+1}"),socket_type="RGBA")
            ntree.links.new(out, file_output.inputs[i])

        self.report({'INFO'}, "已添加文件输出节点并完成连线")
        return {'FINISHED'}


classes = (
    BetterExperie_OT_CompositorAddFileOutput,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
