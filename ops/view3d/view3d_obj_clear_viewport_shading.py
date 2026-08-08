# 清理视图着色

import bpy


class BetterExperie_OT_ClearViewportShading(bpy.types.Operator):
    bl_idname = "better_experie.clear_viewport_shading"
    bl_label = "清理视图着色"
    bl_description = "还原选中物体上的材质，在实体模式下的着色为默认色"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return bool(context.selected_objects)

    def execute(self, context):
        removed_count = 0
        for obj in context.selected_objects:
            obj.color = [0.8, 0.8, 0.8, 1.0]
            for slot in obj.material_slots:
                if slot.material:
                    slot.material.diffuse_color = [0.8, 0.8, 0.8, 1.0]
                    slot.material.metallic = 0
                    slot.material.roughness = 0.4
                    removed_count += 1
        self.report({'INFO'}, f"去除了 {removed_count} 个物体的着色")
        return {'FINISHED'}



classes = (
    BetterExperie_OT_ClearViewportShading,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
