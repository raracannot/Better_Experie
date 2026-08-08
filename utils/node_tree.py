
import bpy

def get_current_node_tree(context):
    try:
        space = context.space_data
        tree = space.node_tree
        if hasattr(space, "path") and space.path:
            tree = space.path[-1].node_tree
        # tree = context.space_data.edit_tree    #试试？
        return tree
    except Exception as e:
        return None


def get_selected_ramp_nodes(context):
    try:
        nodes = []
        space = context.space_data
        if space and space.type == 'NODE_EDITOR' and space.node_tree:
            for node in space.node_tree.nodes:
                if node.select and hasattr(node, "color_ramp"):
                    nodes.append(node)
        return nodes
    except Exception:
        return []


def get_selected_curve_nodes(context):
    try:
        nodes = []
        space = context.space_data
        if space and space.type == 'NODE_EDITOR' and space.node_tree:
            for node in space.node_tree.nodes:
                if node.select and hasattr(node, "mapping"):
                    nodes.append(node)
        return nodes
    except Exception:
        return []
        
        
def get_image_from_selected_node(context):
    """
    从节点编辑器中选中的节点提取所有Image对象（自动遍历所有属性和输入）
    :param context: Blender上下文
    :return: [[node, property_path, image]] 格式的列表
             property_path格式示例：'image'、'inputs[0]'、'texture'
    """
    # 初始化返回列表
    node_image_list = []
    # 获取当前节点树
    node_tree = get_current_node_tree(context)
    if not node_tree:
        return node_image_list
    # 找到选中的节点
    selected_nodes = [n for n in node_tree.nodes if n.select]
    if not selected_nodes:
        return node_image_list
    # 遍历所有选中的节点
    for node in selected_nodes:
        # ==================== 1. 遍历节点的所有属性 ====================
        # 获取节点的所有属性名称
        try:
            # 获取节点的所有可访问属性
            node_properties = dir(node)
            for prop_name in node_properties:
                # 跳过内置/私有属性
                if prop_name.startswith(('_', 'bl_', 'rna_', 'type')):
                    continue
                try:
                    # 获取属性值
                    prop_value = getattr(node, prop_name, None)
                    # 验证是否为Image类型
                    if isinstance(prop_value, bpy.types.Image):
                        node_image_list.append([node, prop_name, prop_value])
                except (AttributeError, TypeError, RuntimeError):
                    # 跳过无法访问的属性
                    continue
        except Exception as e:
            continue
        # 遍历节点的所有输入插槽
        if hasattr(node, 'inputs') and node.inputs:
            for input_idx, input_socket in enumerate(node.inputs):
                try:
                    # 获取输入插槽的默认值
                    default_value = getattr(input_socket, 'default_value', None)
                    
                    # 验证是否为Image类型
                    if isinstance(default_value, bpy.types.Image):
                        input_path = f'inputs[{input_idx}]'
                        node_image_list.append([node, input_path, default_value])
                except (AttributeError, TypeError, RuntimeError):
                    # 跳过无法访问的输入插槽
                    continue
        # 遍历节点的所有输出插槽（备用）通常输出不会有Image默认值，但保留此逻辑以备不时之需
        if hasattr(node, 'outputs') and node.outputs:
            for output_idx, output_socket in enumerate(node.outputs):
                try:
                    default_value = getattr(output_socket, 'default_value', None)
                    if isinstance(default_value, bpy.types.Image):
                        output_path = f'outputs[{output_idx}]'
                        node_image_list.append([node, output_path, default_value])
                except (AttributeError, TypeError, RuntimeError):
                    continue
    return node_image_list

def set_image_to_node(node, prop_name, new_image):
    """
    将指定的Image对象设置到节点的指定属性/插槽位置
    :param node: 目标节点对象（bpy.types.Node）
    :param prop_name: 属性路径，支持格式：
                      - 普通属性: 'image'、'texture' 等
                      - 输入插槽: 'inputs[0]'、'inputs[1]' 等
                      - 输出插槽: 'outputs[0]'、'outputs[1]' 等
    :param new_image: 要设置的Image对象（bpy.types.Image）
    :return: 成功返回True，失败返回False
    """
    # 验证输入参数
    if not isinstance(node, bpy.types.Node):
        return False
    if not isinstance(new_image, bpy.types.Image):
        return False
    if not prop_name or not isinstance(prop_name, str):
        return False
    try:
        # 处理输入插槽（inputs[index]）
        if prop_name.startswith('inputs[') and prop_name.endswith(']'):
            # 提取索引值
            try:
                idx_str = prop_name.replace('inputs[', '').replace(']', '')
                input_idx = int(idx_str)
                # 检查索引是否有效
                if hasattr(node, 'inputs') and 0 <= input_idx < len(node.inputs):
                    input_socket = node.inputs[input_idx]
                    # 设置输入插槽的默认值
                    if hasattr(input_socket, 'default_value'):
                        input_socket.default_value = new_image
                        return True
                    else:
                        return False
                else:
                    return False
            except ValueError:
                return False
        # 处理输出插槽（outputs[index]）
        elif prop_name.startswith('outputs[') and prop_name.endswith(']'):
            # 提取索引值
            try:
                idx_str = prop_name.replace('outputs[', '').replace(']', '')
                output_idx = int(idx_str)
                # 检查索引是否有效
                if hasattr(node, 'outputs') and 0 <= output_idx < len(node.outputs):
                    output_socket = node.outputs[output_idx]
                    # 设置输出插槽的默认值
                    if hasattr(output_socket, 'default_value'):
                        output_socket.default_value = new_image
                        return True
                    else:
                        return False
                else:
                    return False  
            except ValueError:
                return False
        # 处理普通属性（如 'image'、'texture' 等）
        else:
            # 检查属性是否存在且可设置
            if hasattr(node, prop_name):
                # 检查属性是否可写
                try:
                    setattr(node, prop_name, new_image)
                    return True
                except (AttributeError, TypeError, RuntimeError) as e:
                    return False
            else:
                return False
    except Exception as e:
        return False
    
 
    
#用于在节点编辑器中，将所选节点实现点击按钮拖动放置操作，非常关键重要
# import bpy
from mathutils import Vector
def stick_selected_node_to_cursor(cursor_location: Vector):
    # Idea from 一尘不染月当天 https://space.bilibili.com/1109241880
    # https://blender.stackexchange.com/questions/218096/translate-area-mouse-coordinates-to-the-the-node-editors-blackboard-coordinates
    selected_nodes = bpy.context.selected_nodes
    # cursor_location = invoke_cursor_location if invoke_cursor_location is not None else bpy.context.space_data.cursor_location
    sum_location = Vector((0, 0))
    node_parent = {}
    node_counter = 0
    for node in bpy.context.selected_nodes:
        if node.parent is not None:
            node_parent[node] = node.parent
            node.parent = None
        if isinstance(node, bpy.types.NodeFrame):
            node.select = False
        else:
            sum_location += node.location
            node_counter += 1
    node_center = Vector((0, 0))
    if node_counter > 0:
        node_center = sum_location / node_counter
    for node in bpy.context.selected_nodes:
        node.location += cursor_location - node_center
    # 必须先invoke再选择，否则frame的位置会不对
    bpy.ops.node.translate_attach_remove_on_cancel('INVOKE_DEFAULT')
    for node in selected_nodes:
        node.select = True
        if node in node_parent:
            node.parent = node_parent[node]

def set_selected_node_to_cursor(cursor_location: Vector):
    # 收集所有选中的节点（包含新创建的节点）
    node_tree = get_current_node_tree(bpy.context)
    selected_nodes = [n for n in node_tree.nodes if n.select]
    if not selected_nodes:
        return  
    
    # 计算选中节点的中心位置（平均位置）
    total_x = 0.0
    total_y = 0.0
    for node in selected_nodes:
        total_x += node.location.x
        total_y += node.location.y
    node_center = Vector((
        total_x / len(selected_nodes),
        total_y / len(selected_nodes)
    ))
    # 计算偏移量（视口中心 - 节点中心）
    offset = cursor_location - node_center
    # 移动所有选中节点到视口中心
    for node in selected_nodes:
        node.location += offset
