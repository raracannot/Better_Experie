# 快速添加顶点组

import bpy
import bmesh

VERTEX_GROUP_ITEMS = []

def get_vertex_group_items(self, context):
    global VERTEX_GROUP_ITEMS
    selected_objects = bpy.context.selected_objects[:]
    selected_object_names = sorted([obj.name for obj in selected_objects if obj.type == 'MESH'])

    VERTEX_GROUP_ITEMS = [('CREATE_A_NEW_VERTEX_GROUPS', "新建", "新建一个顶点组")]
    for obj_name in selected_object_names:
        obj = bpy.data.objects.get(obj_name)
        for vg in obj.vertex_groups:
            vg_item = (vg.name, vg.name, f"选择现有的顶点组: {vg.name}")
            if vg_item not in VERTEX_GROUP_ITEMS:
                VERTEX_GROUP_ITEMS.append(vg_item)
 
    return VERTEX_GROUP_ITEMS

class BetterExperie_OT_MeshAddVertexGroup(bpy.types.Operator):
    bl_idname = "better_experie.mesh_add_vertex_group"
    bl_label = "智能顶点组" 
    bl_description = "快速为活动网格添加新的顶点组，支持自定义命名\n\n【回车】确认添加并命名顶点组"
    bl_options = {'REGISTER', 'UNDO'}
    
    operator_mode: bpy.props.EnumProperty(
        name="编辑模式",
        description="设置处理顶点组的模式",
        items=[
            ('ADD', "添加", "添加所选顶点入顶点组"),
            ('REPLACE', "替换", "替换所选顶点为顶点组"),
            ('SUBTRACT', "移除", "移除所选顶点出顶点组"),
        ],default='ADD')
        
    vertex_weight: bpy.props.FloatProperty(name="权重", default=1, min=0, max=1)
    vertex_groups_list: bpy.props.EnumProperty(
        name="顶点组",
        description="指定要处理的顶点组",
        items = get_vertex_group_items)
    new_name: bpy.props.StringProperty(name="新建顶点组", default="",description="新建的顶点组名称")    

    @classmethod
    def poll(cls, context):
        return context.active_object and context.mode == 'EDIT_MESH'
        
    def execute(self, context):
        active_object = context.active_object

        selected_objects = [obj for obj in context.selected_objects if obj.type == 'MESH' and obj.mode == 'EDIT']
        current_mesh_select_mode = context.tool_settings.mesh_select_mode

        all_obj=0
        all_vertex=0
        for obj in selected_objects:
            if obj.type != 'MESH':
                print(f"对象 '{obj.name}' 不是网格类型，已跳过。")
                continue

            bpy.context.view_layer.objects.active = obj
            bm = bmesh.from_edit_mesh(obj.data)
            indices = []

            if current_mesh_select_mode[0]:
                for v in bm.verts:
                    if v.select:
                        indices.append(v.index)
            elif current_mesh_select_mode[1]:
                for e in bm.edges:
                    if e.select:
                        for v in e.verts:
                            indices.append(v.index)
            elif current_mesh_select_mode[2]:
                for f in bm.faces:
                    if f.select:
                        for v in f.verts:
                            indices.append(v.index)
            bm.free()

            bpy.ops.object.mode_set(mode='OBJECT')
            vertex_group = None
            if self.vertex_groups_list == "CREATE_A_NEW_VERTEX_GROUPS":
                vertex_group = obj.vertex_groups.new(name=self.new_name)
            elif obj.vertex_groups.get(self.vertex_groups_list) is None:
                vertex_group = obj.vertex_groups.new(name=self.vertex_groups_list)
            else:
                vertex_group = obj.vertex_groups.get(self.vertex_groups_list)

            all_obj+=1
            if indices:
                vertex_group.add(indices, self.vertex_weight, self.operator_mode)
                all_vertex+=len(indices)

            bpy.ops.object.mode_set(mode='EDIT')

        if active_object:
            bpy.context.view_layer.objects.active = active_object
        self.report({'INFO'}, f"新建【{self.new_name}】顶点组，共{all_obj}个对象，{all_vertex}个顶点")
        return {'FINISHED'}

    def invoke(self, context, event):
        self.vertex_groups_list = "CREATE_A_NEW_VERTEX_GROUPS"
        
        current_mesh_select_mode = context.tool_settings.mesh_select_mode
        if current_mesh_select_mode[0]:
            self.new_name = "verts_group"
        elif current_mesh_select_mode[1]:
            self.new_name = "edges_group"
        elif current_mesh_select_mode[2]:
            self.new_name = "faces_group"

        self.execute(context)
        return {'FINISHED'}
        
    def draw(self, context):
        layout = self.layout
        row = layout.row()
        split = row.split(factor=0.3)
        split.label(text="顶点组")
        row = split.row(align=True)
        row.prop(self, "vertex_groups_list",text="")
        if self.vertex_groups_list == 'CREATE_A_NEW_VERTEX_GROUPS':
            row.prop(self, "new_name",text="") 
        row = layout.row()
        split = row.split(factor=0.3)
        split.label(text="模式")
        split.prop(self, "operator_mode",text="")
        row = layout.row()
        split = row.split(factor=0.3)
        split.label(text="权重")
        split.prop(self, "vertex_weight",text="")

classes = (
    BetterExperie_OT_MeshAddVertexGroup,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
