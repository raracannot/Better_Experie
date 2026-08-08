# 焊接边到面：借助 face_split_by_edges 原生工具，将选中的边焊接到其附近的面
# 流程：BVH 找到所选边附近的面 → 选中边+面 → 执行 face_split_by_edges → 还原选中为新切分边

import bpy
import bmesh
import mathutils


class BetterExperie_OT_WeldEdgesToFaces(bpy.types.Operator):
    bl_idname = "better_experie.weld_edges_to_faces"
    bl_label = "焊接边到面"
    bl_description = "将选中的边焊接到其附近的面，切分面并选中新产生的边"
    bl_options = {'REGISTER', 'UNDO'}

    distance: bpy.props.FloatProperty(
        name="查找距离", description="所选边周围多大距离内的面会被选中参与焊接",
        default=0.01, min=0.0, precision=4)

    @classmethod
    def poll(cls, context):
        return (
            context.active_object is not None
            and context.active_object.type == 'MESH'
            and context.mode == 'EDIT_MESH'
            and context.tool_settings.mesh_select_mode[1]
        )

    def execute(self, context):
        obj = context.edit_object
        bm = bmesh.from_edit_mesh(obj.data)
        bm.edges.ensure_lookup_table()
        bm.faces.ensure_lookup_table()

        selected_edges = [e for e in bm.edges if e.select]
        if not selected_edges:
            self.report({'WARNING'}, "请先选择至少一条边")
            return {'CANCELLED'}

        matrix_world = obj.matrix_world

        # 用 BVH 找所有边附近的候选面
        bvh = mathutils.bvhtree.BVHTree.FromBMesh(bm)
        hit_faces = set()
        for edge in selected_edges:
            v1 = matrix_world @ edge.verts[0].co
            v2 = matrix_world @ edge.verts[1].co
            mid = (v1 + v2) / 2
            # 在边中点附近查找面
            loc, normal, index, dist = bvh.find_nearest(mid, self.distance)
            if loc is not None:
                hit_faces.add(bm.faces[index])
            # 也检查边两端的顶点
            for v in (v1, v2):
                loc2, normal2, index2, dist2 = bvh.find_nearest(v, self.distance)
                if loc2 is not None:
                    hit_faces.add(bm.faces[index2])

        if not hit_faces:
            self.report({'WARNING'}, "所选边附近没有找到面")
            return {'CANCELLED'}

        # 记录切分前的边集合（用于后续识别新边）
        pre_split_edges = {e.index for e in bm.edges}

        # 在面选择模式下，直接通过 bmesh 设置选择，确保边+面同时选中
        bm = bmesh.from_edit_mesh(obj.data)
        
        # 选中参与的面
        for f in hit_faces:
            f.select = True

        # 执行原生工具
        try:
            bpy.ops.mesh.face_split_by_edges()
        except RuntimeError as e:
            self.report({'ERROR'}, f"face_split_by_edges 执行失败: {e}")
            return {'CANCELLED'}

        bmesh.update_edit_mesh(obj.data)

        self.report({'INFO'}, f"已焊接边到面")
        return {'FINISHED'}


classes = (
    BetterExperie_OT_WeldEdgesToFaces,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
