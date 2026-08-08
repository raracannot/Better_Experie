# 材质染色工具：清理颜色 / 随机颜色
# 独立面板注册到属性编辑器材质页签，作为 MATERIAL_PT_viewport 的子面板

import bpy
import random
import mathutils

def _resolve_materials(self, context):
    """按修饰键收集目标材质：无=所选物体所有材质槽（去重），Shift=视图层全部物体所有材质槽（去重）"""
    if self.target_scope == 'ALL':
        objects = list(context.view_layer.objects)
    else:
        objects = list(context.selected_objects)

    materials = set()
    for obj in objects:
        for slot in obj.material_slots:
            if slot.material:
                materials.add(slot.material)
    return list(materials)

def _read_scope(self, event):
    if event.shift:
        self.target_scope = 'ALL'
    else:
        self.target_scope = 'SELECTED'

base_description="\n[左键]点击:为所有选中物体染色\n[Shift+左键]点击:为视图层全部物体染色"

class BetterExperie_OT_MaterialColorClear(bpy.types.Operator):
    bl_idname = "better_experie.material_color_clear"
    bl_label = "清理颜色"
    bl_description = "还原材质视口颜色为默认色" + base_description
    bl_options = {'REGISTER', 'UNDO'}

    target_scope: bpy.props.EnumProperty(
        items=[('SELECTED', "选中", ""), ('ALL', "全部", "")],
        default='SELECTED', options={'HIDDEN'})

    def invoke(self, context, event):
        _read_scope(self, event)
        return self.execute(context)

    def execute(self, context):
        materials = _resolve_materials(self, context)
        for mat in materials:
            mat.diffuse_color = (1.0, 1.0, 1.0, 1.0)
        self.report({'INFO'}, f"已清理 {len(materials)} 个材质颜色")
        return {'FINISHED'}


class BetterExperie_OT_MaterialColorRandom(bpy.types.Operator):
    bl_idname = "better_experie.material_color_random"
    bl_label = "随机颜色"
    bl_description = "随机为材质着色" + base_description
    bl_options = {'REGISTER', 'UNDO'}

    target_scope: bpy.props.EnumProperty(
        items=[('SELECTED', "选中", ""), ('ALL', "全部", "")],
        default='SELECTED', options={'HIDDEN'})
    color_count: bpy.props.IntProperty(
        name="颜色数量", description="0表示每个材质一个颜色；大于0表示在N个颜色的色卡中随机挑选",
        default=0, min=0, max=1000)
    hue_only: bpy.props.BoolProperty(
        name="仅色相随机", description="启用时颜色在HSV的H等距排布，S和V为1，实现亮纯色随机",
        default=False)

    def draw(self, context):
        layout = self.layout
        col = layout.column(align=True)
        col.prop(self, "color_count")
        col.prop(self, "hue_only")
        if self.color_count > 0:
            col.label(text=f"将生成 {self.color_count} 色的色卡供材质随机挑选", icon='INFO')

    def invoke(self, context, event):
        _read_scope(self, event)
        return context.window_manager.invoke_props_dialog(self, width=300)

    def execute(self, context):
        materials = _resolve_materials(self, context)
        if not materials:
            self.report({'WARNING'}, "没有可染色的材质")
            return {'CANCELLED'}

        if self.hue_only:
            n = self.color_count if self.color_count > 0 else len(materials)
            for i, mat in enumerate(materials):
                h = i / n if n > 0 else 0.0
                c = mathutils.Color()
                c.hsv = (h % 1.0, 1.0, 1.0)
                mat.diffuse_color = (c.r, c.g, c.b, 1.0)
        else:
            if self.color_count > 0:
                palette = []
                for _ in range(self.color_count):
                    c = mathutils.Color((random.random(), random.random(), random.random()))
                    palette.append((c.r, c.g, c.b, 1.0))
                for mat in materials:
                    mat.diffuse_color = random.choice(palette)
            else:
                for mat in materials:
                    c = mathutils.Color((random.random(), random.random(), random.random()))
                    mat.diffuse_color = (c.r, c.g, c.b, 1.0)

        self.report({'INFO'}, f"已为 {len(materials)} 个材质随机着色")
        return {'FINISHED'}


# ═══════════════════════════════════════════════════════════════
# 面板：属性编辑器 → 材质页签（MATERIAL_PT_viewport 子面板）
# ═══════════════════════════════════════════════════════════════

class BETTER_EXPERIE_PT_material_dye_tool(bpy.types.Panel):
    bl_label = "材质染色工具"
    bl_idname = "BETTER_EXPERIE_PT_material_dye_tool"
    bl_space_type = 'PROPERTIES'
    bl_options = {'DEFAULT_CLOSED'}
    bl_region_type = 'WINDOW'
    bl_context = "material"
    bl_parent_id = "MATERIAL_PT_viewport"

    @classmethod
    def poll(cls, context):
        return context.material is not None

    def draw(self, context):
        mat = context.material
        if not mat:
            return
        layout = self.layout
        row = layout.row(align=True)
        row.operator("better_experie.material_color_clear", text="清理颜色", icon='X')
        row.operator("better_experie.material_color_random", text="随机颜色", icon='SHADERFX')


classes = (
    BetterExperie_OT_MaterialColorClear,
    BetterExperie_OT_MaterialColorRandom,
    BETTER_EXPERIE_PT_material_dye_tool,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
