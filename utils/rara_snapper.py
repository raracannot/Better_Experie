# V0.0.2 (2026/05/28)
# 本工具用于快速获取场景中距离鼠标最近的顶点，可协助实现各类高性能顶点吸附UI
# 内已支持、无顶点物体、网格顶点、曲线点等的高性能吸附
# 工作流程：
    # 精细吸附：
        # 先build_cache，获取所有无法被ray_cast的顶点（游离边、悬浮点）
        # 后find_nearest，借助ray_cast和缓存，快速获取最近点
    # 快速吸附：
        # 直接find_nearest，借助ray_cast快速获取最近点

# 感谢CYX，与RARA一同构建本工具
# CYX：https://space.bilibili.com/289597239
# RARA：https://space.bilibili.com/27284213

# 本工具为【超级技术交流社】内共享模块
# 欢迎您复用本工具优化你的插件，如有建议，请务必反馈

import numpy as np
import mathutils
from mathutils import Vector
from bpy_extras import view3d_utils


# ── Curve 辅助：将曲线物体转成世界空间线段列表 ──
def _curve_segments_world(obj, depsgraph, max_seg=20000):
    segments = []
    if not obj or obj.type != 'CURVE':
        return segments
    try:
        ev = obj.evaluated_get(depsgraph)
        mesh = ev.to_mesh()
        if mesh:
            mat = ev.matrix_world
            vw = [mat @ v.co for v in mesh.vertices]
            for e in mesh.edges:
                if len(segments) >= max_seg:
                    break
                a, b = e.vertices[0], e.vertices[1]
                if a < len(vw) and b < len(vw) and (vw[b] - vw[a]).length > 1e-9:
                    segments.append((vw[a], vw[b]))
            ev.to_mesh_clear()
    except Exception:
        pass
    if not segments:
        try:
            mat = obj.matrix_world
            for spl in obj.data.splines:
                pts = [mat @ (bp.co if spl.type == 'BEZIER' else _cv_pt(p)) for bp, p in
                       zip(spl.bezier_points if spl.type == 'BEZIER' else spl.points,
                           spl.points if spl.type != 'BEZIER' else [None] * len(spl.points))]
                # fallback: iterate properly
                if spl.type == 'BEZIER':
                    pts = [mat @ bp.co for bp in spl.bezier_points]
                else:
                    pts = [mat @ Vector((p.co[0], p.co[1], p.co[2])) for p in spl.points]
                for i in range(len(pts) - 1):
                    if len(segments) >= max_seg:
                        break
                    if (pts[i + 1] - pts[i]).length > 1e-9:
                        segments.append((pts[i], pts[i + 1]))
                if getattr(spl, "use_cyclic_u", False) and len(pts) > 2:
                    if (pts[0] - pts[-1]).length > 1e-9:
                        segments.append((pts[-1], pts[0]))
        except Exception:
            pass
    return segments


def _cv_pt(point):
    try:
        return Vector((point.co[0], point.co[1], point.co[2]))
    except Exception:
        return Vector((0, 0, 0))


class RaraSnapper:
    """统一吸附器。双路径并行(NP缓存投影 + 射线面枚举)，取屏幕最近。

    build_cache
      - 选中/活动物体：全部顶点 + 全部边中点 + 全部边三分点
      - 非选中物体：浮点 + 松散边中点 + 松散边三分点
      - 非网格：原点 → 归入基础点

    find_nearest
      - Ray路径：射线击中面 → 收集面上顶点/中点/三分点/面心 → 取屏幕最近
                 无候选在半径内 → 回退到击中点
      - NP路径：三份缓存各自投影 → 非穿透时逐点校验遮挡 → 取屏幕最近
      - 双路比较 → 返回最近
    """

    def __init__(self):
        self._cached_verts = None
        self._cached_halves = None
        self._cached_thirds = None
        self._cached_objects = set()

    # ══════════════════════════════════════════
    # 缓存构建
    # ══════════════════════════════════════════
    def build_cache(self, context, scope='SELECTED', include_non_mesh=True):
        """
        构建三份独立缓存，供 NP 路径投影使用。不缓存时 Ray 路径仍可独立工作。

        context : bpy.types.Context
            当前上下文。从 context.visible_objects 遍历物体，
            从 context.active_object 判断活动物体。

        scope : str, 可选 'SELECTED' | 'ACTIVE' | 'ALL', 默认 'SELECTED'
            - 'SELECTED' : 仅缓存当前选中物体
            - 'ACTIVE'   : 仅缓存 context.active_object
            - 'ALL'      : 缓存所有 visible_objects

        include_non_mesh : bool, 默认 True
            是否将非网格物体（灯光/相机/空物体）的原点纳入 _cached_verts。

        缓存内容：
            - 选中/活动·网格物体：全部顶点 + 全部边中点 + 全部边三分点
            - 未选中·网格物体 ：浮点(无面引用的顶点) + 松散边中点 + 松散边三分点
            - 非网格物体       ：原点 → _cached_verts

        缓存字段：
            self._cached_verts  : (N,3) float32 世界坐标 — 顶点/原点
            self._cached_halves : (M,3) float32 世界坐标 — 边中点
            self._cached_thirds : (K,3) float32 世界坐标 — 边 1/3 和 2/3 点
            self._cached_objects: set[str] — 已缓存物体名称，Ray路径穿透时排除
        """
        self._cached_objects.clear()
        vt, hf, th = [], [], []

        for obj in context.visible_objects:
            should_cache = (
                scope == 'ALL' or
                (scope == 'ACTIVE' and obj == context.active_object) or
                (scope == 'SELECTED' and obj.select_get())
            )
            if not should_cache:
                continue

            # ── 曲线 → 采样线段上的点入缓存 ──
            if obj.type == 'CURVE':
                self._cached_objects.add(obj.name)
                segs = _curve_segments_world(obj, context.evaluated_depsgraph_get())
                for v1, v2 in segs:
                    vt.append(np.array(v1, dtype=np.float32))
                    vt.append(np.array(v2, dtype=np.float32))
                    hf.append(np.array((v1 + v2) * 0.5, dtype=np.float32))
                    th.append(np.array(v1 + (v2 - v1) * (1.0 / 3.0), dtype=np.float32))
                    th.append(np.array(v1 + (v2 - v1) * (2.0 / 3.0), dtype=np.float32))
                continue

            # ── 非网格 ──
            if obj.type != 'MESH':
                if include_non_mesh:
                    self._cached_objects.add(obj.name)
                    vt.append(np.array(obj.matrix_world.translation, dtype=np.float32))
                continue

            # ── 网格 ──
            if obj.mode == 'EDIT':
                obj.update_from_editmode()
            mesh = obj.data
            nv, ne = len(mesh.vertices), len(mesh.edges)
            if nv == 0:
                continue

            verts = np.zeros(nv * 3, dtype=np.float32)
            mesh.vertices.foreach_get("co", verts)
            verts = verts.reshape((nv, 3))
            wm = np.array(obj.matrix_world, dtype=np.float32)

            self._cached_objects.add(obj.name)

            # 选中/活跃 → 全量；未选中 → 浮点+松散边
            if obj.select_get() or obj == context.active_object:
                # 全部顶点
                c4 = np.empty((nv, 4), dtype=np.float32)
                c4[:, :3] = verts
                c4[:, 3] = 1.0
                vt.append((c4 @ wm.T)[:, :3])

                # 全部边的中点/三分点
                if ne > 0:
                    edges = np.zeros(ne * 2, dtype=np.int32)
                    mesh.edges.foreach_get("vertices", edges)
                    edges = edges.reshape((ne, 2))
                    world_v = (c4 @ wm.T)[:, :3]
                    v0 = world_v[edges[:, 0]]
                    v1 = world_v[edges[:, 1]]
                    hf.append((v0 + v1) * 0.5)
                    th.append(v0 + (v1 - v0) * (1.0 / 3.0))
                    th.append(v0 + (v1 - v0) * (2.0 / 3.0))
            else:
                # 未选中物体：浮点 + 松散边
                self._add_floating_and_loose(verts, wm, mesh, vt, hf, th)

        self._cached_verts = np.vstack(vt).reshape(-1, 3) if vt else None
        self._cached_halves = np.vstack(hf).reshape(-1, 3) if hf else None
        self._cached_thirds = np.vstack(th).reshape(-1, 3) if th else None

    def _add_floating_and_loose(self, verts, wm, mesh, vt, hf, th):
        nv = len(verts)
        nloops = len(mesh.loops)
        if nloops > 0:
            lv = np.zeros(nloops, dtype=np.int32)
            mesh.loops.foreach_get("vertex_index", lv)
            linked = np.unique(lv)
            floating_mask = np.ones(nv, dtype=bool)
            floating_mask[linked] = False
            fl = verts[floating_mask]
        else:
            fl = verts

        # 浮点 → world
        if len(fl) > 0:
            c4 = np.empty((len(fl), 4), dtype=np.float32)
            c4[:, :3] = fl
            c4[:, 3] = 1.0
            vt.append((c4 @ wm.T)[:, :3])

        # 松散边中点/三分点
        ne = len(mesh.edges)
        if ne > 0:
            is_loose = np.zeros(ne, dtype=bool)
            mesh.edges.foreach_get("is_loose", is_loose)
            if np.any(is_loose):
                edges = np.zeros(ne * 2, dtype=np.int32)
                mesh.edges.foreach_get("vertices", edges)
                edges = edges.reshape((ne, 2))[is_loose]
                c4 = np.empty((nv, 4), dtype=np.float32)
                c4[:, :3] = verts
                c4[:, 3] = 1.0
                world_v = (c4 @ wm.T)[:, :3]
                v0 = world_v[edges[:, 0]]
                v1 = world_v[edges[:, 1]]
                hf.append((v0 + v1) * 0.5)
                th.append(v0 + (v1 - v0) * (1.0 / 3.0))
                th.append(v0 + (v1 - v0) * (2.0 / 3.0))

    def clear_cache(self):
        self._cached_verts = None
        self._cached_halves = None
        self._cached_thirds = None

    @property
    def has_cache(self):
        return self._cached_verts is not None

    # ══════════════════════════════════════════
    # find_nearest
    # ══════════════════════════════════════════
    def find_nearest(self, context, event,
                     radius=30, snap_vertex=True, snap_half=True,
                     snap_third=True, snap_edge=True, snap_face=True,
                     penetrate=False):
        """
        双路径并行查找屏幕最近吸附点。NP路径（有缓存时）和Ray路径同时运行，取更近者。

        context : bpy.types.Context
            当前上下文，必须包含 region / region_data。

        event : bpy.types.Event
            鼠标事件，从中取 mouse_region_x / mouse_region_y。

        radius : float, 默认 30
            屏幕像素吸附半径。候选点距鼠标超过此值将被忽略。

        snap_vertex : bool, 默认 True
            是否吸附顶点。NP搜索 _cached_verts，Ray枚举命中面顶点。

        snap_half : bool, 默认 True
            是否吸附边中点。NP搜索 _cached_halves，Ray枚举命中面边中点。

        snap_third : bool, 默认 True
            是否吸附边三等分点（1/3 和 2/3）。NP搜索 _cached_thirds，Ray枚举命中面。

        snap_edge : bool, 默认 True
            是否吸附边线上任意点（鼠标射线到边的垂足，限Ray路径）。

        snap_face : bool, 默认 True
            是否吸附面心（面顶点平均值）。仅 Ray 路径提供。

        penetrate : bool, 默认 False
            - False : NP逐点校验遮挡(最多检查前20个候选)；Ray停在第一个命中面
            - True  : 穿透模式，NP不做遮挡校验直接取最近；Ray穿透缓存物体向后找

        返回: (mathutils.Vector, type_tag) 或 (None, 'NONE')
            type_tag: 'VERT' | 'HALF' | 'THIRD' | 'EDGE' | 'FACE' | 'NONE'
        """
        mx, my = event.mouse_region_x, event.mouse_region_y
        region, rv3d = context.region, context.region_data
        mouse = Vector((mx, my))

        np_pt = None
        np_type = None
        ray_pt = None
        ray_type = None
        hit_loc = None

        # ── NP 路径 ──
        if self.has_cache:
            np_pt, np_type = self._np_search(
                context, region, rv3d, mx, my, radius,
                snap_vertex, snap_half, snap_third, penetrate)

        # ── Ray 路径 ──
        if snap_vertex or snap_half or snap_third or snap_edge or snap_face:
            ray_pt, ray_type, hit_loc = self._ray_search(
                context, region, rv3d, mx, my, mouse, radius,
                snap_vertex, snap_half, snap_third, snap_edge, snap_face,
                penetrate)

        # 双路都不中 → 击中点兜底
        if np_pt is None and ray_pt is None and hit_loc is not None:
            ray_pt, ray_type = hit_loc, 'FACE'

        if np_pt is None and ray_pt is None:
            return None, 'NONE'

        if np_pt is None:
            return ray_pt, ray_type
        if ray_pt is None:
            return np_pt, np_type
        d_np = self._screen_px(region, rv3d, np_pt, mouse)
        d_ray = self._screen_px(region, rv3d, ray_pt, mouse)
        if d_np is None:
            return ray_pt, ray_type
        if d_ray is None:
            return np_pt, np_type
        if d_np < d_ray:
            return np_pt, np_type
        return ray_pt, ray_type

    # ══════════════════════════════════════════
    # NP 搜索
    # ══════════════════════════════════════════
    def _np_search(self, context, region, rv3d, mx, my, radius,
                   sv, sh, st, penetrate):
        """返回 (世界坐标, 类型标签) 或 (None, None)"""
        sources = []  # [(pts_array, type_tag), ...]
        if sv and self._cached_verts is not None:
            sources.append((self._cached_verts, 'VERT'))
        if sh and self._cached_halves is not None:
            sources.append((self._cached_halves, 'HALF'))
        if st and self._cached_thirds is not None:
            sources.append((self._cached_thirds, 'THIRD'))
        if not sources:
            return None, None

        all_pts = np.vstack([s[0] for s in sources])
        all_tags = np.concatenate([np.full(len(s[0]), s[1]) for s in sources])

        persp = np.array(rv3d.perspective_matrix, dtype=np.float32)
        c4 = np.empty((len(all_pts), 4), dtype=np.float32)
        c4[:, :3] = all_pts
        c4[:, 3] = 1.0
        ndc = c4 @ persp.T
        w = ndc[:, 3]

        valid = w > 0
        if not np.any(valid):
            return None, None

        ndc_v = ndc[valid] / w[valid, np.newaxis]
        sx = (ndc_v[:, 0] + 1.0) * 0.5 * region.width
        sy = (ndc_v[:, 1] + 1.0) * 0.5 * region.height
        d2 = (sx - mx) ** 2 + (sy - my) ** 2
        r2 = radius ** 2

        in_range = d2 <= r2
        if not np.any(in_range):
            return None, None

        valid_indices = np.where(valid)[0]
        in_range_indices = valid_indices[in_range]
        d2_in_range = d2[in_range]
        sort_order = np.argsort(d2_in_range)
        sorted_indices = in_range_indices[sort_order]

        if penetrate:
            idx = sorted_indices[0]
            return Vector(all_pts[idx]), str(all_tags[idx])

        depsgraph = context.evaluated_depsgraph_get()
        camera_origin = view3d_utils.region_2d_to_origin_3d(
            region, rv3d, (mx, my))
        limit = min(20, len(sorted_indices))
        for i in range(limit):
            idx = sorted_indices[i]
            p_world = Vector(all_pts[idx])
            ray_dir = (p_world - camera_origin).normalized()
            hit, hit_loc, _, _, _, _ = context.scene.ray_cast(
                depsgraph, camera_origin, ray_dir)
            if hit:
                hit_dist = (hit_loc - camera_origin).length
                cand_dist = (p_world - camera_origin).length
                if hit_dist < cand_dist - 0.01:
                    continue
            return p_world, str(all_tags[idx])
        return None, None

    # ══════════════════════════════════════════
    # Ray 搜索
    # ══════════════════════════════════════════
    def _ray_search(self, context, region, rv3d, mx, my, mouse, radius,
                    sv, sh, st, se, sf, penetrate):
        """返回 (snap_pt, snap_type, hit_loc)"""
        hit_obj, loc, face_idx, mat = self._hit_face(context, region, rv3d, mx, my, penetrate)
        if not hit_obj:
            return None, None, None

        mesh = self._eval_mesh(context, hit_obj)
        if not mesh or face_idx >= len(mesh.polygons):
            return None, None, loc

        poly = mesh.polygons[face_idx]
        pv = poly.vertices
        n = len(pv)

        if sv:
            pt = self._best_among_verts(mat, mesh, pv, region, rv3d, mouse, radius)
            if pt is not None:
                return pt, 'VERT', loc

        if sh or st:
            best_pt, best_d, best_type = None, float('inf'), None
            for i in range(n):
                v1 = mat @ mesh.vertices[pv[i]].co
                v2 = mat @ mesh.vertices[pv[(i + 1) % n]].co
                if sh:
                    mid = (v1 + v2) * 0.5
                    d = self._screen_px(region, rv3d, mid, mouse)
                    if d is not None and d < best_d and d <= radius:
                        best_d, best_pt, best_type = d, mid, 'HALF'
                if st and best_pt is None:
                    for frac in (1.0 / 3.0, 2.0 / 3.0):
                        pt = v1 + (v2 - v1) * frac
                        d = self._screen_px(region, rv3d, pt, mouse)
                        if d is not None and d < best_d and d <= radius:
                            best_d, best_pt, best_type = d, pt, 'THIRD'
            if best_pt is not None:
                return best_pt, best_type, loc

        if sf:
            fc = sum((mat @ mesh.vertices[idx].co for idx in pv), Vector()) / n
            d = self._screen_px(region, rv3d, fc, mouse)
            if d is not None and d <= radius:
                return fc, 'FACE', loc

        if se:
            best_pt, best_d = None, float('inf')
            for i in range(n):
                v1 = mat @ mesh.vertices[pv[i]].co
                v2 = mat @ mesh.vertices[pv[(i + 1) % n]].co
                ep = self._edge_closest_point(
                    context, region, rv3d, mx, my, v1, v2)
                if ep is not None:
                    d = self._screen_px(region, rv3d, ep, mouse)
                    if d is not None and d < best_d and d <= radius:
                        best_d, best_pt = d, ep
            if best_pt is not None:
                return best_pt, 'EDGE', loc

        return None, None, loc

    @staticmethod
    def _best_among_verts(mat, mesh, pv, region, rv3d, mouse, radius):
        best_pt, best_d = None, float('inf')
        for idx in pv:
            wp = mat @ mesh.vertices[idx].co
            c = view3d_utils.location_3d_to_region_2d(region, rv3d, wp)
            if c is None:
                continue
            d = (c - mouse).length
            if d < best_d and d <= radius:
                best_d = d
                best_pt = wp
        return best_pt

    # ── 边线吸附：3D射线到边线的垂足，仅在线段内部时返回 ──
    @staticmethod
    def _edge_closest_point(context, region, rv3d, mx, my, v1, v2):
        origin = view3d_utils.region_2d_to_origin_3d(region, rv3d, (mx, my))
        direction = view3d_utils.region_2d_to_vector_3d(region, rv3d, (mx, my))
        res = mathutils.geometry.intersect_line_line(
            origin, origin + direction, v1, v2)
        if res is None:
            return None
        p = res[1]  # 边线上的最近点
        edge_vec = v2 - v1
        edge_len = edge_vec.length
        if edge_len < 1e-6:
            return None
        # 投影距离（世界单位），比对 [0, edge_len] 而非 [0,1]
        t = (p - v1).dot(edge_vec) / edge_len
        if 0 < t < edge_len:
            return v1 + edge_vec * (t / edge_len)
        return None

    # ══════════════════════════════════════════
    # 射线命中
    # ══════════════════════════════════════════
    def _hit_face(self, context, region, rv3d, mx, my, penetrate):
        origin = view3d_utils.region_2d_to_origin_3d(region, rv3d, (mx, my))
        direction = view3d_utils.region_2d_to_vector_3d(region, rv3d, (mx, my))
        depsgraph = context.evaluated_depsgraph_get()
        ray_start = origin

        for _ in range(20):
            res = context.scene.ray_cast(depsgraph, ray_start, direction)
            if not res[0]:
                return None, None, -1, None
            _, loc, _, fidx, obj, mat = res
            if penetrate and obj.name in self._cached_objects:
                ray_start = loc + direction * 0.001
                continue
            return obj, loc, fidx, mat
        return None, None, -1, None

    @staticmethod
    def _eval_mesh(context, obj):
        try:
            return obj.evaluated_get(context.evaluated_depsgraph_get()).to_mesh()
        except Exception:
            return None

    @staticmethod
    def _screen_px(region, rv3d, world_pt, mouse):
        c = view3d_utils.location_3d_to_region_2d(region, rv3d, world_pt)
        if c is None:
            return None
        return (c - mouse).length
