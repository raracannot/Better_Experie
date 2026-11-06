# UV 并排边环（批处理）：从选中的 UV 边出发，跨面沿「对边」方向扩选

import bpy
import bmesh
import math

from mathutils import Vector

from ...utils.select_direction import rank_by_reference
from ...utils.uv_topology import (
    EPS,
    opposite_segment,
    seg_mid,
    segment_in_face,
    uv_edge_faces,
    write_selection,
)

DIR_RULE_ITEMS = (
    ('U', "+U", "A 侧 = 朝 +U 方向延伸的那一侧"),
    ('V', "+V", "A 侧 = 朝 +V 方向延伸的那一侧"),
    ('MAJORITY', "众向", "以第一个选中元素的走向为基准，其余元素向它对齐"),
)


def side_direction(seed, face, layer):
    """该面相对种子边的「跨面」方向（种子边中点 → 对边中点，UV 空间）"""
    cur = segment_in_face(seed.edge, face, layer)
    if cur is None:
        return None
    opp = opposite_segment(cur, layer)
    if opp is None:
        return None
    delta = seg_mid(opp, layer) - seg_mid(cur, layer)
    return delta.normalized() if delta.length > EPS else None


def reference_vector(rule, first_seed, layer):
    """参考方向（UV 空间 2D）；MAJORITY 取第一条种子、第一个相邻面的跨面方向"""
    if rule == 'U':
        return Vector((1.0, 0.0))
    if rule == 'V':
        return Vector((0.0, 1.0))
    return side_direction(first_seed, first_seed.face, layer)


def collect_seeds(bm, layer, sync):
    """当前被选中的 UV 边"""
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


def ordered_sides(seed, layer, ref):
    """按参考方向给种子的两侧排序；A 侧 = 首位"""
    sides = uv_edge_faces(seed, layer)
    if ref is not None and len(sides) > 1:
        sides = rank_by_reference(
            sides, lambda face: side_direction(seed, face, layer), ref)
    return sides


def expand_side(seed, layer, face, limit):
    """沿一侧一直扩选，返回段列表"""
    cur = segment_in_face(seed.edge, face, layer)
    if cur is None:
        return []

    budget = limit if limit > 0 else 10000
    out = []
    for _ in range(budget):
        opp = opposite_segment(cur, layer)
        if opp is None:
            break
        out.append(opp)

        others = [f for f in uv_edge_faces(opp, layer) if f is not cur.face]
        if not others:
            break
        nxt = segment_in_face(opp.edge, others[0], layer)
        if nxt is None:
            break
        cur = nxt
    return out


def trace(seed, layer, direction, steps, ref):
    """按方向模式展开一条种子边，返回段列表（含种子本身）"""
    result = [seed]
    sides = ordered_sides(seed, layer, ref)
    if not sides:
        return result

    limit = abs(steps)
    if direction == 'BOTH':
        targets = sides
    elif direction == 'DIR_A':
        targets = sides[:1] if steps >= 0 else sides[1:]
    else:  # DIR_B
        targets = sides[1:] if steps >= 0 else sides[:1]

    for face in targets:
        result.extend(expand_side(seed, layer, face, limit))
    return result


class BetterExperie_OT_UVSelectEdgeRing(bpy.types.Operator):
    bl_idname = "better_experie.uv_select_edge_ring"
    bl_label = "UV 并排边环（批处理）"
    bl_description = "从选中的 UV 边出发，跨面沿对边方向扩选（接缝处自然断开）"
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
        name="扩选次数", description="向两侧扩选的段数（绝对值），0 为不设限，单边模式下负数为反向延伸",
        default=0, min=-10000, max=10000)
    max_angle: bpy.props.FloatProperty(
        name="最大转向角", description="保留参数，当前按四边形对边扩展，不使用角度限制",
        default=math.radians(90.0), min=0.0, max=math.radians(180.0), unit='ROTATION')

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
            picked.update(trace(seed, layer, self.trace_dir, self.steps, ref))

        write_selection(bm, picked, layer, sync,
                        mode=context.tool_settings.uv_select_mode)
        if sync:
            bm.select_flush_mode()
        bmesh.update_edit_mesh(obj.data)
        return {'FINISHED'}


classes = (
    BetterExperie_OT_UVSelectEdgeRing,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
