# 交点打断：检测选中边与网格其他边的交点，在交点处打断边
# 优化：numpy 向量化求交、KDTree 坐标匹配避免引用失效、remove_doubles 融并

import bpy
import bmesh
import numpy as np
import traceback
from mathutils.kdtree import KDTree


def _find_intersections_np(sel_edges, all_edges, eps):
    """numpy 向量化求交：返回 {选中边索引: [(t, 交点坐标), ...]}
    选中边 x 全部边的交点检测"""
    sel_data = np.array([[(e1[1].x, e1[1].y, e1[1].z), (e1[2].x, e1[2].y, e1[2].z)] for e1 in sel_edges], dtype=np.float64)
    all_data = np.array([[(e2[1].x, e2[1].y, e2[1].z), (e2[2].x, e2[2].y, e2[2].z)] for e2 in all_edges], dtype=np.float64)

    p1 = sel_data[:, 0]  # (N,3)
    p2 = sel_data[:, 1]
    q1 = all_data[:, 0]  # (M,3)
    q2 = all_data[:, 1]

    d1 = p2 - p1        # (N,3)
    d2 = q2 - q1        # (M,3)

    # 向量化最近点算法：对每对 (i,j) 计算
    # 用广播计算所有组合，但 N x M 可能很大。逐条选中边循环，内部向量化全部边
    results = {}
    for i in range(len(sel_edges)):
        d1i = d1[i]
        a = np.dot(d1i, d1i)
        if a <= 1e-12:
            continue
        p1i = p1[i]
        r = p1i - q1       # (M,3)
        c = r @ d1i         # (M,) 每个 q 的 c
        f = np.einsum('ij,ij->i', d2, r)  # (M,)
        a_vec = np.full(len(all_edges), a)
        e_vec = np.einsum('ij,ij->i', d2, d2)  # (M,)
        b_vec = d2 @ d1i     # (M,)
        denom = a_vec * e_vec - b_vec * b_vec
        valid = np.abs(denom) > 1e-12
        if not np.any(valid):
            continue
        with np.errstate(divide='ignore', invalid='ignore'):
            s = (b_vec * f - c * e_vec) / denom
            t = (b_vec * s + f) / e_vec
        s = np.clip(s, 0.0, 1.0)
        t = np.clip(t, 0.0, 1.0)
        # 最近点
        closest1 = p1i[None, :] + s[:, None] * d1i[None, :]
        closest2 = q1 + t[:, None] * d2
        dist = np.linalg.norm(closest1 - closest2, axis=1)
        hit = (dist < eps) & valid

        for j in np.nonzero(hit)[0]:
            # 排除端点相交
            if s[j] < 1e-6 or s[j] > 1 - 1e-6:
                continue
            if t[j] < 1e-6 or t[j] > 1 - 1e-6:
                continue
            pt = (closest1[j] + closest2[j]) / 2
            results.setdefault(sel_edges[i][0], []).append((s[j], pt.copy()))

    return results


class BetterExperie_OT_IntersectEdges(bpy.types.Operator):
    bl_idname = "better_experie.intersect_edges"
    bl_label = "交点打断"
    bl_description = "检测选中边与网格其他边的交点，在交点处打断（选中边）"
    bl_options = {'REGISTER', 'UNDO'}

    distance: bpy.props.FloatProperty(
        name="交点容差", description="两条边最近距离小于此值即视为相交打断",
        default=0.001, min=0.0, precision=5)
    merge_intersections: bpy.props.BoolProperty(
        name="交点融并", description="相交的两条边都在交点处打断，并融并为同一个顶点",
        default=False)

    @classmethod
    def poll(cls, context):
        return (
            context.active_object is not None
            and context.active_object.type == 'MESH'
            and context.mode == 'EDIT_MESH'
            and context.tool_settings.mesh_select_mode[1]
        )

    def draw(self, context):
        layout = self.layout
        col = layout.column(align=True)
        col.prop(self, "distance")
        col.prop(self, "merge_intersections")

    def _collect_edges(self, bm, selected_only):
        edges_data = []
        for e in bm.edges:
            if e.hide:
                continue
            if selected_only and not e.select:
                continue
            v1 = e.verts[0]
            v2 = e.verts[1]
            edges_data.append((e, v1.co.copy(), v2.co.copy()))
        return edges_data

    def execute(self, context):
        obj = context.edit_object
        bm = bmesh.from_edit_mesh(obj.data)
        bm.edges.ensure_lookup_table()
        bm.verts.ensure_lookup_table()

        selected_edges = [e for e in bm.edges if e.select and not e.hide]
        if not selected_edges:
            self.report({'WARNING'}, "请先选择至少一条边")
            return {'CANCELLED'}

        all_edges = self._collect_edges(bm, selected_only=False)
        sel_edges = self._collect_edges(bm, selected_only=True)

        # numpy 向量化求交
        split_points = _find_intersections_np(sel_edges, all_edges, self.distance)

        if not split_points:
            self.report({'INFO'}, "未检测到有效交点")
            return {'FINISHED'}

        # 融并模式下，也要收集"相交的另一条边"的割点
        if self.merge_intersections:
            merge_points = _find_intersections_np(all_edges, sel_edges, self.distance)
            # 合并两边割点（用边对象 key）
            for e, pts in merge_points.items():
                if e not in split_points:
                    split_points[e] = pts
                else:
                    split_points[e].extend(pts)

        # 打断：对每条边，用坐标匹配 subdivide 产生的等分顶点
        total_cuts = 0

        # 预计算所有目标割点坐标，避免循环内引用失效
        for edge, pts in list(split_points.items()):
            pts.sort(key=lambda x: x[0])
            unique_pts = []
            last_t = -1
            for t, p in pts:
                if t - last_t > 1e-6:
                    unique_pts.append((t, p))
                    last_t = t
            if not unique_pts:
                continue

            try:
                v1 = edge.verts[0]
                v2 = edge.verts[1]
                # 预先复制端点坐标，subdivide 后引用可能失效，快照保证后续计算安全
                v1_co = v1.co.copy()
                v2_co = v2.co.copy()
            except ReferenceError:
                continue

            cuts = len(unique_pts)
            try:
                res = bmesh.ops.subdivide_edges(bm, edges=[edge], cuts=cuts)
            except Exception:
                continue

            inner = res.get("geom_inner", [])
            inner_verts = [x for x in inner if isinstance(x, bmesh.types.BMVert)]
            if len(inner_verts) != cuts:
                continue

            # 计算各割点世界坐标（用快照坐标，不依赖 bmesh 引用）
            target_coords = [v1_co.lerp(v2_co, t) for t, p in unique_pts]

            # 用坐标排序等分顶点（到 v1 快照的距离单调递增）
            try:
                inner_verts.sort(key=lambda v: (v.co - v1_co).length)
            except ReferenceError:
                continue

            # 移动等分顶点到割点坐标
            for i, target_co in enumerate(target_coords):
                if i >= len(inner_verts):
                    break
                inner_verts[i].co = target_co
                total_cuts += 1

        # 仅融并模式做顶点去重（消除相交两边的交点顶点重复）
        if self.merge_intersections:
            bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=self.distance)

        bmesh.update_edit_mesh(obj.data)
        self.report({'INFO'}, f"交点打断完成：{total_cuts} 处")
        return {'FINISHED'}


classes = (
    BetterExperie_OT_IntersectEdges,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
