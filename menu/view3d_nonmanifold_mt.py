
import bpy


class BETTER_EXPERIE_MT_nonmanifold_loop_select(bpy.types.Menu):
    bl_label = "非流形循环选取"
    bl_idname = "BETTER_EXPERIE_MT_nonmanifold_loop_select"

    def draw(self, context):
        layout = self.layout
        layout.operator("better_experie.select_edge_ring_geo", text="选择并排边环（批处理）")
        layout.operator("better_experie.select_edge_ring_interactive", text="选择并排边环（交互）")
        layout.separator()
        layout.operator("better_experie.select_nonmanifold_edge_loop_batch", text="选择非流形循环边（批处理）")
        layout.operator("better_experie.select_nonmanifold_edge_loop", text="选择非流形循环边（交互）")
        layout.separator()
        layout.operator("better_experie.select_face_ring_batch", text="选择非流形循环面（批处理）")
        layout.operator("better_experie.select_face_ring_modal", text="选择非流形循环面（交互）")


classes = (
    BETTER_EXPERIE_MT_nonmanifold_loop_select,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
