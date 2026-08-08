# 使用 KDTree 加速将选中顶点焊接到最近的边上

import bpy
import bmesh
import mathutils


def closest_point_on_segment(p, a, b):
    ap = p - a
    ab = b - a
    ab_dot_ab = ab.dot(ab)
    if ab_dot_ab == 0:
        return a
    t = ap.dot(ab) / ab_dot_ab
    t = max(0.0, min(1.0, t))
    return a + t * ab


class BetterExperie_OT_WeldVertsToEdges(bpy.types.Operator):
    bl_idname = "better_experie.weld_verts_to_edges"
    bl_label = "焊接顶点到边"
    bl_description = "将选中的顶点尝试焊接到周围的边上"
    bl_options = {'REGISTER', 'UNDO'}

    threshold: bpy.props.FloatProperty(
        name="焊接阈值",
        default=1e-5,
        min=0.0,
        description="顶点与边的距离小于此阈值时进行焊接"
    )

    @classmethod
    def poll(cls, context):
        return context.active_object and context.mode == 'EDIT_MESH'

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        obj = context.active_object
        bm = bmesh.from_edit_mesh(obj.data)
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()

        selected_verts = [v for v in bm.verts if v.select and not v.hide]
        if not selected_verts:
            return {'CANCELLED'}

        welded_vert_count = 0
        processed_verts = set()

        for v in selected_verts:
            if not v.is_valid or v in processed_verts:
                continue

            valid_edges = [e for e in bm.edges if v not in e.verts and not e.hide]
            if not valid_edges:
                continue

            size = len(valid_edges)
            kd = mathutils.kdtree.KDTree(size)
            for i, e in enumerate(valid_edges):
                midpoint = (e.verts[0].co + e.verts[1].co) / 2.0
                kd.insert(midpoint, i)
            kd.balance()

            search_radius = self.threshold + max((e.calc_length() for e in valid_edges))
            candidates = kd.find_range(v.co, search_radius)

            closest_edge = None
            min_distance = float('inf')
            closest_point = None

            for (co, index, dist) in candidates:
                e = valid_edges[index]
                v1_co = e.verts[0].co
                v2_co = e.verts[1].co
                proj = closest_point_on_segment(v.co, v1_co, v2_co)
                distance = (v.co - proj).length

                if distance < min_distance:
                    min_distance = distance
                    closest_edge = e
                    closest_point = proj

            if closest_edge and min_distance < self.threshold:
                v1 = closest_edge.verts[0]
                v2 = closest_edge.verts[1]
                vec = v2.co - v1.co
                length = vec.length

                if length == 0:
                    continue

                t = (closest_point - v1.co).dot(vec.normalized()) / length
                t = max(0.0, min(1.0, t))

                split_result = bmesh.utils.edge_split(closest_edge, v1, t)
                new_vert = split_result[1]
                new_vert.co = closest_point

                if v.is_valid and new_vert.is_valid:
                    bmesh.ops.pointmerge(bm, verts=[v, new_vert], merge_co=new_vert.co)
                    processed_verts.add(v)
                    processed_verts.add(new_vert)
                    welded_vert_count += 1

                    bm.verts.ensure_lookup_table()
                    bm.edges.ensure_lookup_table()

        bmesh.update_edit_mesh(obj.data)
        self.report({'INFO'}, f'已成功焊接 {welded_vert_count} 个顶点')
        return {'FINISHED'}



classes = (
    BetterExperie_OT_WeldVertsToEdges,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
