# 片段位置轮换

import bpy
from ...utils.strips_utils import get_selected_strip_groups


class BetterExperie_OT_RotateStripPositions(bpy.types.Operator):
    bl_idname = "better_experie.rotate_strip_positions"
    bl_label = "交换位置"
    bl_description = "将选中片段的组位置和轨道循环轮换，每个组移到下一组的位置和轨道"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        sed = getattr(context.scene, "sequence_editor", None)
        if not sed:
            return False
        return len(get_selected_strip_groups(context)) >= 2

    def execute(self, context):
        groups = get_selected_strip_groups(context)
        if len(groups) < 2:
            self.report({'WARNING'}, "请至少选中 2 组片段")
            return {'CANCELLED'}

        sed = context.scene.sequence_editor
        n = len(groups)
        starts = [min(s.frame_start for s in g) for g in groups]
        anchors = [min(s.channel for s in g) for g in groups]

        targets = {}
        for i, group in enumerate(groups):
            t_off = starts[(i + 1) % n] - starts[i]
            c_off = anchors[(i + 1) % n] - anchors[i]
            for s in group:
                targets[s] = (s.frame_start + t_off, s.channel + c_off)

        max_frame = max(max(s.frame_final_end for s in sed.strips), 0)
        safe_time = max_frame + 10000

        all_used = {s.channel for s in sed.strips}
        safe_ch = 1
        while safe_ch in all_used:
            safe_ch += 1

        all_strips = [s for g in groups for s in g]
        for i, s in enumerate(all_strips):
            s.frame_start = safe_time + i
            s.channel = safe_ch + i

        for s, (t_start, t_ch) in targets.items():
            s.frame_start = t_start
            s.channel = t_ch

        count = len(all_strips)
        self.report({'INFO'}, f"已轮换 {count} 个片段（{n} 组）")
        return {'FINISHED'}


classes = (
    BetterExperie_OT_RotateStripPositions,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
