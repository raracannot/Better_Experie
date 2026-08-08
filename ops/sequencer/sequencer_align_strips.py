# 片段对齐

import bpy
from ...utils.strips_utils import get_selected_strip_groups


class BetterExperie_OT_AlignStripsLeft(bpy.types.Operator):
    bl_idname = "better_experie.align_strips_left"
    bl_label = "向左对齐"
    bl_description = "将所有选中片段的开头对齐到最早片段的开头，同源组保持相对位置不变"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        sed = getattr(context.scene, "sequence_editor", None)
        return sed and sum(1 for s in sed.strips if s.select) >= 2

    def execute(self, context):
        groups = get_selected_strip_groups(context)
        target = min(min(s.frame_start for s in g) for g in groups)
        for group in groups:
            offset = target - min(s.frame_start for s in group)
            for s in group:
                s.frame_start += offset
        count = sum(len(g) for g in groups)
        self.report({'INFO'}, f"已向左对齐 {count} 个片段（{len(groups)} 组）")
        return {'FINISHED'}


class BetterExperie_OT_AlignStripsRight(bpy.types.Operator):
    bl_idname = "better_experie.align_strips_right"
    bl_label = "向右对齐"
    bl_description = "将所有选中片段的结尾对齐到最晚片段的结尾，同源组保持相对位置不变"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        sed = getattr(context.scene, "sequence_editor", None)
        return sed and sum(1 for s in sed.strips if s.select) >= 2

    def execute(self, context):
        groups = get_selected_strip_groups(context)
        target_end = max(max(s.frame_final_end for s in g) for g in groups)
        for group in groups:
            group_end = max(s.frame_final_end for s in group)
            offset = target_end - group_end
            for s in group:
                s.frame_start += offset
        count = sum(len(g) for g in groups)
        self.report({'INFO'}, f"已向右对齐 {count} 个片段（{len(groups)} 组）")
        return {'FINISHED'}


classes = (
    BetterExperie_OT_AlignStripsLeft,
    BetterExperie_OT_AlignStripsRight,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
