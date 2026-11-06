# UV 非流形循环边（批处理）：沿 UV 走向续接整条链，接缝处自然断开

import bpy
import bmesh
import math

from mathutils import Vector

from ...utils.uv_topology import (
    EPS,
    other_vert,
    seg_dir,
    segments_from,
    write_selection,
)

DIR_RULE_ITEMS = (
    ('U', "+U", "A 端 = 朝 +U 方向延伸的那一端"),
    ('V', "+V", "A 端 = 朝 +V 方向延伸的那一端"),
    ('MAJORITY', "众向", "以第一个选中元素的走向为基准，其余元素向它对齐"),
)


def reference_vector(rule, first_seed, layer):
    """参考方向（UV 空间 2D 向量）；MAJORITY 取第一条种子自身的走向"""
    if rule == 'U':
        return Vector((1.0, 0.0))
    if rule == 'V':
        return Vector((0.0, 1.0))
    return seg_dir(first_seed, layer)


def collect_seeds(bm, layer, sync):
    """当前被选中的 UV 边（sync 时来自网格边选择，否则来自 UV 逐 loop 标志）"""
    seeds = []
    if sync:
        for edge in bm.edges:
            if edge.hide or not edge.select:
                continue
            for face in edge.link_faces:
                if face.hide:
                    continue
                loop = next((l for l in face.loops if l.edge is edge), None)
                if loop is not None and loop not in seeds:
                    seeds.append(loop)
    else:
        for face in bm.faces:
            if face.hide:
                continue
            for loop in face.loops:
                if loop.uv_select_edge:
                    seeds.append(loop)
    return seeds


def a_end_vert(seed, layer, ref):
    """A 端：外指方向与参考方向同侧的那一端；ref 为 None 时退回 loop 顺序"""
    d = seg_dir(seed, layer)
    if ref is None or d is None:
        return seed.link_loop_next.vert
    return seed.link_loop_next.vert if d.dot(ref) > 0.0 else seed.vert


def walk_arm(seed, layer, start_vert, max_angle, limit):
    """从 seed 的某一端出发按走向续接，返回段（loop）列表"""
    v0, v1 = seed.vert, seed.link_loop_next.vert
    u0, u1 = seed[layer].uv.copy(), seed.link_loop_next[layer].uv.copy()
    if start_vert is v0:
        cur_vert, cur_uv, prev_uv = v0, u0, u1
    else:
        cur_vert, cur_uv, prev_uv = v1, u1, u0

    threshold = math.cos(max_angle)
    budget = limit if limit > 0 else 10000
    out = []
    for _ in range(budget):
        in_vec = cur_uv - prev_uv
        if in_vec.length < EPS:
            break
        in_vec = in_vec.normalized()

        best, best_dot = None, threshold
        for seg, other, other_uv, direction in segments_from(cur_vert, cur_uv, layer):
            dot = in_vec.dot(direction)
            if dot > best_dot:
                best, best_dot = (seg, other, other_uv), dot
        if best is None:
            break

        seg, other, other_uv = best
        out.append(seg)
        prev_uv, cur_vert, cur_uv = cur_uv, other, other_uv
    return out


def trace(seed, layer, direction, steps, max_angle, ref):
    """按延伸方向模式展开一条种子边，返回段列表（含种子本身）"""
    limit = abs(steps)
    result = [seed]

    if direction == 'BOTH':
        starts = [seed.vert, seed.link_loop_next.vert]
    else:
        start = a_end_vert(seed, layer, ref)
        if direction == 'DIR_B' or steps < 0:
            start = other_vert(seed, start)
        starts = [start]

    for start_vert in starts:
        result.extend(walk_arm(seed, layer, start_vert, max_angle, limit))
    return result


class BetterExperie_OT_UVSelectNonManifoldEdgeLoop(bpy.types.Operator):
    bl_idname = "better_experie.uv_select_nonmanifold_edge_loop"
    bl_label = "UV 非流形循环边（批处理）"
    bl_description = "从选中的 UV 边出发，沿 UV 走向续接整条链（接缝处自然断开）"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return (
            context.active_object is not None
            and context.active_object.type == 'MESH'
            and context.mode == 'EDIT_MESH'
        )

    trace_dir: bpy.props.EnumProperty(
        name="延伸方向",
        items=[
            ('BOTH', "双向", ""),
            ('DIR_A', "方向 A", ""),
            ('DIR_B', "方向 B", ""),
        ], default='BOTH')
    dir_rule: bpy.props.EnumProperty(
        name="方向定义", items=DIR_RULE_ITEMS, default='MAJORITY')
    steps: bpy.props.IntProperty(
        name="延伸步数", description="向两端延伸的段数（绝对值），0 为不设限，单边模式下负数为反向延伸",
        default=0, min=-10000, max=10000)
    max_angle: bpy.props.FloatProperty(
        name="最大转向角", description="相邻 UV 段的方向偏差超过此值则停止",
        default=math.radians(45.0), min=0.0, max=math.radians(90.0), unit='ROTATION')

    def execute(self, context):
        obj = context.edit_object
        bm = bmesh.from_edit_mesh(obj.data)
        layer = bm.loops.layers.uv.active
        if layer is None:
            self.report({'WARNING'}, "没有活动的 UV 层")
            return {'CANCELLED'}

        sync = context.tool_settings.use_uv_select_sync
        seeds = collect_seeds(bm, layer, sync)
        if not seeds:
            self.report({'WARNING'}, "请先选中至少一条 UV 边")
            return {'CANCELLED'}

        ref = reference_vector(self.dir_rule, seeds[0], layer)
        picked = set()
        for seed in seeds:
            picked.update(trace(seed, layer, self.trace_dir, self.steps, self.max_angle, ref))

        write_selection(bm, picked, layer, sync,
                        mode=context.tool_settings.uv_select_mode)
        if sync:
            bm.select_flush_mode()
        bmesh.update_edit_mesh(obj.data)
        return {'FINISHED'}


classes = (
    BetterExperie_OT_UVSelectNonManifoldEdgeLoop,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
