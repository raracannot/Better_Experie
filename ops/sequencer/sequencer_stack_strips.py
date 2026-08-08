# 片段堆叠（带偏移弹窗）

import bpy
from ...utils.strips_utils import get_selected_strip_groups


class BetterExperie_OT_StackStrips(bpy.types.Operator):
    bl_idname = "better_experie.stack_strips"
    bl_label = "堆叠片段（偏移）"
    bl_description = "将选中的VSE片段按同源分组后堆叠排列，可设置重叠/间隔帧数"
    bl_options = {'REGISTER', 'UNDO'}

    overlap: bpy.props.IntProperty(
        name="堆叠偏移",
        description="下一组开头相对于上一组结尾的偏移帧数（负值=重叠，0=首尾相连，正值=间隔）",
        default=0,
        soft_min=-120000,
        soft_max=120000,
    )

    @classmethod
    def poll(cls, context):
        sed = getattr(context.scene, "sequence_editor", None)
        if not sed:
            return False
        return sum(1 for s in sed.strips if s.select) >= 2

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=300)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "overlap")
        groups = get_selected_strip_groups(context)
        strip_count = sum(len(g) for g in groups)
        layout.label(text=f"选中 {strip_count} 个片段（{len(groups)} 组）")

    def execute(self, context):
        groups = get_selected_strip_groups(context)

        if len(groups) < 2:
            self.report({'WARNING'}, "请至少选中 2 组片段")
            return {'CANCELLED'}

        prev_end = None
        for group in groups:
            if prev_end is not None:
                group_start = min(s.frame_start for s in group)
                offset = prev_end + self.overlap - group_start
                for s in group:
                    s.frame_start += offset
            prev_end = max(s.frame_final_end for s in group)

        count = sum(len(g) for g in groups)
        self.report({'INFO'}, f"已堆叠 {count} 个片段（{len(groups)} 组）")
        return {'FINISHED'}


classes = (
    BetterExperie_OT_StackStrips,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

