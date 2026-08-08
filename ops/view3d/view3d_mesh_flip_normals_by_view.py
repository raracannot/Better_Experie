# 以视口反转法向

import bpy
import bmesh
import mathutils


class BetterExperie_OT_FlipNormalsByView(bpy.types.Operator):
    bl_idname = "better_experie.flip_normals_by_view"
    bl_label = "以视口设置法向"
    bl_description = "将选中的网格的法向朝向视口方向"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return (
            context.active_object is not None
            and context.active_object.type == 'MESH'
            and context.mode == 'EDIT_MESH'
        )

    def execute(self, context):
        obj = context.edit_object
        me = obj.data
        bm = bmesh.from_edit_mesh(me)

        space = context.space_data
        region_3d = space.region_3d

        if region_3d.is_perspective:
            cam_location = region_3d.view_matrix.inverted().translation
        else:
            cam_location = (
                context.scene.camera.location
                if context.scene.camera
                else mathutils.Vector((0.0, 0.0, 0.0))
            )

        for face in bm.faces:
            if face.select:
                normal_to_cam = (cam_location - face.calc_center_median()).normalized()
                if face.normal.dot(normal_to_cam) < 0:
                    face.normal_flip()

        bmesh.update_edit_mesh(me)
        self.report({'INFO'}, "已按视口方向反转法向")
        return {'FINISHED'}



classes = (
    BetterExperie_OT_FlipNormalsByView,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
