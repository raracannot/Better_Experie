# 保持曲率滑动：T 面板工作区工具（选中边线上叠绘手柄，拖手柄滑移）
#
# 由原「保持曲率滑动」并入，拓扑 / 向心 Catmull-Rom / HUD / 边框绘制均在本文件内。
# 入口只有 3D 视图 T 面板（并入原生 edge_slide 工具组），不再向菜单注入。

import os
import bpy
import bmesh
import blf
import gpu
import math
import mathutils
import traceback
from mathutils import Vector
from gpu_extras.batch import batch_for_shader
from bpy_extras import view3d_utils

TOOL_ID = "better_experie.curv_slide_tool"
HANDLE_RADIUS = 7.0
HANDLE_HIT = 14.0
HANDLE_BAR_WIDTH = 3.0


# ---------------------------------------------------------------- 边链拓扑
def _div_set(selected_edges):
    """Partition selected edges into connected components via flood-fill."""
    eall = set(selected_edges)
    components = []
    while eall:
        e1 = eall.pop()
        component = {e1}
        stack = [e1]
        while stack:
            cur = stack.pop()
            for v in cur.verts:
                for e2 in v.link_edges:
                    if e2 in selected_edges and e2 not in component:
                        component.add(e2)
                        stack.append(e2)
        eall -= component
        components.append(list(component))
    return components


def _get_endpoints(edge_set):
    """Find vertices with exactly 1 selected edge in the given set (open ends)."""
    vs = set()
    for e in edge_set:
        vs.update(e.verts)
    ends = []
    for v in vs:
        count = sum(1 for e in v.link_edges if e in edge_set)
        if count == 1:
            ends.append(v)
    return ends


def _build_edge_chain(edge_set, start_vert):
    """Walk from a start_vert along selected edges to build an ordered chain.
    Returns list of (BMVert, BMEdge) tuples in traversal order, or empty list on failure."""
    if not edge_set:
        return []
    chain = []
    visited = set()
    cur_v = start_vert
    while True:
        unvisited = [e for e in cur_v.link_edges if e in edge_set and e not in visited]
        if not unvisited:
            break
        if len(unvisited) > 1:
            # T 形接点检测：优先选与入射方向最对齐的边
            if chain:
                in_vec = (cur_v.co - chain[-1][0].co).normalized()
                best = max(unvisited, key=lambda e: abs(in_vec.dot(
                    (e.other_vert(cur_v).co - cur_v.co).normalized())))
                e1 = best
            else:
                e1 = unvisited[0]
        else:
            e1 = unvisited[0]
        visited.add(e1)
        next_v = e1.other_vert(cur_v)
        chain.append((cur_v, e1))
        cur_v = next_v
    chain.append((cur_v, None))
    return chain


# ------------------------------------------------------- 向心 Catmull-Rom
def _knot_after(knot, start, end):
    """下一个结点参数：按 ``sqrt(弦长)`` 推进，这就是「向心」的含义。"""
    return knot + max((end - start).length, 1e-12) ** 0.5


def _catmull_rom(p0, p1, p2, p3, t):
    """在 ``p1`` 与 ``p2`` 之间插值，返回一个**新的** Vector。

    ``t=0`` 正好落在 p1、``t=1`` 正好落在 p2。四点中有重合点时不会除零，
    退化为相邻点的线性插值。向心参数化避免短段处回环。
    """
    knot0 = 0.0
    knot1 = _knot_after(knot0, p0, p1)
    knot2 = _knot_after(knot1, p1, p2)
    knot3 = _knot_after(knot2, p2, p3)
    knot = knot1 + max(0.0, min(1.0, t)) * (knot2 - knot1)

    def blend(start, end, start_knot, end_knot):
        span = end_knot - start_knot
        if span <= 1e-12:
            return start.copy()
        return start.copy().lerp(end, (knot - start_knot) / span)

    level1_first = blend(p0, p1, knot0, knot1)
    level1_second = blend(p1, p2, knot1, knot2)
    level1_third = blend(p2, p3, knot2, knot3)

    span = knot2 - knot0
    level2_first = level1_first.copy().lerp(
        level1_second, (knot - knot0) / span if span > 1e-12 else 0.0
    )
    span = knot3 - knot1
    level2_second = level1_second.copy().lerp(
        level1_third, (knot - knot1) / span if span > 1e-12 else 0.0
    )
    span = knot2 - knot1
    return level2_first.lerp(
        level2_second, (knot - knot1) / span if span > 1e-12 else 0.0
    )


# ------------------------------------------------------------ HUD / 边框
def _draw_hud_text(text, context, font_size=20, color=(1, 1, 1, 1)):
    """底部居中 HUD 文本，带阴影，跟随视口刷新，不被其他工具打断"""
    if text is None:
        return
    font_id = 0
    blf.size(font_id, font_size)
    blf.enable(font_id, blf.SHADOW)
    blf.shadow(font_id, 3, 0.0, 0.0, 0.0, 0.8)
    tw, th = blf.dimensions(font_id, text)
    blf.position(font_id, (context.region.width - tw) / 2, 30, 0)
    blf.color(font_id, *color)
    blf.draw(font_id, text)
    blf.disable(font_id, blf.SHADOW)


def _draw_border(self, context):
    try:
        shader = gpu.shader.from_builtin('UNIFORM_COLOR')
        region = context.region
        w, h = region.width, region.height
        m = 2
        coords = [
            (m, m), (w - m, m),
            (w - m, m), (w - m, h - m),
            (w - m, h - m), (m, h - m),
            (m, h - m), (m, m),
        ]
        try:
            gpu.state.line_width_set(10.0)
            gpu.state.blend_set('ALPHA')
            batch = batch_for_shader(shader, 'LINES', {"pos": coords})
            shader.bind()
            shader.uniform_float("color", (1.0, 1.0, 1.0, 1.0))
            batch.draw(shader)
        finally:
            gpu.state.blend_set('NONE')
            gpu.state.line_width_set(1.0)
    except ReferenceError:
        pass
    except Exception:
        traceback.print_exc()


def _add_modal_border(owner, context):
    """注册视口白色边框绘制，返回 handler。"""
    if getattr(owner, "_modal_border_handle", None) is not None:
        _remove_modal_border(owner)
    handle = bpy.types.SpaceView3D.draw_handler_add(
        _draw_border, (owner, context), 'WINDOW', 'POST_PIXEL')
    owner._modal_border_handle = handle
    return handle


def _remove_modal_border(owner):
    """安全移除视口边框 handler"""
    handle = getattr(owner, '_modal_border_handle', None)
    if handle:
        try:
            bpy.types.SpaceView3D.draw_handler_remove(handle, 'WINDOW')
        except Exception:
            pass
        owner._modal_border_handle = None


# ---------------------------------------------------------------- 几何工具
def _get_circle_from_3_points(p1, p2, p3):
    a = p1 - p3
    b = p2 - p3
    cross_ab = a.cross(b)
    scale2 = max(a.length_squared, b.length_squared, 1e-10)
    if cross_ab.length_squared < scale2 * 1e-12:
        return None, None, None
    a_sq = a.length_squared
    b_sq = b.length_squared
    cross_sq = cross_ab.length_squared
    term1 = a_sq * b - b_sq * a
    center = p3 + term1.cross(cross_ab) / (2.0 * cross_sq)
    radius = (p1 - center).length
    normal = cross_ab.normalized()
    return center, radius, normal


def _geometric_rail_verts(chain_verts, all_selected, closed=False):
    """几何定侧 + 沿链平行传递，定出每个顶点的 p1（负侧）与 p3（正侧）。

    锚点上用 ``side_ref = normal × tangent`` 定侧，完全不看拓扑顺序；之后每个顶点
    都拿上一顶点选中的 p3 方向投影到当前切线平面当参考，选与它最连续的那条轨道。
    一侧取不到时另一侧仍返回，调用方按镜像补齐。返回 [(p1_vert, p3_vert), ...]。
    """
    edge_set = set(all_selected)
    count = len(chain_verts)
    result = []
    previous_side = None
    for index, vertex in enumerate(chain_verts):
        if count == 1:
            tangent = Vector((1.0, 0.0, 0.0))
        elif closed:
            tangent = (
                chain_verts[(index + 1) % count].co
                - chain_verts[(index - 1) % count].co
            )
        elif index == 0:
            tangent = chain_verts[1].co - vertex.co
        elif index == count - 1:
            tangent = vertex.co - chain_verts[index - 1].co
        else:
            tangent = chain_verts[index + 1].co - chain_verts[index - 1].co

        if tangent.length < 1e-12:
            result.append((None, None))
            continue
        tangent.normalize()

        normal = vertex.normal.copy()
        if normal.length < 1e-9:
            result.append((None, None))
            continue
        normal.normalize()

        # 参考侧向量：有上一步就沿用它，否则用 normal × tangent 起锚
        side_ref = None
        if previous_side is not None:
            projected = previous_side - tangent * previous_side.dot(tangent)
            if projected.length > 1e-6:
                side_ref = projected.normalized()
        if side_ref is None:
            candidate_ref = normal.cross(tangent)
            if candidate_ref.length < 1e-9:
                result.append((None, None))
                continue
            side_ref = candidate_ref.normalized()

        candidates = []
        for edge in vertex.link_edges:
            if edge in edge_set:
                continue
            delta = edge.other_vert(vertex).co - vertex.co
            perpendicular = delta - tangent * delta.dot(tangent)
            if perpendicular.length <= 1e-9:
                continue
            candidates.append(
                (abs(delta.normalized().dot(tangent)), perpendicular.normalized(), edge)
            )
        # 最垂直于链方向的排在前面（斜着走过去的边不是轨道）
        candidates.sort(key=lambda item: item[0])

        positive = [item for item in candidates if item[1].dot(side_ref) > 0.0]
        negative = [item for item in candidates if item[1].dot(side_ref) <= 0.0]
        if positive:
            previous_side = positive[0][1]
        result.append(
            (
                negative[0][2].other_vert(vertex) if negative else None,
                positive[0][2].other_vert(vertex) if positive else None,
            )
        )
    return result


def _chart_chain_direction(chain_verts, closed):
    """把链的走向定死：从索引较小的一端出发（闭环从最小索引顶点起、朝邻居更小的方向）。"""
    if len(chain_verts) < 3:
        return chain_verts
    if closed:
        start = min(range(len(chain_verts)), key=lambda i: chain_verts[i].index)
        ordered = chain_verts[start:] + chain_verts[:start]
        if ordered[-1].index < ordered[1].index:
            ordered = [ordered[0]] + ordered[:0:-1]
        return ordered
    if chain_verts[0].index > chain_verts[-1].index:
        return list(reversed(chain_verts))
    return chain_verts


def _chain_from_component(comp):
    """把一个连通分量的选中边整理成有序顶点链，返回 ``(chain_verts, closed)``。

    只有两遍覆盖的顶点不同（真有分叉）时才拼接，避免整条链被折成两遍。
    """
    endpoints = _get_endpoints(comp)
    closed = len(endpoints) == 0
    if closed:
        chain_data = _build_edge_chain(comp, comp[0].verts[0])
        chain_verts = [item[0] for item in chain_data if item[1] is not None]
        if len(chain_verts) > 2 and chain_verts[0] == chain_verts[-1]:
            chain_verts.pop()
    elif len(endpoints) == 1:
        chain_verts = [item[0] for item in _build_edge_chain(comp, endpoints[0])]
    else:
        verts1 = [item[0] for item in _build_edge_chain(comp, endpoints[0])]
        verts2 = [item[0] for item in _build_edge_chain(comp, endpoints[1])]
        if set(verts1) == set(verts2):
            chain_verts = verts1
        else:
            tail = verts2[:-1] if verts2 else []
            tail.reverse()
            chain_verts = verts1 + tail

    if len(chain_verts) < 3:
        return [], closed
    return _chart_chain_direction(chain_verts, closed), closed


def _slide_target(data, t):
    """CIRCLE 模式下 t 时刻顶点的落点，预览圆弧、``_update_positions`` 和手柄共用。"""
    center = data['center']
    angle_p1 = data.get('angle_p1', 0.0)
    angle_p3 = data.get('angle_p3', 0.0)
    if center is None or angle_p1 * angle_p3 >= 0.0:
        # 平直面 / 三点共线 / 两条轨道落在顶点同侧：沿直线滑
        target = data['p3'] if t >= 0 else data['p1']
        return data['p2'] + (target - data['p2']) * abs(t)
    # 方向绑在侧别上：t>0 恒朝 p3、t<0 恒朝 p1
    angle = t * angle_p3 if t >= 0 else (-t) * angle_p1
    vec = data['init_vec'].copy()
    vec.rotate(mathutils.Quaternion(data['normal'], angle))
    return center + vec


def _slide_position(data, t, mode):
    """t 时刻顶点的落点：预览、模态和 F9 重放共用同一份计算。"""
    if mode == 'CIRCLE':
        return _slide_target(data, t)
    # 参数顺序要和 CIRCLE 对齐：t>0 恒走 p3 一侧
    if t >= 0:
        return _catmull_rom(data['p1'], data['p2'], data['p3'], data['p4'], t)
    return _catmull_rom(data['p3'], data['p2'], data['p1'], data['p0'], -t)


def _rail_length(data, mode, sign=1.0, samples=16):
    """从 t=0 到 t=sign 的轨道弧长（世界单位），用于距离/比例换算。"""
    total = 0.0
    previous = _slide_position(data, 0.0, mode)
    for index in range(1, samples + 1):
        current = _slide_position(data, sign * (index / samples), mode)
        total += (current - previous).length
        previous = current
    return total


def _pick_anchor_data(data, anchor_co):
    """按锚点坐标找回当初拖动的那个顶点数据（几乎没有成本，直接用最近点）"""
    target = Vector(anchor_co)
    if target.length_squared <= 1e-12:
        return data[0]
    return min(data, key=lambda item: (item['p2'] - target).length_squared)


def _amount_to_ratio(amount, rail_pos, rail_neg):
    if amount >= 0.0:
        return amount / rail_pos if rail_pos > 1e-9 else 0.0
    return amount / rail_neg if rail_neg > 1e-9 else 0.0


def _on_amount_mode_change(self, context):
    """切换比例/距离时换算当前数值，避免切换瞬间模型跳走。"""
    try:
        obj = getattr(context, "edit_object", None)
        if obj is None or obj.type != 'MESH':
            return
        bm = bmesh.from_edit_mesh(obj.data)
        data = [item for chain in _build_slide_data(bm) for item in chain]
        if not data:
            return
        anchor = _pick_anchor_data(data, self.anchor_co)
        rail = _rail_length(anchor, self.mode, 1.0 if self.amount >= 0 else -1.0)
        if rail <= 1e-9:
            return
        if self.amount_mode == 'DISTANCE':
            self.amount = self.amount * rail
        else:
            self.amount = self.amount / rail
    except Exception:
        pass


def _get_next_vert(curr_v, prev_v):
    best_v = None
    best_dot = -1.0
    vec_in = (curr_v.co - prev_v.co).normalized()
    for e in curr_v.link_edges:
        other_v = e.other_vert(curr_v)
        if other_v == prev_v:
            continue
        vec_out = (other_v.co - curr_v.co).normalized()
        dot = vec_in.dot(vec_out)
        if dot > best_dot:
            best_dot = dot
            best_v = other_v
    return best_v


def _build_slide_data(bm):
    """按边链分组建出滑移数据：``[[data, ...], ...]``，每个 data 对应一个顶点。"""
    selected_edges = [e for e in bm.edges if e.select and len(e.link_faces) > 0]
    if not selected_edges:
        return []
    all_selected = set(selected_edges)
    entries = []
    for comp in _div_set(selected_edges):
        chain_verts, closed = _chain_from_component(comp)
        if len(chain_verts) < 3:
            continue
        rail_map = _geometric_rail_verts(chain_verts, all_selected, closed=closed)
        chain_entries = []
        for v, (r1, r3) in zip(chain_verts, rail_map):
            if r1 is None and r3 is None:
                continue

            p2 = v.co.copy()
            # 一侧轨道缺失时按镜像补齐，两侧都缺才跳过
            p1 = r1.co.copy() if r1 is not None else p2 + (p2 - r3.co)
            p3 = r3.co.copy() if r3 is not None else p2 + (p2 - p1)
            v_next1 = _get_next_vert(r1, v) if r1 is not None else None
            v_next2 = _get_next_vert(r3, v) if r3 is not None else None
            p0 = v_next1.co.copy() if v_next1 else p1 + (p1 - p2)
            p4 = v_next2.co.copy() if v_next2 else p3 + (p3 - p2)

            center, radius, normal = _get_circle_from_3_points(p1, p2, p3)
            if center is not None:
                init_vec = p2 - center
                vec_p1 = p1 - center
                vec_p3 = p3 - center
                angle_p1 = math.atan2(init_vec.cross(vec_p1).dot(normal), init_vec.dot(vec_p1))
                angle_p3 = math.atan2(init_vec.cross(vec_p3).dot(normal), init_vec.dot(vec_p3))
                limit_min = min(angle_p1, angle_p3)
                limit_max = max(angle_p1, angle_p3)
            else:
                # 三点共线（平直面）：不再丢弃这个顶点，退化成直线滑移
                init_vec = Vector((0.0, 0.0, 0.0))
                angle_p1 = angle_p3 = 0.0
                limit_min = limit_max = 0.0

            chain_entries.append({
                'vert': v, 'init_co': p2.copy(),
                'center': center, 'radius': radius, 'normal': normal, 'init_vec': init_vec,
                'p0': p0, 'p1': p1, 'p2': p2, 'p3': p3, 'p4': p4,
                'angle_p1': angle_p1, 'angle_p3': angle_p3,
                'limit_min': limit_min, 'limit_max': limit_max
            })
        if chain_entries:
            entries.append(chain_entries)
    return entries


# ------------------------------------------------------------ T 面板控件
_DRAG = None
_OVERLAY_CACHE = {"key": None, "handles": [], "bm": None}


def _tool_active(context):
    if context.mode != 'EDIT_MESH':
        return False
    workspace = context.workspace
    if workspace is None:
        return False
    try:
        tool = workspace.tools.from_space_view3d_mode('EDIT_MESH', create=False)
    except Exception:
        return False
    return tool is not None and tool.idname == TOOL_ID


def _segment_distance(point, start, end):
    """点到线段的最短距离（屏幕空间命中用）"""
    segment = end - start
    length_squared = segment.length_squared
    if length_squared <= 1e-9:
        return (point - start).length
    factor = max(0.0, min(1.0, (point - start).dot(segment) / length_squared))
    return (point - (start + segment * factor)).length


def _chain_handles(entries):
    """每条链上每段边一个手柄：中心 = 边中点，长度 = 边长的一半。"""
    handles = []
    for chain in entries:
        pairs = list(zip(chain, chain[1:]))
        # 闭环链补上收尾那段边，保证“每条边都有手柄”
        if len(chain) > 2:
            try:
                if any(edge.other_vert(chain[-1]['vert']) == chain[0]['vert']
                       for edge in chain[-1]['vert'].link_edges):
                    pairs.append((chain[-1], chain[0]))
            except ReferenceError:
                pass
        for first, second in pairs:
            direction = second['p2'] - first['p2']
            length = direction.length
            if length <= 1e-9:
                continue
            handles.append({
                'center': (first['p2'] + second['p2']) * 0.5,
                'direction': direction / length,
                'half': length * 0.25,
                'data': first,
            })
    return handles


def _overlay_handles(context):
    """当前可拖的手柄列表（缓存，选择不变就不重建）"""
    obj = context.edit_object
    if obj is None or obj.type != 'MESH':
        return []
    mesh = obj.data
    bm = bmesh.from_edit_mesh(mesh)
    if len(bm.edges) > 20000:
        return []
    selected = [e.index for e in bm.edges if e.select and len(e.link_faces) > 0]
    key = (mesh.as_pointer(), len(bm.verts), len(selected), sum(selected))
    handles = _OVERLAY_CACHE["handles"]
    if _OVERLAY_CACHE["key"] == key:
        try:
            # 顶点被别处改过（刚滑完、撤销）就重建
            if not handles or (handles[0]['data']['vert'].co - handles[0]['data']['p2']).length < 1e-9:
                return handles
        except ReferenceError:
            pass
    handles = _chain_handles(_build_slide_data(bm))
    # bm 也要留着：它一被回收，handles 里的 BMVert 就成了失效引用
    _OVERLAY_CACHE.update(key=key, handles=handles, bm=bm)
    return handles


def _draw_disc(shader, center, radius, color, segments=20):
    verts = [(center.x, center.y)]
    for i in range(segments + 1):
        angle = math.tau * i / segments
        verts.append((center.x + math.cos(angle) * radius, center.y + math.sin(angle) * radius))
    shader.uniform_float("color", color)
    batch_for_shader(shader, 'TRI_FAN', {"pos": verts}).draw(shader)


def _bar_quad(positions, start, end, width):
    """把一条有厚度的把手（两个三角）追加到顶点列表"""
    direction = end - start
    length = direction.length
    if length < 1e-6:
        return
    normal = Vector((-direction.y, direction.x)) * (width * 0.5 / length)
    a = (start.x + normal.x, start.y + normal.y)
    b = (start.x - normal.x, start.y - normal.y)
    c = (end.x + normal.x, end.y + normal.y)
    d = (end.x - normal.x, end.y - normal.y)
    positions.extend([a, b, c, c, b, d])


def _draw_overlay():
    try:
        context = bpy.context
        if not _tool_active(context):
            return
        obj = context.edit_object
        region = context.region
        rv3d = context.region_data
        if obj is None or obj.type != 'MESH' or region is None or rv3d is None:
            return
        matrix = obj.matrix_world
        shader = gpu.shader.from_builtin('UNIFORM_COLOR')
        shader.bind()
        gpu.state.blend_set('ALPHA')

        # 拖拽中：只在当前手柄上画“原位 → 落点”的指示线，不画其它把手
        if _DRAG is not None:
            anchor = getattr(_DRAG, "_anchor", None)
            if anchor is None:
                gpu.state.blend_set('NONE')
                return
            t = getattr(_DRAG, "current_t", 0.0)
            mode = getattr(_DRAG, "mode", 'CIRCLE')
            start = view3d_utils.location_3d_to_region_2d(region, rv3d, matrix @ anchor['p2'])
            end = view3d_utils.location_3d_to_region_2d(
                region, rv3d, matrix @ _slide_position(anchor, t, mode))
            if start is not None and end is not None:
                if (end - start).length > 1.0:
                    gpu.state.line_width_set(2.0)
                    shader.uniform_float("color", (1.0, 0.83, 0.25, 0.85))
                    batch_for_shader(shader, 'LINES', {
                        "pos": [(start.x, start.y), (end.x, end.y)]}).draw(shader)
                    gpu.state.line_width_set(1.0)
                _draw_disc(shader, end, HANDLE_RADIUS + 1.0, (0.05, 0.05, 0.05, 0.8))
                _draw_disc(shader, end, HANDLE_RADIUS - 1.5, (1.0, 0.83, 0.25, 0.95))
            gpu.state.blend_set('NONE')
            return

        handles = _overlay_handles(context)
        if not handles:
            gpu.state.blend_set('NONE')
            return
        rotation = matrix.to_3x3()
        dark = []      # 外描边
        bright = []    # 主体
        for handle in handles:
            center = matrix @ handle['center']
            direction = (rotation @ handle['direction']).normalized()
            half = handle['half']
            start = view3d_utils.location_3d_to_region_2d(region, rv3d, center - direction * half)
            end = view3d_utils.location_3d_to_region_2d(region, rv3d, center + direction * half)
            if start is None or end is None:
                continue
            _bar_quad(dark, start, end, HANDLE_BAR_WIDTH + 2.0)
            _bar_quad(bright, start, end, HANDLE_BAR_WIDTH)
        if dark:
            shader.uniform_float("color", (0.05, 0.05, 0.05, 0.75))
            batch_for_shader(shader, 'TRIS', {"pos": dark}).draw(shader)
        if bright:
            shader.uniform_float("color", (1.0, 0.83, 0.25, 0.95))
            batch_for_shader(shader, 'TRIS', {"pos": bright}).draw(shader)
        gpu.state.blend_set('NONE')
    except ReferenceError:
        pass
    except Exception:
        traceback.print_exc()


# ---------------------------------------------------------------- 算 子
class _CurvatureSlideBase(bpy.types.Operator):
    """曲率滑动基类：只被 T 面板拖拽工具继承，自身不注册、也没有菜单入口。"""

    bl_options = {'REGISTER', 'UNDO'}

    mode: bpy.props.EnumProperty(
        name="模式",
        items=[('CIRCLE', "圆弧", "沿圆弧轨道滑移"),
               ('SPLINE', "样条", "沿向心 Catmull-Rom 样条滑移")],
        default='CIRCLE')
    amount_mode: bpy.props.EnumProperty(
        name="数值",
        items=[('RATIO', "比例", "按轨道比例（-1 ~ 1）表示滑移量"),
               ('DISTANCE', "距离", "按世界单位表示移动距离")],
        default='RATIO',
        update=_on_amount_mode_change)
    amount: bpy.props.FloatProperty(
        name="滑移量",
        description="比例模式：-1 ~ 1；距离模式：世界单位",
        default=0.0, soft_min=-1.0, soft_max=1.0)
    anchor_co: bpy.props.FloatVectorProperty(
        name="锚点", description="拖动手柄的原始位置，用于找回锚定顶点",
        default=(0.0, 0.0, 0.0), options={'HIDDEN'})

    @classmethod
    def poll(cls, context):
        return context.mode == 'EDIT_MESH'

    # ---------------------------------------------------------- F9 重放
    def _anchor_data(self, data):
        return _pick_anchor_data(data, self.anchor_co)

    def _ratio(self, anchor):
        """把面板数值换算成 -1 ~ 1 的轨道比例"""
        if self.amount_mode == 'RATIO':
            return max(-1.0, min(1.0, self.amount))
        rail_pos = _rail_length(anchor, self.mode, 1.0)
        rail_neg = _rail_length(anchor, self.mode, -1.0)
        return max(-1.0, min(1.0, _amount_to_ratio(self.amount, rail_pos, rail_neg)))

    def _finalize_properties(self):
        """把模态结果写回属性，供 F9 面板与撤销重放使用"""
        anchor = getattr(self, "_anchor", None)
        if anchor is None:
            data = getattr(self, "slide_data", None)
            anchor = data[0] if data else None
        if anchor is None:
            self.amount = 0.0
            return
        self.anchor_co = tuple(anchor['p2'])
        ratio = getattr(self, "current_t", 0.0)
        if self.amount_mode == 'DISTANCE':
            rail = _rail_length(anchor, self.mode, 1.0 if ratio >= 0 else -1.0)
            self.amount = ratio * rail
        else:
            self.amount = ratio

    def execute(self, context):
        obj = context.edit_object
        if obj is None:
            return {'CANCELLED'}
        bm = bmesh.from_edit_mesh(obj.data)
        data = [item for chain in _build_slide_data(bm) for item in chain]
        if not data:
            self.report({'WARNING'}, "找不到可滑移的腰线结构（选择是否还保留着？）")
            return {'CANCELLED'}
        t = self._ratio(self._anchor_data(data))
        for item in data:
            item['vert'].co = _slide_position(item, t, self.mode)
        bmesh.update_edit_mesh(obj.data)
        return {'FINISHED'}

    def draw(self, context):
        layout = self.layout
        column = layout.column()
        column.use_property_split = True
        column.prop(self, "mode", text="模式")
        column.prop(self, "amount_mode", text="数值")
        if self.amount_mode == 'RATIO':
            column.prop(self, "amount", text="滑移量", slider=True)
        else:
            column.prop(self, "amount", text="距离")

    def _on_invoke(self, context, event):
        """子类可在这里拦下不属于自己的点击。"""
        return True

    def _compute_t(self):
        delta_x = self.current_mouse_x - self.mouse_start_x
        return max(-1.0, min(1.0, delta_x * 0.005))

    def invoke(self, context, event):
        obj = context.edit_object
        self.bm = bmesh.from_edit_mesh(obj.data)
        self.matrix_world = obj.matrix_world.copy()
        self.mode = 'CIRCLE'
        self.current_t = 0.0
        self.current_mouse_reg = (event.mouse_region_x, event.mouse_region_y)

        entries = _build_slide_data(self.bm)
        self.slide_data = [data for chain in entries for data in chain]
        self.handles = _chain_handles(entries)

        if not self._on_invoke(context, event):
            return {'PASS_THROUGH'}
        if not self.slide_data:
            if any(e.select for e in self.bm.edges):
                self.report({'WARNING'}, "无法找到合适的腰线结构——请确保每条选中边两侧都有相邻面")
            else:
                self.report({'WARNING'}, "请先选中边线（非边界边）")
            return {'CANCELLED'}

        # GPU 批处理 + 模态
        self.batches_circle = []
        self.batches_spline = []
        shader = gpu.shader.from_builtin('UNIFORM_COLOR')
        for data in self.slide_data:
            center = data['center']
            radius = data['radius']
            normal = data['normal']
            if center is None or data['angle_p1'] * data['angle_p3'] >= 0.0:
                # 平直面 / 三点共线 / 两条轨道落在顶点同侧：没有跨过顶点的圆弧，
                # 画直线预览，和 _update_positions 里的退化处理保持一致
                points_circle = [
                    self.matrix_world @ data['p1'],
                    self.matrix_world @ data['p2'],
                    self.matrix_world @ data['p3'],
                ]
            else:
                tangent = data['init_vec'].normalized()
                bitangent = normal.cross(tangent).normalized()
                points_circle = []
                for i in range(33):
                    angle = data['limit_min'] + (data['limit_max'] - data['limit_min']) * (i / 32)
                    p_local = center + (tangent * math.cos(angle) + bitangent * math.sin(angle)) * radius
                    points_circle.append(self.matrix_world @ p_local)
            self.batches_circle.append(batch_for_shader(shader, 'LINE_STRIP', {"pos": points_circle}))
            points_spline = []
            for i in range(21):
                t = 1.0 - (i / 20)
                p_local = _catmull_rom(data['p3'], data['p2'], data['p1'], data['p0'], t)
                points_spline.append(self.matrix_world @ p_local)
            for i in range(1, 21):
                t = i / 20
                p_local = _catmull_rom(data['p1'], data['p2'], data['p3'], data['p4'], t)
                points_spline.append(self.matrix_world @ p_local)
            self.batches_spline.append(batch_for_shader(shader, 'LINE_STRIP', {"pos": points_spline}))

        self._handle = bpy.types.SpaceView3D.draw_handler_add(
            self._draw_callback, (context,), 'WINDOW', 'POST_VIEW')
        self._hud_handle = bpy.types.SpaceView3D.draw_handler_add(
            self._draw_hud_callback, (context,), 'WINDOW', 'POST_PIXEL')
        self._modal_border_handle = None
        _add_modal_border(self, context)
        self.mouse_start_x = event.mouse_x
        self.current_mouse_x = event.mouse_x
        context.window_manager.modal_handler_add(self)
        self._update_header(context)
        return {'RUNNING_MODAL'}

    def _update_header(self, context):
        mode_names = {'CIRCLE': "[C4D]圆弧", 'SPLINE': "[真曲率]样条"}
        msg = "滑动鼠标 | TAB: 切模式(%s) | 左键: 确认 | ESC: 取消" % mode_names[self.mode]
        context.workspace.status_text_set(msg)
        self._hud_text = msg

    def _draw_hud_callback(self, context):
        hud = getattr(self, '_hud_text', None)
        if hud:
            _draw_hud_text(hud, context)

    def _draw_callback(self, context):
        depth = 'NONE' if context.space_data.shading.show_xray else 'LESS_EQUAL'
        gpu.state.blend_set('ALPHA')
        gpu.state.line_width_set(2.0)
        gpu.state.depth_test_set(depth)
        shader = gpu.shader.from_builtin('UNIFORM_COLOR')
        shader.bind()
        if self.mode == 'CIRCLE':
            shader.uniform_float("color", (0.0, 1.0, 1.0, 0.5))
            for batch in self.batches_circle:
                batch.draw(shader)
        else:
            shader.uniform_float("color", (1.0, 0.6, 0.0, 0.8))
            for batch in self.batches_spline:
                batch.draw(shader)
        gpu.state.depth_test_set('NONE')
        gpu.state.blend_set('NONE')
        gpu.state.line_width_set(1.0)

    def _remove_draw_handler(self, context):
        global _DRAG
        if _DRAG is self:
            _DRAG = None
        _remove_modal_border(self)
        if hasattr(self, "_handle"):
            bpy.types.SpaceView3D.draw_handler_remove(self._handle, 'WINDOW')
            del self._handle
        if hasattr(self, "_hud_handle"):
            bpy.types.SpaceView3D.draw_handler_remove(self._hud_handle, 'WINDOW')
            del self._hud_handle
        context.workspace.status_text_set(None)
        context.area.tag_redraw()

    def _update_positions(self, context):
        t = self._compute_t()
        self.current_t = t
        for data in self.slide_data:
            data['vert'].co = _slide_position(data, t, self.mode)
        bmesh.update_edit_mesh(context.edit_object.data)

    def modal(self, context, event):
        try:
            if event.type == 'TAB' and event.value == 'PRESS':
                self.mode = 'SPLINE' if self.mode == 'CIRCLE' else 'CIRCLE'
                self._update_header(context)
                self._update_positions(context)
                context.area.tag_redraw()
                return {'RUNNING_MODAL'}
            if event.type == 'MOUSEMOVE':
                self.current_mouse_x = event.mouse_x
                self.current_mouse_reg = (event.mouse_region_x, event.mouse_region_y)
                self._update_positions(context)
                context.area.tag_redraw()
                return {'RUNNING_MODAL'}
            elif event.type in {'LEFTMOUSE', 'RIGHTMOUSE', 'RET', 'NUMPAD_ENTER'}:
                self._finalize_properties()
                self._remove_draw_handler(context)
                return {'FINISHED'}
            elif event.type == 'ESC':
                for data in self.slide_data:
                    data['vert'].co = data['init_co']
                bmesh.update_edit_mesh(context.edit_object.data)
                self._remove_draw_handler(context)
                return {'CANCELLED'}
            return {'RUNNING_MODAL'}
        except Exception as e:
            traceback.print_exc()
            self._remove_draw_handler(context)
            self.report({'ERROR'}, f"曲率滑移出错已安全退出: {str(e)}")
            return {'CANCELLED'}


class BetterExperie_OT_CurvatureSlideDrag(_CurvatureSlideBase):
    """T 面板工具用：拖动叠绘手柄滑移，t 由手柄在屏幕上的投影决定。"""
    bl_idname = "better_experie.curv_slide_drag"
    bl_label = "拖动曲率滑动"
    bl_description = "拖动选中边线上的手柄，保持曲率滑移（F9 可微调模式与滑移量）"

    def invoke(self, context, event):
        result = super().invoke(context, event)
        if result == {'PASS_THROUGH'}:
            # 工具的左键会把原生点选挡掉，没点到手柄时手动补一次；
            # 返回 CANCELLED，避免在撤销栈里留下一条什么都沒做的记录
            try:
                bpy.ops.view3d.select(
                    'INVOKE_DEFAULT', extend=event.shift, deselect=event.ctrl,
                    toggle=False, location=(event.mouse_region_x, event.mouse_region_y))
            except Exception:
                pass
            return {'CANCELLED'}
        return result

    def _on_invoke(self, context, event):
        region = context.region
        rv3d = context.region_data
        if region is None or rv3d is None or not self.handles:
            return False
        mouse = Vector((event.mouse_region_x, event.mouse_region_y))
        rotation = self.matrix_world.to_3x3()
        anchor = None
        best = HANDLE_HIT
        for handle in self.handles:
            center = self.matrix_world @ handle['center']
            direction = (rotation @ handle['direction']).normalized()
            half = handle['half']
            start = view3d_utils.location_3d_to_region_2d(region, rv3d, center - direction * half)
            end = view3d_utils.location_3d_to_region_2d(region, rv3d, center + direction * half)
            if start is None or end is None:
                continue
            dist = _segment_distance(mouse, start, end)
            if dist <= best:
                anchor, best = handle, dist
        if anchor is None:
            # 没点到手柄：把这次点击让给原生的选择
            return False
        data = anchor['data']
        self._anchor = data
        # 以点击点作为拖动原点，点到边上的任意位置都不会立即跳量
        self._drag_start = mouse
        self._screen_p2 = view3d_utils.location_3d_to_region_2d(
            region, rv3d, self.matrix_world @ data['p2'])
        self._dir_pos = self._screen_to(region, rv3d, data['p3']) - self._screen_p2
        self._dir_neg = self._screen_to(region, rv3d, data['p1']) - self._screen_p2
        global _DRAG
        _DRAG = self
        return True

    def _screen_to(self, region, rv3d, co):
        pos = view3d_utils.location_3d_to_region_2d(region, rv3d, self.matrix_world @ co)
        return pos if pos is not None else self._screen_p2

    def _compute_t(self):
        origin = getattr(self, "_drag_start", None) or getattr(self, "_screen_p2", None)
        if origin is None:
            return 0.0
        offset = Vector((self.current_mouse_reg[0] - origin.x,
                         self.current_mouse_reg[1] - origin.y))
        if self._dir_pos.length_squared <= 16.0 and self._dir_neg.length_squared <= 16.0:
            # 轨道在屏幕上几乎缩成一点，退回按鼠标横向位移换算
            return max(-1.0, min(1.0, (self.current_mouse_x - self.mouse_start_x) * 0.005))
        if self._dir_pos.length_squared > 16.0 and offset.dot(self._dir_pos) >= 0.0:
            t = offset.dot(self._dir_pos) / self._dir_pos.length_squared
        elif self._dir_neg.length_squared > 16.0:
            t = -offset.dot(self._dir_neg) / self._dir_neg.length_squared
        else:
            t = 0.0
        return max(-1.0, min(1.0, t))


# ---------------------------------------------------------------- 工 具
_ADDON_DIR = os.path.dirname(os.path.abspath(__file__))


def _tool_icon():
    """自定义图标：workspacetool/icons/curvature_slide.dat（Blender 自己补扩展名）"""
    own = os.path.join(_ADDON_DIR, "icons", "curvature_slide")
    if os.path.isfile(own + ".dat"):
        return own
    return "ops.generic.select_box"


class BetterExperie_TL_CurvatureSlideTool(bpy.types.WorkSpaceTool):
    bl_idname = TOOL_ID
    bl_space_type = 'VIEW_3D'
    bl_context_mode = 'EDIT_MESH'
    bl_label = "保持曲率滑动"
    bl_icon = _tool_icon()
    bl_widget = None
    bl_keymap = (
        ("better_experie.curv_slide_drag", {"type": "LEFTMOUSE", "value": "PRESS"},
         {"properties": []}),
    )

    @staticmethod
    def draw_settings(context, layout, tool):
        col = layout.column(align=True)
        col.label(text="拖边上的手柄")
        col.label(text="TAB 切模式")
        col.label(text="F9 微调滑移量")


classes = (
    BetterExperie_OT_CurvatureSlideDrag,
)

_OVERLAY_HANDLE = None
_TOOL_GROUP = None


def _merge_tool_group():
    """把自己塞进原生「滑移边线 / 顶点滑移」那个工具组的下拉里。

    这是对 ToolSelectPanelHelper 私有结构的改写，必须幂等：
    重复调用（热重载会走两轮注册）时不能再合一次。
    """
    global _TOOL_GROUP
    if _TOOL_GROUP is not None:
        return
    try:
        from bl_ui.space_toolsystem_common import ToolSelectPanelHelper
    except ImportError:
        return
    cls = ToolSelectPanelHelper._tool_class_from_space_type('VIEW_3D')
    if cls is None:
        return
    tools = cls._tools.get('EDIT_MESH')
    if not tools:
        return
    own = None
    target = None
    for item in tools:
        if not isinstance(item, tuple):
            continue
        names = [getattr(sub, 'idname', '') for sub in item if sub is not None]
        if TOOL_ID in names:
            own = item
        elif 'builtin.edge_slide' in names:
            target = item
    if own is None or target is None:
        return
    member = next((sub for sub in own if getattr(sub, 'idname', '') == TOOL_ID), None)
    if member is None:
        return
    if member in target:
        return
    merged = tuple(list(target) + [member])
    rest = []
    for item in tools:
        if item is own:
            continue
        if item is None and rest and rest[-1] is None:
            continue
        rest.append(item)
    while rest and rest[-1] is None:
        rest.pop()
    cls._tools['EDIT_MESH'] = [merged if item is target else item for item in rest]
    _TOOL_GROUP = (cls, target, merged, member)


def _split_tool_group():
    """注销前拆回去，否则 unregister_tool 找不到自己的那一条。"""
    global _TOOL_GROUP
    if _TOOL_GROUP is None:
        return
    cls, target, merged, member = _TOOL_GROUP
    try:
        tools = cls._tools['EDIT_MESH']
        for index, item in enumerate(tools):
            if item is merged:
                tools[index:index + 1] = [target, (member,)]
                break
    except (KeyError, ValueError):
        pass
    _TOOL_GROUP = None


def register():
    global _OVERLAY_HANDLE, _DRAG
    for cls in classes:
        try:
            bpy.utils.register_class(cls)
        except Exception:
            pass
    _DRAG = None
    if _OVERLAY_HANDLE is None:
        _OVERLAY_HANDLE = bpy.types.SpaceView3D.draw_handler_add(
            _draw_overlay, (), 'WINDOW', 'POST_PIXEL')
    try:
        bpy.utils.register_tool(BetterExperie_TL_CurvatureSlideTool,
                                after={"builtin.edge_slide"}, separator=True, group=True)
    except Exception:
        pass
    _merge_tool_group()


def unregister():
    global _OVERLAY_HANDLE, _DRAG
    _split_tool_group()
    _DRAG = None
    _OVERLAY_CACHE.update(key=None, handles=[], bm=None)
    if _OVERLAY_HANDLE is not None:
        try:
            bpy.types.SpaceView3D.draw_handler_remove(_OVERLAY_HANDLE, 'WINDOW')
        except Exception:
            pass
        _OVERLAY_HANDLE = None
    try:
        bpy.utils.unregister_tool(BetterExperie_TL_CurvatureSlideTool)
    except Exception:
        pass
    for cls in reversed(classes):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass
