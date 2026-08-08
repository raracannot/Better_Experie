# SEQUENCER_MT_context_menu 时间轴面板
import bpy


class BETTER_EXPERIE_MT_sequencer_submenu(bpy.types.Menu):
    bl_label = "更好的体验"
    bl_idname = "SEQUENCER_MT_rara_submenu"

    def draw(self, context):
        layout = self.layout

        layout.operator("better_experie.align_strips_left", text="向左对齐", icon="ALIGN_LEFT")
        layout.operator("better_experie.align_strips_right", text="向右对齐", icon="ALIGN_RIGHT")
        layout.operator("better_experie.stack_strips_forward", text="向左堆叠", icon="BACK")
        layout.operator("better_experie.stack_strips_reverse", text="向右堆叠", icon="FORWARD")
        layout.separator()
        layout.operator("better_experie.stack_strips", text="错位堆叠片段", icon="SEQ_STRIP_DUPLICATE")
        layout.operator("better_experie.rotate_strip_positions", text="交换位置", icon="AREA_SWAP")
        layout.separator()
        layout.operator("better_experie.compact_channels", text="清理空轨道", icon="TRASH")


def sequencer_context_draw(self, context):
    if not getattr(context.scene, "sequence_editor", None):
        return
    self.layout.separator()
    self.layout.menu(BETTER_EXPERIE_MT_sequencer_submenu.bl_idname)


classes = (
    BETTER_EXPERIE_MT_sequencer_submenu,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.SEQUENCER_MT_context_menu.append(sequencer_context_draw)


def unregister():
    bpy.types.SEQUENCER_MT_context_menu.remove(sequencer_context_draw)
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
