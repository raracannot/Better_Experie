# UV 编辑器的「非流形选取」子菜单

import bpy


class BETTER_EXPERIE_MT_uv_nonmanifold(bpy.types.Menu):
    bl_label = "非流形 UV 选取"
    bl_idname = "BETTER_EXPERIE_MT_uv_nonmanifold"

    def draw(self, context):
        layout = self.layout
        layout.operator("better_experie.uv_select_nonmanifold_edge_loop", text="选择非流形循环边")
        layout.operator("better_experie.uv_select_edge_ring", text="选择并排边环")


def draw_uv_select_submenu(self, context):
    space = context.space_data
    if space is None or not getattr(space, "show_uvedit", False):
        return
    layout = self.layout
    layout.separator()
    layout.menu("BETTER_EXPERIE_MT_uv_nonmanifold")


classes = (
    BETTER_EXPERIE_MT_uv_nonmanifold,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.IMAGE_MT_select.append(draw_uv_select_submenu)


def unregister():
    bpy.types.IMAGE_MT_select.remove(draw_uv_select_submenu)
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
