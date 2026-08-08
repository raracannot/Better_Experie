# 读取节点信息【开发】

import bpy
    
class BetterExperie_OT_DeveloperReadNodeInfo(bpy.types.Operator):
    bl_idname = "better_experie.developer_read_node_info"
    bl_label = "读取节点信息"
    bl_description = '读取选中活动节点的详细信息'

    def execute(self, context):
        active_node = context.active_node
        if not active_node:
            self.report({'INFO'}, "没有选中活动节点")
            return {'FINISHED'}
        message = f"节点信息：\n"
        message += f"名称 = {active_node.name}\n"
        message += f"类型 = '{active_node.bl_idname}'\n"
        message += f"位置 = ({active_node.location.x}, {active_node.location.y})\n"
        message += f"--------------------\n"
        for prop in active_node.bl_rna.properties:
            if prop.identifier not in {
                'name', 'width', 'height', 'bl_width_default', 'bl_width_min', 'bl_width_max',
                'bl_height_default', 'bl_height_min', 'bl_height_max',
            }:
                try:
                    value = getattr(active_node, prop.identifier)
                    message += f"{prop.identifier} = {value}\n"
                except AttributeError:
                    pass
        message += f"--------------------\n"
        for i, input_socket in enumerate(active_node.inputs):
            if input_socket.is_linked:
                linked_node = input_socket.links[0].from_node

                message += f"input[{i}][{input_socket.identifier}] = {linked_node.name}(linked_type='{linked_node.bl_idname}')\n"
            else:
                if hasattr(input_socket, 'default_value'):
                    default_value = input_socket.default_value
                    try:
                        # 判断 default_value 是否为可迭代且非字符串
                        if hasattr(default_value, '__iter__') and not isinstance(default_value, str):
                            values = []
                            for val in default_value:
                                try:
                                    values.append(float(val))
                                except (ValueError, TypeError):
                                    # 不是数字，直接用原值字符串
                                    values.append(str(val))
                            formatted_value = f"({', '.join(map(str, values))})"
                            message += f"input[{i}][{input_socket.identifier}] = {formatted_value}({input_socket.type})\n"
                        else:
                            message += f"input[{i}][{input_socket.identifier}] = {default_value}({input_socket.type})\n"
                    except Exception as e:
                        # 捕获所有异常，防止报错中断
                        message += f"input[{i}][{input_socket.identifier}] = {default_value}({input_socket.type})\n"
                else:
                    message += f"input[{i}] = NONE\n"
        message += f"--------------------\n"
        for i, output_socket in enumerate(active_node.outputs):
            if output_socket.is_linked:
                for link in output_socket.links:
                    to_node = link.to_node
                    message += f"output[{i}][{output_socket.identifier}] = {to_node.name}(linked_type='{to_node.bl_idname}')\n"
            else:
                message += f"output[{i}][{output_socket.identifier}] = NONE ({output_socket.type})\n"
        message += f"--------------------\n"
        self.report({'INFO'}, message)
        return {'FINISHED'}
        
        
classes = (
    BetterExperie_OT_DeveloperReadNodeInfo,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
