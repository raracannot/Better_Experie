# 图像与剪贴板

import bpy
import re 
from ...utils.node_tree import get_current_node_tree
from ...utils.clipboard_image import import_image_from_clipboard,copy_image_to_clipboard,has_content_in_clipboard

def new_image_node(node_tree , bimg):
    ui_type = bpy.context.area.ui_type
    if ui_type == "ShaderNodeTree":
        RENDERER_NODE_MAPPING = {
            'BLENDER_EEVEE': ('ShaderNodeTexImage', "image"), # EEVEE渲染器
            'BLENDER_EEVEE_NEXT': ('ShaderNodeTexImage', "image"), # EEVEE渲染器
            'CYCLES': ('ShaderNodeTexImage', "image"), # Cycles渲染器
            'BLENDER_WORKBENCH': ('ShaderNodeTexImage', "image"), # Workbench渲染器
            'OCTANE': ('OctaneRGBImage', "image"), # Octane渲染器，已验证

            # 'CORONA': 'CoronaImageNode', #没有对应的渲染器，无法验证
            # 'VRAY': 'VRayTexImage', #没有对应的渲染器，无法验证
        }
        current_renderer = bpy.context.scene.render.engine.upper()
        node_type, socket_path  = RENDERER_NODE_MAPPING.get(current_renderer, ('ShaderNodeTexImage', "image"))
    else:
        NODE_TYPE_MAPPING = {
            'CompositorNodeTree': ('CompositorNodeImage', "image"), 
            'TextureNodeTree': ('TextureNodeImage', "image"), 
            'GeometryNodeTree': ('GeometryNodeImageTexture', "inputs[0]"),
            
            'ScriptingNodesTree': ('SN_IconNode', "icon_file"),
            'WanvasAIFlowNodeTree': ('WanvasAIFlowNodeReferenceInput', "image"), 
        }
        node_type, socket_path  = NODE_TYPE_MAPPING.get(ui_type, ('ShaderNodeTexImage', "image"))
    img_node = node_tree.nodes.new(type=node_type)

    try:
        if match := re.search(r'\[(\d+)\]', socket_path):
            idx = int(match.group(1))    # 提取 0
            target_obj = getattr(img_node, "inputs")[idx]
            target_obj.default_value = bimg
        else:
            # 处理普通属性（如 image、icon_file）
            setattr(img_node, socket_path, bimg)
    except (AttributeError, IndexError) as e:
        print(f"赋值失败: {e}，节点类型: {node_type}，属性路径: {socket_path}")
        # 降级处理：尝试直接赋值image属性
        if hasattr(img_node, 'image'):
            img_node.image = bimg
    return img_node

def get_image_from_selected_node(context) -> bpy.types.Image | None:
    """
    从节点编辑器中选中的节点提取图像对象
    :param context: Blender上下文
    :return: 成功返回Image对象，失败返回None
    """
    # 获取当前节点树
    node_tree = get_current_node_tree(context)
    if not node_tree:
        print("错误：无法获取节点树")
        return None
    
    # 找到选中的节点
    selected_nodes = [n for n in node_tree.nodes if n.select]
    if not selected_nodes:
        print("错误：未选中任何节点")
        return None
    
    # 遍历选中节点，寻找包含图像的节点
    for node in selected_nodes:
        # 检查常见的图像属性
        if hasattr(node, 'image') and node.image:
            return node.image
        # 检查GeometryNodeImageTexture的输入
        if node.bl_idname == 'GeometryNodeImageTexture' and node.inputs and len(node.inputs) > 0:
            if hasattr(node.inputs[0], 'default_value') and node.inputs[0].default_value:
                return node.inputs[0].default_value
        # 检查其他特殊节点的图像属性
        for attr in ['icon_file', 'texture']:
            if hasattr(node, attr) and getattr(node, attr):
                return getattr(node, attr)
    
    print("错误：选中的节点不包含有效图像")
    return None
    
    
#导入剪贴板图像到三维视口
class BetterExperie_OT_ImportClipboardImage_View3D(bpy.types.Operator):
    bl_idname = "better_experie.import_clipboard_image_view3d"
    bl_label = "导入剪贴板图像到三维视口"
    bl_options = {'REGISTER', 'UNDO'}
    bl_description = "将剪贴板中的图像导入到三维视口，创建带材质的平面或图像空物体\n支持adobe剪贴板、office剪贴板、截图、复制的图像文件"

    create_view_3d: bpy.props.EnumProperty(
        name="三维模式下的新建内容",
        items=[
            ('PLANE', "网格图像", ""),
            ('EMPTY', "空物体图像", ""),
        ], default='PLANE')
    
    @classmethod
    def poll(cls, context):
        return context.space_data.type == 'VIEW_3D' and has_content_in_clipboard()

    def execute(self, context):
        # 获取剪贴板图像
        try:
            bimg = import_image_from_clipboard()
            if bimg is None:
                self.report({'ERROR'}, "剪贴板中没有有效的图像数据或粘贴失败")
                return {'CANCELLED'}
        except Exception as e:
            self.report({'ERROR'}, f"获取剪贴板内容失败: {str(e)}")
            return {'CANCELLED'}

        # 仅创建三维视口内容
        try:
            if self.create_view_3d == "PLANE":
                self.create_plane(context, bimg)
            else:
                self.create_empty(context, bimg)
        except Exception as e:
            self.report({'ERROR'}, f"创建三维物体失败: {str(e)}")
            return {'CANCELLED'}

        self.report({'INFO'}, "成功从剪贴板导入图像到三维视口")
        return {'FINISHED'}

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "create_view_3d", text="新建类型")

    def create_plane(self, context, bimg):
        width, height = bimg.size
        bpy.ops.mesh.primitive_plane_add(
            size=1.0,
            location=(0, 0, 0),
            rotation=(0, 0, 0)
        )
        plane = bpy.context.active_object
        plane.name = "Clipboard Image Plane"
        plane.scale.x = width / 100
        plane.scale.y = height / 100
        plane.scale.z = 1.0
        
        # 创建材质
        material = bpy.data.materials.new(name="Clipboard Image Materials")
        material.use_nodes = True
        
        nodes = material.node_tree.nodes
        links = material.node_tree.links
        # 清空默认节点
        for node in nodes:
            nodes.remove(node)
        # 创建图像纹理节点
        tex_image = nodes.new('ShaderNodeTexImage')
        tex_image.image = bimg
        tex_image.interpolation = 'Smart'
        tex_image.location = (-300, 0)
        # 创建 Principled BSDF 节点
        bsdf = nodes.new('ShaderNodeBsdfPrincipled')
        bsdf.location = (0, 0)
        # 创建输出节点
        output = nodes.new('ShaderNodeOutputMaterial')
        output.location = (300, 0)
        # 连接节点
        links.new(bsdf.inputs['Base Color'], tex_image.outputs['Color'])
        links.new(output.inputs['Surface'], bsdf.outputs['BSDF'])
        # 处理透明通道
        if bimg.alpha_mode != 'NONE':
            if 'Alpha' in bsdf.inputs:
                links.new(bsdf.inputs['Alpha'], tex_image.outputs['Alpha'])
            material.blend_method = 'BLEND'
        
        # 将材质赋给平面
        if plane.data.materials:
            plane.data.materials[0] = material
        else:
            plane.data.materials.append(material)

    def create_empty(self, context, bimg):
        bpy.ops.object.empty_add(type='IMAGE', location=(0, 0, 0))
        empty = bpy.context.active_object
        empty.name = "Clipboard Image Empty"
        empty.data = bimg
        width, height = bimg.size
        empty.empty_display_size = max(width, height) / 100


#导入剪贴板图像到节点视口
class BetterExperie_OT_ImportClipboardImage_NodeEditor(bpy.types.Operator):
    bl_idname = "better_experie.import_clipboard_image_nodeeditor"
    bl_label = "导入剪贴板图像到节点视口"
    bl_options = {'REGISTER', 'UNDO'}
    bl_description = "将剪贴板中的图像导入到节点编辑器，创建对应的图像节点\n支持材质、合成、几何等各类节点编辑器"

    @classmethod
    def poll(cls, context):
        return context.space_data.type == 'NODE_EDITOR' and has_content_in_clipboard()

    def execute(self, context):
        # 获取剪贴板图像
        try:
            bimg = import_image_from_clipboard()
            if bimg is None:
                self.report({'ERROR'}, "剪贴板中没有有效的图像数据或粘贴失败")
                return {'CANCELLED'}
        except Exception as e:
            self.report({'ERROR'}, f"获取剪贴板内容失败: {str(e)}")
            return {'CANCELLED'}

        node_tree = get_current_node_tree(context)
        if not node_tree:
            self.report({'ERROR'}, f"创建节点失败，无法获取节点树")
            return {'CANCELLED'}
                
        have_node_image = False
        try:
            # 找到选中的节点
            selected_nodes = [n for n in node_tree.nodes if n.select]
            if selected_nodes:
                # 遍历选中节点，寻找包含图像的节点
                for node in selected_nodes:
                    handled = False
                    # 检查常见的图像属性
                    if hasattr(node, 'image') and node.image:
                        node.image = bimg
                        have_node_image = True
                        handled = True
                        break
                    # 检查GeometryNodeImageTexture的输入
                    if node.bl_idname == 'GeometryNodeImageTexture' and node.inputs and len(node.inputs) > 0:
                        if hasattr(node.inputs[0], 'default_value') and node.inputs[0].default_value:
                            node.inputs[0].default_value = bimg
                            have_node_image = True
                            handled = True
                            break
                    # 检查其他特殊节点的图像属性
                    for attr in ['icon_file', 'texture']:
                        if hasattr(node, attr) and getattr(node, attr):
                            setattr(node, attr, bimg)
                            have_node_image = True
                            handled = True
                            break
                    if handled:
                            break
        except Exception as e:
            have_node_image = False
            print(f"应用图像参数失败: {str(e)}，接下来尝试新建节点")

        if have_node_image:
            self.report({'INFO'}, "成功将剪贴板图像写入所选节点")
        else:
            try:
                # 仅创建节点内容
                img_node = new_image_node(node_tree, bimg)
                img_node.name = "Clipboard_Image_Node"
                img_node.label = "Clipboard Image"

                # ====================== 核心：强制居中 ======================
                region = context.region
                rv2d = context.region.view2d

                # 视口中心坐标（像素）
                x = region.width / 2.0
                y = region.height / 2.0

                # 转换成节点坐标
                view_x, view_y = rv2d.region_to_view(x, y)
                
                # UI 缩放修正
                ui_scale = context.preferences.system.ui_scale
                img_node.location = (view_x / ui_scale, view_y / ui_scale)

                # 选中并居中
                for n in node_tree.nodes:
                    n.select = False
                img_node.select = True
                self.report({'INFO'}, "成功将剪贴板图像粘贴进视口")
            except Exception as e:
                self.report({'ERROR'}, f"创建节点失败: {str(e)}")
                return {'CANCELLED'}
                
        return {'FINISHED'}

    def draw(self, context):
        layout = self.layout
        layout.label(text="将剪贴板图像粘贴至节点组")



#复制选中节点图像到剪贴板操作符
class BetterExperie_OT_CopyNodeImageToClipboard(bpy.types.Operator):
    bl_idname = "better_experie.copy_node_image_to_clipboard"
    bl_label = "复制选中节点图像到剪贴板"
    bl_options = {'REGISTER'}
    bl_description = "将节点编辑器中选中的图像节点的图像复制到系统剪贴板\n支持ShaderNodeTexImage、GeometryNodeImageTexture等各类图像节点"

    @classmethod
    def poll(cls, context):
        # 只在节点编辑器中显示，且确保有选中节点
        if context.space_data.type != 'NODE_EDITOR':
            return False
        node_tree = get_current_node_tree(context)
        if not node_tree:
            return False
        # 检查是否有选中节点
        selected_nodes = [n for n in node_tree.nodes if n.select]
        return len(selected_nodes) > 0

    def execute(self, context):
        # 从选中节点提取图像
        bimg = get_image_from_selected_node(context)
        print(f"准备复制{bimg}")
        if not bimg:
            self.report({'ERROR'}, "无法从选中节点提取有效图像")
            return {'CANCELLED'}
        
        # 复制图像到剪贴板
        if copy_image_to_clipboard(bimg):
            self.report({'INFO'}, f"成功将图像「{bimg.name}」复制到剪贴板")
            return {'FINISHED'}
        else:
            self.report({'ERROR'}, "复制图像到剪贴板失败")
            return {'CANCELLED'}

classes = (
    BetterExperie_OT_ImportClipboardImage_View3D,    # 三维视口操作符
    BetterExperie_OT_ImportClipboardImage_NodeEditor, # 节点视口操作符
    BetterExperie_OT_CopyNodeImageToClipboard,       # 节点图像复制操作符
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

# if __name__ == "__main__":
    # register()