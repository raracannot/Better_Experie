# 基于属性域直写，重置选中面法线为局部计算值，避开锐边标记冲突

import bpy
import bmesh
import array


class BetterExperie_OT_ResetLocalNormals(bpy.types.Operator):
    bl_idname = "better_experie.reset_local_normals"
    bl_label = "重算矢量"
    bl_description = "重新计算选中项的矢量，可处理非流形面导致的矢量阴影"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return (
            context.active_object is not None
            and context.active_object.type == 'MESH'
            and context.mode == 'EDIT_MESH'
        )

    def execute(self, context):
        obj = context.active_object
        me = obj.data

        bm = bmesh.from_edit_mesh(me)
        bm.faces.ensure_lookup_table()

        selected_faces = [f for f in bm.faces if f.select]
        if not selected_faces:
            self.report({'WARNING'}, "未选中任何面")
            return {'CANCELLED'}

        loop_map = []

        temp_me = bpy.data.meshes.new("temp_normals")
        bm_new = bmesh.new()
        v_map = {}

        for f in selected_faces:
            new_verts = []
            for v in f.verts:
                if v not in v_map:
                    v_map[v] = bm_new.verts.new(v.co)
                new_verts.append(v_map[v])

            new_f = bm_new.faces.new(new_verts)
            new_f.smooth = f.smooth

            for l in f.loops:
                loop_map.append(l.index)

        bm_new.to_mesh(temp_me)
        bm_new.free()
        temp_me.update()

        bpy.ops.object.mode_set(mode='OBJECT')

        all_normals = array.array('f', [0.0] * (len(me.loops) * 3))
        me.loops.foreach_get("normal", all_normals)

        for i, temp_loop in enumerate(temp_me.loops):
            orig_idx = loop_map[i]
            all_normals[orig_idx * 3]     = temp_loop.normal[0]
            all_normals[orig_idx * 3 + 1] = temp_loop.normal[1]
            all_normals[orig_idx * 3 + 2] = temp_loop.normal[2]

        attr_name = "custom_normal"
        if attr_name in me.attributes:
            me.attributes.remove(me.attributes[attr_name])

        custom_n_attr = me.attributes.new(name=attr_name, type='FLOAT_VECTOR', domain='CORNER')
        custom_n_attr.data.foreach_set("vector", all_normals)

        bpy.data.meshes.remove(temp_me)
        bpy.ops.object.mode_set(mode='EDIT')

        self.report({'INFO'}, "法线已通过属性域重置 (已避开锐边标记)")
        return {'FINISHED'}



classes = (
    BetterExperie_OT_ResetLocalNormals,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
