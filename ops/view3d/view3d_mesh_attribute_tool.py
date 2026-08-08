# 顶点属性面板优化

import bpy
import bmesh

class BetterExperie_MeshAttributeSettings(bpy.types.PropertyGroup):
    val_float: bpy.props.FloatProperty(name="浮点值", default=1.0)
    val_int: bpy.props.IntProperty(name="整数值", default=1)
    val_int8: bpy.props.IntProperty(name="8位整数", default=1, min=-128, max=127)
    val_bool: bpy.props.BoolProperty(name="布尔值", default=True)
    val_float2: bpy.props.FloatVectorProperty(name="二维矢量", size=2, default=(1.0, 1.0))
    val_vector: bpy.props.FloatVectorProperty(name="三维矢量", size=3, default=(1.0, 1.0, 1.0))
    val_color: bpy.props.FloatVectorProperty(
        name="颜色值", subtype='COLOR', size=4, min=0.0, max=1.0, default=(1.0, 1.0, 1.0, 1.0)
    )
    val_string: bpy.props.StringProperty(name="字符串", default="")


class BetterExperie_OT_MeshApplyAttribute(bpy.types.Operator):
    bl_idname = "better_experie.mesh_apply_attribute"
    bl_label = "写入属性"
    bl_description = "将设定的数值写入到当前活动的网格属性中"
    bl_options = {'REGISTER', 'UNDO'}

    only_selected: bpy.props.BoolProperty(
        name="仅写入所选",
        description="如果为True，则仅应用到选中的元素；否则应用到全部",
        default=False
    )

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return (obj and obj.type == 'MESH' and context.mode == 'EDIT_MESH' and obj.data.attributes.active)

    def execute(self, context):
        obj = context.active_object
        mesh = obj.data
        settings = context.scene.better_experie_mesh_attribute_settings

        active_attr = mesh.attributes.active
        if not active_attr:
            self.report({'WARNING'}, "没有活动的网格属性！")
            return {'CANCELLED'}

        domain = active_attr.domain
        data_type = active_attr.data_type
        layer_name = active_attr.name

        bm = bmesh.from_edit_mesh(mesh)

        if domain == 'POINT':
            elements = bm.verts
            layers = bm.verts.layers
        elif domain == 'EDGE':
            elements = bm.edges
            layers = bm.edges.layers
        elif domain == 'FACE':
            elements = bm.faces
            layers = bm.faces.layers
        elif domain == 'CORNER':
            elements = bm.faces
            layers = bm.loops.layers
        else:
            self.report({'WARNING'}, f"暂不支持的域: {domain}")
            return {'CANCELLED'}

        target_layer = None
        write_value = None

        if data_type == 'FLOAT':
            target_layer = layers.float.get(layer_name)
            write_value = settings.val_float
        elif data_type == 'INT':
            target_layer = layers.int.get(layer_name)
            write_value = settings.val_int
        elif data_type == 'INT8':
            target_layer = getattr(layers, 'int8', layers.int).get(layer_name)
            write_value = settings.val_int8
        elif data_type == 'BOOLEAN':
            if hasattr(layers, 'boolean'):
                target_layer = layers.boolean.get(layer_name)
                write_value = settings.val_bool
            elif hasattr(layers, 'bool'):
                target_layer = layers.bool.get(layer_name)
                write_value = settings.val_bool
            else:
                target_layer = layers.int.get(layer_name)
                write_value = 1 if settings.val_bool else 0
        elif data_type == 'FLOAT2':
            target_layer = getattr(layers, 'float2', layers.float_vector).get(layer_name)
            if hasattr(layers, 'float2'):
                write_value = (settings.val_float2[0], settings.val_float2[1])
            else:
                write_value = (settings.val_float2[0], settings.val_float2[1], 0.0)
        elif data_type == 'FLOAT_VECTOR':
            target_layer = layers.float_vector.get(layer_name)
            write_value = settings.val_vector
        elif data_type in {'FLOAT_COLOR', 'BYTE_COLOR'}:
            target_layer = layers.float_color.get(layer_name)
            if not target_layer:
                target_layer = layers.color.get(layer_name)
            write_value = settings.val_color
        elif data_type == 'STRING':
            if hasattr(layers, 'string'):
                target_layer = layers.string.get(layer_name)
                write_value = settings.val_string.encode('utf-8')
            else:
                self.report({'WARNING'}, "当前 Blender 版本的 BMesh 不支持字符串层！")
                return {'CANCELLED'}
        else:
            self.report({'WARNING'}, f"暂不支持的数据类型: {data_type}")
            return {'CANCELLED'}

        if not target_layer:
            self.report({'WARNING'}, f"无法在 BMesh 中获取层: {layer_name} ({data_type})")
            return {'CANCELLED'}

        if domain == 'CORNER':
            for face in bm.faces:
                for loop in face.loops:
                    if not self.only_selected or loop.vert.select:
                        loop[target_layer] = write_value
        else:
            for elem in elements:
                if not self.only_selected or elem.select:
                    elem[target_layer] = write_value

        bmesh.update_edit_mesh(mesh)
        return {'FINISHED'}


def draw_mesh_attribute_tool(self, context):
    if context.mode != 'EDIT_MESH':
        return
    obj = context.active_object
    if not obj or obj.type != 'MESH':
        return
    active_attr = obj.data.attributes.active
    if not active_attr:
        return

    layout = self.layout
    settings = context.scene.better_experie_mesh_attribute_settings

    box = layout.box()
    split = box.split(factor=0.3)
    split.label(text="快速写入:")

    row = split.row()
    data_type = active_attr.data_type
    if data_type == 'FLOAT':
        row.prop(settings, "val_float", text="")
    elif data_type == 'INT':
        row.prop(settings, "val_int", text="")
    elif data_type == 'INT8':
        row.prop(settings, "val_int8", text="")
    elif data_type == 'BOOLEAN':
        row.prop(settings, "val_bool", text="")
    elif data_type == 'FLOAT2':
        row.prop(settings, "val_float2", text="")
    elif data_type == 'FLOAT_VECTOR':
        row.prop(settings, "val_vector", text="")
    elif data_type in {'FLOAT_COLOR', 'BYTE_COLOR'}:
        row.prop(settings, "val_color", text="")
    elif data_type == 'STRING':
        row.prop(settings, "val_string", text="")
    else:
        row.label(text=f"暂不支持{active_attr.data_type}数据类型", icon='ERROR')
        return

    row = box.row(align=True)
    op_all = row.operator("better_experie.mesh_apply_attribute", text="写入全部", icon='SNAP_FACE')
    op_all.only_selected = False
    op_sel = row.operator("better_experie.mesh_apply_attribute", text="写入所选", icon='SNAP_FACE_CENTER')
    op_sel.only_selected = True


classes = (
    BetterExperie_MeshAttributeSettings,
    BetterExperie_OT_MeshApplyAttribute,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.better_experie_mesh_attribute_settings = bpy.props.PointerProperty(type=BetterExperie_MeshAttributeSettings)
    bpy.types.DATA_PT_mesh_attributes.append(draw_mesh_attribute_tool)


def unregister():
    bpy.types.DATA_PT_mesh_attributes.remove(draw_mesh_attribute_tool)
    del bpy.types.Scene.better_experie_mesh_attribute_settings
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
