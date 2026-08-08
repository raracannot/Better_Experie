# 压实轨道

import bpy


class BetterExperie_OT_CompactChannels(bpy.types.Operator):
    bl_idname = "better_experie.compact_channels"
    bl_label = "压实轨道"
    bl_description = "将所有片段向下移动到连续轨道，消除轨道之间的空隙"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        sed = getattr(context.scene, "sequence_editor", None)
        return sed is not None and len(sed.strips) > 0

    def execute(self, context):
        sed = context.scene.sequence_editor
        if not sed.strips:
            self.report({'WARNING'}, "没有可压实的片段")
            return {'CANCELLED'}

        strips_info = [(s, s.frame_start, s.channel) for s in sed.strips]
        used_channels = sorted({ch for _, _, ch in strips_info})
        mapping = {old: new for new, old in enumerate(used_channels, start=1)}

        max_frame = max(s.frame_final_end for s in sed.strips)
        safe_time = max_frame + 10000

        for i, (s, _, _) in enumerate(strips_info):
            s.frame_start = safe_time + i * 1000
            s.channel = i

        for s, _, orig_ch in strips_info:
            new_ch = mapping.get(orig_ch)
            if new_ch is not None:
                s.channel = new_ch

        for s, orig_start, _ in strips_info:
            s.frame_start = orig_start

        self.report({'INFO'}, f"已压实 {len(used_channels)} 个轨道，无空隙")
        return {'FINISHED'}


classes = (
    BetterExperie_OT_CompactChannels,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
