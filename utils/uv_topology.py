# UV 空间的拓扑辅助
#
# UV 里的「一条边」= 某个面里的一个 loop 段（loop.vert → loop.next.vert）。
# 两个面只有在共享同一条网格边、且两端 UV 都相同时才算 UV 连通；
# 接缝处两端的 UV 不同，所以遍历会在接缝自然断开。

from mathutils import Vector

EPS = 1e-6


def seg_uv0(loop, layer):
    return loop[layer].uv


def seg_uv1(loop, layer):
    return loop.link_loop_next[layer].uv


def seg_dir(loop, layer):
    """这一段的方向（起点 → 终点，UV 空间单位向量）"""
    d = seg_uv1(loop, layer) - seg_uv0(loop, layer)
    return d.normalized() if d.length > EPS else None


def seg_mid(loop, layer):
    return (seg_uv0(loop, layer) + seg_uv1(loop, layer)) * 0.5


def other_vert(loop, vert):
    nxt = loop.link_loop_next
    return nxt.vert if vert is loop.vert else loop.vert


def segments_from(vert, co, layer, eps=EPS):
    """从 UV 点 (vert, co) 出发的所有 UV 边段。

    返回 [(start_loop, other_vert, other_uv, 单位方向), ...]
    start_loop 满足 start_loop.vert is vert、start_loop.link_loop_next.vert is other_vert。
    """
    out = []
    for loop in vert.link_loops:
        if (loop[layer].uv - co).length > eps:
            continue                      # 接缝另一侧的 loop：UV 不在同一处
        nxt = loop.link_loop_next
        if nxt.vert is not vert:
            d = nxt[layer].uv - co
            if d.length > eps:
                out.append((loop, nxt.vert, nxt[layer].uv.copy(), d.normalized()))
        prv = loop.link_loop_prev
        if prv.vert is not vert:
            d = prv[layer].uv - co
            if d.length > eps:
                out.append((prv, prv.vert, prv[layer].uv.copy(), d.normalized()))
    return out


def segment_in_face(edge, face, layer):
    """face 里对应 mesh 边 edge 的那个 loop 段（face 自己的 UV 表示）"""
    for loop in face.loops:
        if loop.edge is edge:
            return loop
    return None


def uv_edge_faces(loop, layer, eps=EPS):
    """与 loop 这一段共享同一条 UV 边的所有面（两端 UV 相同）；loop.face 排第一"""
    u0, u1 = seg_uv0(loop, layer), seg_uv1(loop, layer)
    faces = [loop.face]
    for face in loop.edge.link_faces:
        if face is loop.face:
            continue
        cand = segment_in_face(loop.edge, face, layer)
        if cand is None:
            continue
        a, b = seg_uv0(cand, layer), seg_uv1(cand, layer)
        same = ((a - u0).length <= eps and (b - u1).length <= eps)
        flipped = ((a - u1).length <= eps and (b - u0).length <= eps)
        if same or flipped:
            faces.append(face)
    return faces


def opposite_segment(loop, layer):
    """面内与 loop 这一段相对的那一段。

    四边形直接取对边（loop.next.next）；其它面用「中点偏移最贴合垂直方向」挑。
    """
    face = loop.face
    if len(face.loops) == 4:
        return loop.link_loop_next.link_loop_next

    base_mid = seg_mid(loop, layer)
    base_dir = seg_dir(loop, layer)
    if base_dir is None:
        return None
    normal = Vector((-base_dir.y, base_dir.x))
    best, best_score = None, -1.0
    skip = {loop, loop.link_loop_next}
    for cand in face.loops:
        if cand in skip:
            continue
        d = seg_mid(cand, layer) - base_mid
        if d.length < EPS:
            continue
        score = abs(d.normalized().dot(normal))
        if score > best_score:
            best, best_score = cand, score
    return best


def write_selection(bm, loops, layer, sync, select=True, mode='EDGE'):
    """把段集合写回选择。

    sync=True 时 UV 选择跟随网格选择，写网格边；否则按 UV 选择模式写逐 loop 标志。
    注意：这里不调用 uv_select_flush，否则「两端都被选中的其它边」会被连带选中。
    """
    if sync:
        for loop in loops:
            loop.edge.select = select
        return

    for loop in loops:
        if mode == 'VERTEX':
            loop.uv_select_vert_set(select)
            loop.link_loop_next.uv_select_vert_set(select)
        elif mode == 'FACE':
            loop.face.uv_select_set(select)
        else:
            loop.uv_select_edge_set(select)
            loop.uv_select_vert_set(select)
            loop.link_loop_next.uv_select_vert_set(select)
