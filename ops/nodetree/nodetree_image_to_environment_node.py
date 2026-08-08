# 图像与环境转换

import bpy

class BetterExperie_OT_ConvertEnvironmentAndImage(bpy.types.Operator):
    bl_idname = "better_experie.convert_environment_and_image"
    bl_label = "转换"
    bl_options = {'REGISTER', 'UNDO'}
    bl_description = "将图像在环境纹理和图像纹理之间快速转换"
    
    def execute(self, context):
        # 获取当前节点树
        node_tree = context.space_data.edit_tree
        
        if not node_tree:
            self.report({'ERROR'}, "没有激活的节点树")
            return {'CANCELLED'}
        
        # 获取选中的节点
        selected_nodes = [node for node in node_tree.nodes if node.select]
        
        if not selected_nodes:
            self.report({'ERROR'}, "请先选择节点")
            return {'CANCELLED'}
        
        converted_count = 0
        
        # 处理每个选中的节点
        for node in selected_nodes:
            # 确定新节点类型
            if node.bl_idname == 'ShaderNodeTexEnvironment':
                new_node_id = 'ShaderNodeTexImage'
            elif node.bl_idname == 'ShaderNodeTexImage':
                new_node_id = 'ShaderNodeTexEnvironment'
            else:
                # 不是目标类型的节点，跳过
                continue
            # 创建新节点
            new_node = node_tree.nodes.new(type=new_node_id)
            
            # 复制基本属性
            new_node.name = node.name
            new_node.label = node.label
            new_node.location = node.location
            new_node.select = node.select
            new_node.interpolation = node.interpolation
            # 复制图像属性
            if hasattr(node, 'image') and hasattr(new_node, 'image'):
                new_node.image = node.image
            # 记录并重新连接输入
            input_links = []
            for input_socket in node.inputs:
                for link in input_socket.links:
                    input_links.append((link.from_socket, input_socket.name))
            # 记录并重新连接输出
            output_links = []
            for output_socket in node.outputs:
                for link in output_socket.links:
                    output_links.append((output_socket.name, link.to_socket))
            # 建立新的输入连接
            for from_socket, input_name in input_links:
                if input_name in new_node.inputs:
                    node_tree.links.new(from_socket, new_node.inputs[input_name])
            # 建立新的输出连接
            for output_name, to_socket in output_links:
                if output_name in new_node.outputs:
                    node_tree.links.new(new_node.outputs[output_name], to_socket)
            # 删除原始节点
            node_tree.nodes.remove(node)
            converted_count += 1
        
        self.report({'INFO'}, f"已转换 {converted_count} 个节点")
        return {'FINISHED'}
        
classes = (
    BetterExperie_OT_ConvertEnvironmentAndImage,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
