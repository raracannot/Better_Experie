# 顶点颜色面板优化

import bpy
import bmesh
import math

class BetterExperie_VertexColorSettings(bpy.types.PropertyGroup):
    color: bpy.props.FloatVectorProperty(
        name="颜色",
        subtype='COLOR',
        size=4,
        min=0.0, max=1.0,
        default=(1.0, 1.0, 1.0, 1.0),
        description="要应用的颜色"
    )

    blend_mode: bpy.props.EnumProperty(
        name="混合模式",
        description="颜色应用的混合方式",
        items=[
            ('REPLACE', "替换", "直接替换为新颜色"),
            ('ADD', "添加", "与原颜色相加"),
            ('SUBTRACT', "减去", "从原颜色中减去"),
            ('MULTIPLY', "相乘", "与原颜色相乘"),
            ('LIGHTEN', "变亮", "保留两者中较亮的值"),
            ('DARKEN', "变暗", "保留两者中较暗的值"),
        ],
        default='REPLACE'
    )

    threshold: bpy.props.FloatProperty(
        name="阈值",
        description="颜色匹配的容差阈值（0为完全一致，越大越宽松）",
        default=0.2,
        min=0.0, max=2.0
    )


def _blend_color(old_c, new_c, mode):
    if mode == 'REPLACE':
        return new_c

    res = [0.0, 0.0, 0.0, 0.0]
    for i in range(4):
        if mode == 'ADD':
            res[i] = min(old_c[i] + new_c[i], 1.0)
        elif mode == 'SUBTRACT':
            res[i] = max(old_c[i] - new_c[i], 0.0)
        elif mode == 'MULTIPLY':
            res[i] = old_c[i] * new_c[i]
        elif mode == 'LIGHTEN':
            res[i] = max(old_c[i], new_c[i])
        elif mode == 'DARKEN':
            res[i] = min(old_c[i], new_c[i])
    return tuple(res)


def _color_distance(c1, c2):
    return math.sqrt((c1[0] - c2[0]) ** 2 + (c1[1] - c2[1]) ** 2 + (c1[2] - c2[2]) ** 2)


class BetterExperie_OT_MeshApplyVertexColor(bpy.types.Operator):
    bl_idname = "better_experie.mesh_apply_vertex_color"
    bl_label = "应用顶点颜色"
    bl_description = "将颜色应用到顶点"
    bl_options = {'REGISTER', 'UNDO'}

    only_selected: bpy.props.BoolProperty(
        name="仅应用所选",
        description="如果为True，则仅应用到选中的顶点；否则应用到全部",
        default=False
    )

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return (obj and obj.type == 'MESH' and context.mode == 'EDIT_MESH' and obj.data.color_attributes.active_color)

    def execute(self, context):
        obj = context.active_object
        mesh = obj.data
        settings = context.scene.better_experie_vertex_color_settings
        target_color = settings.color
        blend_mode = settings.blend_mode

        active_color_attr = mesh.color_attributes.active_color
        if not active_color_attr:
            self.report({'WARNING'}, "没有活动的颜色属性层！")
            return {'CANCELLED'}

        domain = active_color_attr.domain
        layer_name = active_color_attr.name

        bm = bmesh.from_edit_mesh(mesh)

        if domain == 'CORNER':
            color_layer = bm.loops.layers.color.get(layer_name)
            if not color_layer:
                self.report({'WARNING'}, "无法获取面拐角颜色层！")
                return {'CANCELLED'}

            for face in bm.faces:
                for loop in face.loops:
                    if not self.only_selected or loop.vert.select:
                        old_color = loop[color_layer]
                        loop[color_layer] = _blend_color(old_color, target_color, blend_mode)

        elif domain == 'POINT':
            color_layer = bm.verts.layers.color.get(layer_name)
            if not color_layer:
                color_layer = bm.verts.layers.float_color.get(layer_name)

            if not color_layer:
                self.report({'WARNING'}, "无法获取顶点颜色层！")
                return {'CANCELLED'}

            for vert in bm.verts:
                if not self.only_selected or vert.select:
                    old_color = vert[color_layer]
                    vert[color_layer] = _blend_color(old_color, target_color, blend_mode)
        else:
            self.report({'WARNING'}, f"不支持的颜色属性域: {domain}")
            return {'CANCELLED'}

        bmesh.update_edit_mesh(mesh)
        return {'FINISHED'}


class BetterExperie_OT_MeshSelectSimilarVertexColor(bpy.types.Operator):
    bl_idname = "better_experie.mesh_select_similar_vertex_color"
    bl_label = "选中相似颜色"
    bl_description = "选中颜色与当前设定颜色相近的顶点"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return (obj and obj.type == 'MESH' and context.mode == 'EDIT_MESH' and obj.data.color_attributes.active_color)

    def execute(self, context):
        obj = context.active_object
        mesh = obj.data
        settings = context.scene.better_experie_vertex_color_settings
        target_color = settings.color
        threshold = settings.threshold

        active_color_attr = mesh.color_attributes.active_color
        if not active_color_attr:
            self.report({'WARNING'}, "没有活动的颜色属性层！")
            return {'CANCELLED'}

        domain = active_color_attr.domain
        layer_name = active_color_attr.name

        # 强制切换到点模式，在点模式完成选取计算更稳定
        tool_settings = context.tool_settings
        original_select_mode = tuple(tool_settings.mesh_select_mode)
        tool_settings.mesh_select_mode = (True, True, True)

        bm = bmesh.from_edit_mesh(mesh)

        for v in bm.verts:
            v.select = False
        for e in bm.edges:
            e.select = False
        for f in bm.faces:
            f.select = False

        try:
            if domain == 'CORNER':
                color_layer = bm.loops.layers.color.get(layer_name)
                if not color_layer:
                    color_layer = bm.loops.layers.float_color.get(layer_name)

                if not color_layer:
                    self.report({'WARNING'}, "无法获取面拐角颜色层！")
                    return {'CANCELLED'}

                for face in bm.faces:
                    for loop in face.loops:
                        loop_color = loop[color_layer]
                        if _color_distance(loop_color, target_color) <= threshold:
                            loop.vert.select = True

            elif domain == 'POINT':
                color_layer = bm.verts.layers.color.get(layer_name)
                if not color_layer:
                    color_layer = bm.verts.layers.float_color.get(layer_name)

                if not color_layer:
                    self.report({'WARNING'}, "无法获取顶点颜色层！")
                    return {'CANCELLED'}

                for vert in bm.verts:
                    vert_color = vert[color_layer]
                    if _color_distance(vert_color, target_color) <= threshold:
                        vert.select = True

            bm.select_flush_mode()
        finally:
            # 选取完成后，还原至原始模式
            tool_settings.mesh_select_mode = original_select_mode
            bmesh.update_edit_mesh(mesh)
        return {'FINISHED'}


def draw_vertex_color_tool(self, context):
    if context.mode != 'EDIT_MESH':
        return

    layout = self.layout
    settings = context.scene.better_experie_vertex_color_settings

    box = layout.box()
    row = box.row(align=True)
    row.prop(settings, "color", text="")
    row.prop(settings, "blend_mode", text="")
    row.separator()
    row.prop(settings, "threshold", text="阈值")

    row = box.row(align=True)
    op_all = row.operator("better_experie.mesh_apply_vertex_color", text="写入全部", icon='SNAP_FACE')
    op_all.only_selected = False
    op_sel = row.operator("better_experie.mesh_apply_vertex_color", text="写入所选", icon='SNAP_FACE_CENTER')
    op_sel.only_selected = True
    row.separator()
    row.operator("better_experie.mesh_select_similar_vertex_color", text="选中颜色", icon='RESTRICT_SELECT_OFF')


classes = (
    BetterExperie_VertexColorSettings,
    BetterExperie_OT_MeshApplyVertexColor,
    BetterExperie_OT_MeshSelectSimilarVertexColor,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.better_experie_vertex_color_settings = bpy.props.PointerProperty(type=BetterExperie_VertexColorSettings)
    bpy.types.DATA_PT_vertex_colors.append(draw_vertex_color_tool)


def unregister():
    bpy.types.DATA_PT_vertex_colors.remove(draw_vertex_color_tool)
    del bpy.types.Scene.better_experie_vertex_color_settings
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
