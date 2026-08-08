# 简单堆叠（无弹窗）

import bpy
from ...utils.strips_utils import get_selected_strip_groups


class BetterExperie_OT_StackStripsForward(bpy.types.Operator):
    bl_idname = "better_experie.stack_strips_forward"
    bl_label = "正向堆叠"
    bl_description = "将选中片段按同源分组后首尾相连正向堆叠，同组内保持相对位置不变"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        sed = getattr(context.scene, "sequence_editor", None)
        return sed and sum(1 for s in sed.strips if s.select) >= 2

    def execute(self, context):
        groups = get_selected_strip_groups(context)
        if len(groups) < 2:
            self.report({'WARNING'}, "请至少选中 2 组片段")
            return {'CANCELLED'}
        prev_end = None
        for group in groups:
            if prev_end is not None:
                group_start = min(s.frame_start for s in group)
                offset = prev_end - group_start
                for s in group:
                    s.frame_start += offset
            prev_end = max(s.frame_final_end for s in group)
        count = sum(len(g) for g in groups)
        self.report({'INFO'}, f"已正向堆叠 {count} 个片段（{len(groups)} 组）")
        return {'FINISHED'}


class BetterExperie_OT_StackStripsReverse(bpy.types.Operator):
    bl_idname = "better_experie.stack_strips_reverse"
    bl_label = "反向堆叠"
    bl_description = "将选中片段按同源分组后尾对头反向堆叠，同组内保持相对位置不变"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        sed = getattr(context.scene, "sequence_editor", None)
        return sed and sum(1 for s in sed.strips if s.select) >= 2

    def execute(self, context):
        groups = get_selected_strip_groups(context)
        if len(groups) < 2:
            self.report({'WARNING'}, "请至少选中 2 组片段")
            return {'CANCELLED'}
        groups.reverse()
        prev_start = None
        for group in groups:
            if prev_start is not None:
                group_end = max(s.frame_final_end for s in group)
                offset = prev_start - group_end
                for s in group:
                    s.frame_start += offset
            prev_start = min(s.frame_start for s in group)
        count = sum(len(g) for g in groups)
        self.report({'INFO'}, f"已反向堆叠 {count} 个片段（{len(groups)} 组）")
        return {'FINISHED'}


classes = (
    BetterExperie_OT_StackStripsForward,
    BetterExperie_OT_StackStripsReverse,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
