# 快速烘焙节点
import os
import bpy
import tempfile

def create_image(image_name, res, alpha=True, float_buffer=False, color=(0.0, 0.0, 0.0, 1.0)):
    images = bpy.data.images[:]
    bpy.ops.image.new(
        name=image_name,  width=res,  height=res, color=color, alpha=alpha, 
        generated_type='BLANK', float=float_buffer, use_stereo_3d=False, tiled=False)
    image = [i for i in bpy.data.images if i not in images]
    if image:
        return image[0]
    return None
    
def bake_texture(context, obj, mat, active_node, res, bg_color=(0.0, 0.0, 0.0, 1.0), float_buffer=False, bake_type="EMIT", samples_to_use=1, device="GPU"):
    # 检查并确保物体有活动的UV层
    if not obj.data.uv_layers:
        # 如果没有UV层，创建一个
        original_mode = obj.mode
        #uv_layer = obj.data.uv_layers.new(name="GeneratedUVMap")
        #uv_layer.active = True
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.uv.smart_project(island_margin = 0.01)
        bpy.ops.object.mode_set(mode=original_mode)
        uv_layer = obj.data.uv_layers.active
    else:
        # 如果有UV层但没有活动的，设置第一个为活动
        if not obj.data.uv_layers.active:
            obj.data.uv_layers[0].active = True
    
    # 烘焙前确保当前物体不隐藏    
    original_hide_render = obj.hide_render
    obj.hide_render = False

    image_name = obj.name + f"_{active_node.name}_{res}"
    img = create_image(image_name, res, color=bg_color, float_buffer=float_buffer)
    # if image_name not in bpy.data.images.keys():
        # img = create_image(image_name, res, color=bg_color, float_buffer=float_buffer)
    # else:
        # bpy.data.images.remove(bpy.data.images[image_name])
        # img = create_image(image_name, res, color=bg_color, float_buffer=float_buffer)

    nodes = mat.node_tree.nodes
    links = mat.node_tree.links

    texture_node = nodes.new('ShaderNodeTexImage')
    texture_node.name = 'Texture_Bake_Node'
    texture_node.location = -900, -200
    texture_node.select = True
    nodes.active = texture_node
    texture_node.image = img

    engine = bpy.context.scene.render.engine
    og_device = bpy.context.scene.cycles.device
    use_direct = bpy.context.scene.render.bake.use_pass_direct
    use_indirect = bpy.context.scene.render.bake.use_pass_indirect
    use_clear = bpy.context.scene.render.bake.use_clear
    use_selected_to_active = bpy.context.scene.render.bake.use_selected_to_active

    bpy.context.scene.render.engine = 'CYCLES'
    samples = bpy.context.scene.cycles.samples
    
    bpy.context.scene.render.bake.use_selected_to_active = False
    bpy.context.scene.render.bake.use_clear = False
    bpy.context.scene.cycles.samples = samples_to_use
    bpy.context.scene.cycles.device = device
    bpy.context.view_layer.objects.active = obj
    
    #执行烘焙
    bpy.ops.object.bake(type=bake_type)
    # --------- 保存到临时目录，并打包到blend，删除临时文件 ---------

    if not img:
        return "错误"
    # 使用tempfile模块创建安全的临时文件
    temp_dir = tempfile.gettempdir()
    temp_path = os.path.join(temp_dir, f"{image_name}.png")
    img.save_render(temp_path)

    img.pack()
    try:
        os.remove(temp_path)
    except Exception as e:
        print("删除临时图片失败：", e)
    # ---------------------------------------------------

    # 恢复设置
    bpy.context.scene.render.engine = engine
    bpy.context.scene.cycles.device = og_device
    bpy.context.scene.cycles.samples = samples
    bpy.context.scene.render.bake.use_pass_direct = use_direct
    bpy.context.scene.render.bake.use_pass_indirect = use_indirect
    bpy.context.scene.render.bake.use_clear = use_clear
    bpy.context.scene.render.bake.use_selected_to_active = use_selected_to_active
    
    obj.hide_render = original_hide_render
    
    return texture_node

def sockets(self, context):
    if context.active_node:
        outputs = [a for a in context.active_node.outputs if a.enabled]
        if outputs:
            return [(str(i), a.label if a.label else a.name, a.label if a.label else a.name) for i, a in enumerate(outputs)]
    # 如果没有有效输出，提供一个默认选项
    return [("None", "无可用输出", "无可用输出")]


# DEFAULT_UV = [("None", "无UV层", "无UV层")]
def update_uv():
    global DEFAULT_UV
    obj = bpy.context.active_object
    items = []
    if obj and obj.type == "MESH":
        for i, layer in enumerate(obj.data.uv_layers):
            if layer:
                items.append((str(i), str(layer.name), ""))
    DEFAULT_UV = items if items else [("None", "无UV层", "无UV层")]
    
    
class BetterExperie_OT_BakeANode(bpy.types.Operator):
    bl_idname = "better_experie.bake_a_node"
    bl_label = "烘焙节点"
    bl_description = "将选中的节点输出烘焙为贴图（仅着色器可用）\n请确保【场景已选中活动网格】【节点树已选中活动节点】"
    bl_options = {"REGISTER", "UNDO"}

    res: bpy.props.IntProperty(default=1024, min = 2, max=8192, name="分辨率")
    samples_to_use: bpy.props.IntProperty(default=1, min = 1, max=128, name="采样数")
    socket: bpy.props.EnumProperty(items=sockets, options={'SKIP_SAVE'}, name="烘焙输出口")
    margin: bpy.props.IntProperty(default=16, min = 0, name="边距")
    device: bpy.props.EnumProperty(
        items=(("CPU", "CPU", "使用CPU进行烘焙"), ("GPU", "GPU", "使用GPU进行烘焙")),
        default=1, name="烘焙时使用设备")
    replace: bpy.props.BoolProperty(default=False, name="用烘焙结果替换节点", options={'SKIP_SAVE'})
    anotheruv: bpy.props.BoolProperty(default=False, name="使用其他UV通道", options={'SKIP_SAVE'})
    uvsource: bpy.props.EnumProperty(items=lambda self, context: DEFAULT_UV, name="UV通道")
    bg_color: bpy.props.FloatVectorProperty(
        size=4, subtype='COLOR', soft_max=1, soft_min=0,
        default=[0, 0, 0, 1.0], name="背景色")
    float_buffer: bpy.props.BoolProperty(default=False, name="32位浮点")
    blend: bpy.props.FloatProperty(name="边界混合", default=2.5, min = 0)
    hardness: bpy.props.FloatProperty(name="边界硬度", default=1.5, min = 0)
    bake_mode: bpy.props.EnumProperty(
        items=(
            ("UV", "烘焙为UV", "烘焙到对象的UV上"),
            ("PLANE", "烘焙为平面", "烘焙到正方形贴图上"),
        ),default="UV",name="烘焙模式")
        
    @classmethod
    def poll(cls, context):
        return context.area.type == 'NODE_EDITOR' and context.material and context.active_node and context.selected_objects and context.selected_nodes

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "bake_mode", expand=True)
        
        layout.prop(self, "res")
        layout.prop(self, "samples_to_use")
        layout.prop(self, "margin")
        layout.prop(self, "device")
        layout.prop(self, "socket")
        layout.prop(self, "bg_color")
        layout.prop(self, "float_buffer")
        layout.prop(self, "replace")

        if self.bake_mode == "UV":
            uv_layers = context.active_object.data.uv_layers
            if len(uv_layers) > 0:
                layout.prop(self, "anotheruv", toggle=True, icon="TRIA_DOWN")
                if self.anotheruv:
                    layout.prop(self, "uvsource")
            else:
                layout.label(text="未找到UV，将自动生成", icon='ERROR')
            
    def execute(self, context):
        socket = eval(self.socket)
        
        mat = context.material
        obj = context.active_object
        active_node = context.active_node

        if not active_node:
            self.report({'ERROR'}, "未找到活动节点")
            return {'CANCELLED'}
        
        if len(active_node.outputs) < 1:
            self.report({'ERROR'}, "所选节点不包含输出口")
            return {'CANCELLED'}
        
        # 记录所选节点的位置
        active_node_location = (active_node.location.x, active_node.location.y)

        node_tree = mat.node_tree
        last_output_socket = None
        output_node = None
        baked_node = None
        last_active_uv = None
        delete_output = False
        og_margin = bpy.context.scene.render.bake.margin
        bpy.context.scene.render.bake.margin = self.margin

        # 临时平面相关变量
        temp_plane = None
        original_obj = obj  # 保存原始对象引用

        for n in node_tree.nodes:
            if n.type == 'OUTPUT_MATERIAL' and n.is_active_output:
                output_node = n
                if n.inputs[0].is_linked:
                    last_output_socket = n.inputs[0].links[0].from_socket
        if not output_node:
            output_node = node_tree.nodes.new(type='ShaderNodeOutputMaterial')
            delete_output = True

        if self.anotheruv and self.uvsource != "None":
            for a in obj.data.uv_layers:
                if a.active:
                    last_active_uv = a
            for a in obj.data.uv_layers:
                if a.name == self.uvsource:
                    a.active = True

        # 根据烘焙模式选择不同的烘焙逻辑
        if self.bake_mode == "PLANE": #烘焙为平面
            # 创建临时平面
            bpy.ops.mesh.primitive_plane_add(size=1, enter_editmode=False, location=(0, 0, 0))
            temp_plane = bpy.context.active_object
            temp_plane.name = "BakeTempPlane"
            
            # 为临时平面创建并分配材质
            temp_mat = bpy.data.materials.new(name="TempBakeMaterial")
            # temp_mat.use_nodes = True
            temp_plane.data.materials.append(temp_mat)
            
            # 复制原始材质节点到临时材质
            temp_nodes = temp_mat.node_tree.nodes
            temp_links = temp_mat.node_tree.links
            
            # 清除默认节点
            for node in temp_nodes:
                temp_nodes.remove(node)
                
            # 复制节点
            node_mapping = {}
            for node in mat.node_tree.nodes:
                new_node = temp_nodes.new(type=node.bl_idname)
                # 复制节点属性
                for attr in node.bl_rna.properties:
                    if not attr.is_readonly:
                        try:
                            setattr(new_node, attr.identifier, getattr(node, attr.identifier))
                        except:
                            pass  # 忽略无法复制的属性
                new_node.location = node.location
                node_mapping[node] = new_node
            
            # 复制链接
            for link in mat.node_tree.links:
                from_node = node_mapping.get(link.from_node)
                to_node = node_mapping.get(link.to_node)
                if from_node and to_node:
                    from_socket = from_node.outputs[link.from_socket.name]
                    to_socket = to_node.inputs[link.to_socket.name]
                    temp_links.new(from_socket, to_socket)
            
            # 设置临时平面为活动对象
            obj = temp_plane
            
            # 为临时平面创建UV
            bpy.ops.object.mode_set(mode='EDIT')
            bpy.ops.mesh.select_all(action='SELECT')
            bpy.ops.uv.unwrap()
            bpy.ops.object.mode_set(mode='OBJECT')
            
            # 使用临时材质进行烘焙
            mat = temp_mat
            active_node = node_mapping.get(active_node)
            if not active_node:
                self.report({'ERROR'}, "无法在临时材质中找到对应节点")
                return {'CANCELLED'}
        
            # 烘焙逻辑（使用临时材质的节点树）
            temp_node_tree = temp_mat.node_tree
            temp_output_node = temp_nodes.get("Material Output")
            if not temp_output_node:
                temp_output_node = temp_nodes.new(type='ShaderNodeOutputMaterial')
            
            temp_baked_node = None
            
            if active_node.outputs[socket].type != "SHADER":
                viewer_node = temp_nodes.new(type='ShaderNodeEmission')
                temp_links.new(active_node.outputs[socket], viewer_node.inputs[0])
                temp_links.new(viewer_node.outputs[0], temp_output_node.inputs[0])
                temp_baked_node = bake_texture(
                    context, obj, temp_mat, active_node, self.res,
                    bg_color=self.bg_color,
                    float_buffer=self.float_buffer,
                    samples_to_use=self.samples_to_use,
                    device=self.device
                )
            else:
                temp_links.new(active_node.outputs[0], temp_output_node.inputs[0])
                temp_baked_node = bake_texture(
                    context, obj, temp_mat, active_node, self.res,
                    bg_color=self.bg_color,
                    float_buffer=self.float_buffer,
                    bake_type="COMBINED",
                    samples_to_use=self.samples_to_use,
                    device=self.device
                )
            
            # 将临时材质中的烘焙结果复制到原始材质
            if temp_baked_node and temp_baked_node.image:
                # 在原始材质中创建新的纹理节点
                baked_node = node_tree.nodes.new('ShaderNodeTexImage')
                baked_node.name = 'Texture_Bake_Node'
                baked_node.label = 'Baked Texture'
                baked_node.location = active_node_location
                
                # 复制图像数据
                baked_node.image = temp_baked_node.image
                
                # 替换节点逻辑
                if self.replace:
                    for link in active_node.outputs[socket].links:
                        node_tree.links.new(baked_node.outputs[0], link.to_socket)
            else:
                self.report({'ERROR'}, "烘焙失败，无法获取烘焙结果")
                # 删除临时平面
                if temp_plane:
                    bpy.data.objects.remove(temp_plane)
                return {'CANCELLED'}
        
        else: #烘焙到物体UV
            
            viewer_node = None  # 初始化变量
            if active_node.outputs[socket].type != "SHADER":
                viewer_node = node_tree.nodes.new(type='ShaderNodeEmission')
                node_tree.links.new(active_node.outputs[socket], viewer_node.inputs[0])
                node_tree.links.new(viewer_node.outputs[0], output_node.inputs[0])
                baked_node = bake_texture(
                    context, obj, mat, active_node, self.res,
                    bg_color=self.bg_color,
                    float_buffer=self.float_buffer,
                    samples_to_use=self.samples_to_use,
                    device=self.device
                )
            else:
                node_tree.links.new(active_node.outputs[0], output_node.inputs[0])
                baked_node = bake_texture(
                    context, obj, mat, active_node, self.res,
                    bg_color=self.bg_color,
                    float_buffer=self.float_buffer,
                    bake_type="COMBINED",
                    samples_to_use=self.samples_to_use,
                    device=self.device
                )

        # 恢复连接和清理
        if last_output_socket:
            node_tree.links.new(last_output_socket, output_node.inputs[0])
        
        # 只在原始UV模式下删除查看器节点，并确保节点存在
        if self.bake_mode != "PLANE" and viewer_node and viewer_node.name in node_tree.nodes:
            node_tree.nodes.remove(viewer_node)
        
        if last_active_uv:
            last_active_uv.active = True
            
        if baked_node:
            baked_node.location = (active_node_location[0], active_node_location[1] + 300)
            
        if baked_node and self.replace:
            baked_node.location = active_node.location
            if self.anotheruv and self.uvsource != "None":
                uvmap_node = mat.node_tree.nodes.new('ShaderNodeUVMap')
                uvmap_node.uv_map = self.uvsource
                uvmap_node.location = baked_node.location.x - 200, baked_node.location.y
                mat.node_tree.links.new(uvmap_node.outputs[0], baked_node.inputs[0])
            for link in active_node.outputs[socket].links:
                node_tree.links.new(baked_node.outputs[0], link.to_socket)
        
        for node in node_tree.nodes:
            node.select = False
        if baked_node:
            baked_node.select = True
            node_tree.nodes.active = baked_node
        else:
            active_node.select = True
            node_tree.nodes.active = active_node
        
        if delete_output:
            node_tree.nodes.remove(output_node)
        bpy.context.scene.render.bake.margin = og_margin
        
        if temp_plane:
            bpy.data.objects.remove(temp_plane)
            bpy.context.view_layer.objects.active = original_obj
            original_obj.select_set(True)

        return {'FINISHED'}

    def invoke(self, context, event):
        update_uv()
        self.device = bpy.context.scene.cycles.device
        return context.window_manager.invoke_props_dialog(self)
        
        
        

classes = (
    BetterExperie_OT_BakeANode,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
