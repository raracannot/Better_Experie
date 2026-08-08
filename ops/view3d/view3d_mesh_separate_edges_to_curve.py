# 拆分所选边为曲线

import bpy


class BetterExperie_OT_SeparateEdgesToCurve(bpy.types.Operator):
    bl_idname = "better_experie.separate_edges_to_curve"
    bl_label = "拆分所选边为曲线"
    bl_description = "将选中的边线分离为独立对象并转换为曲线"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return (
            context.active_object is not None
            and context.active_object.type == 'MESH'
            and context.mode == 'EDIT_MESH'
        )

    def execute(self, context):
        original_obj = context.active_object

        try:
            bpy.ops.mesh.duplicate()
            bpy.ops.mesh.separate(type='SELECTED')
            bpy.ops.object.mode_set(mode='OBJECT')

            new_obj = None
            for obj in context.selected_objects:
                if obj != original_obj:
                    new_obj = obj
                    break

            if new_obj:
                bpy.ops.object.select_all(action='DESELECT')
                new_obj.select_set(True)
                context.view_layer.objects.active = new_obj
                bpy.ops.object.convert(target='CURVE')
                self.report({'INFO'}, "已分离并转换为曲线")
            else:
                self.report({'WARNING'}, "未找到分离的对象，请确保选中了边线")
                bpy.ops.object.select_all(action='DESELECT')
                original_obj.select_set(True)
                context.view_layer.objects.active = original_obj
                bpy.ops.object.mode_set(mode='EDIT')

        except Exception as e:
            self.report({'ERROR'}, f"发生错误: {str(e)}")
            return {'CANCELLED'}

        return {'FINISHED'}



classes = (
    BetterExperie_OT_SeparateEdgesToCurve,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
