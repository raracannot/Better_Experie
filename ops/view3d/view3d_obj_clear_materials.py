# 清理材质

import bpy


def _get_materials_collection(obj):
    if obj.type in {'MESH', 'CURVE', 'SURFACE', 'META', 'FONT', 'GPENCIL'}:
        data = getattr(obj, "data", None)
        if data is not None:
            return getattr(data, "materials", None)
    return None


class BetterExperie_OT_ClearMaterials(bpy.types.Operator):
    bl_idname = "better_experie.clear_materials"
    bl_label = "清理材质"
    bl_description = "清空所选对象的材质槽；Shift+点击时遍历场景所有对象，仅清理空材质槽"
    bl_options = {'REGISTER', 'UNDO'}

    clean_empty_only: bpy.props.BoolProperty(
        default=False,
        description="仅清理空材质槽（Shift+点击开启）",
        options={'HIDDEN'})

    def invoke(self, context, event):
        self.clean_empty_only = event.shift
        return self.execute(context)

    def execute(self, context):
        if self.clean_empty_only:
            removed = 0
            for obj in context.scene.objects:
                mats = _get_materials_collection(obj)
                if mats is None:
                    continue
                for i in range(len(mats) - 1, -1, -1):
                    if mats[i] is None:
                        mats.pop(index=i)
                        removed += 1
            self.report({'INFO'}, f"已清理 {removed} 个空材质槽")
            return {'FINISHED'}

        objs = context.selected_objects
        if not objs:
            self.report({'WARNING'}, "未选中任何对象")
            return {'CANCELLED'}

        cleared = 0
        for obj in objs:
            mats = _get_materials_collection(obj)
            if mats is None:
                continue
            if len(mats) > 0:
                mats.clear()
                cleared += 1
        self.report({'INFO'}, f"已清空 {cleared} 个对象的材质槽")
        return {'FINISHED'}


classes = (
    BetterExperie_OT_ClearMaterials,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
