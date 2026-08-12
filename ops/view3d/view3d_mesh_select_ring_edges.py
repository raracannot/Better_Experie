# 并排边环选择：两个入口 — 批处理（先选边后点）与交互式模态（GPU HUD 预览）

import bpy
import bmesh
import math
import gpu
import traceback
from mathutils.bvhtree import BVHTree
from bpy_extras import view3d_utils
from gpu_extras.batch import batch_for_shader
from ...utils.modal_border import add_modal_border, remove_modal_border


def _dist_to_edge(point, edge_v1, edge_v2):
    line_vec = edge_v2 - edge_v1
    p_vec = point - edge_v1
    line_len_sq = line_vec.length_squared
    if line_len_sq == 0:
        return p_vec.length
    t = max(0.0, min(1.0, p_vec.dot(line_vec) / line_len_sq))
    closest_point = edge_v1 + t * line_vec
    return (point - closest_point).length


def _get_opposite_edge_geometric(face, edge, parallel_factor=0.5):
    if len(face.edges) < 3:
        return None
    v1, v2 = edge.verts[0].co, edge.verts[1].co
    mid_point = (v1 + v2) / 2
    edge_vec = (v2 - v1).normalized()
    perp_dir = edge_vec.cross(face.normal).normalized()
    best_edge = None
    max_alignment = -1.0
    for other_edge in face.edges:
        if other_edge == edge or other_edge.hide:
            continue
        other_mid = (other_edge.verts[0].co + other_edge.verts[1].co) / 2
        target_vec = (other_mid - mid_point).normalized()
        alignment = abs(target_vec.dot(perp_dir))
        if alignment > max_alignment:
            max_alignment = alignment
            best_edge = other_edge
    return best_edge if max_alignment >= parallel_factor else None


def _expand_ring_from_edge(bm, start_edge, steps, parallel_factor=0.5,
                           max_angle=math.radians(90), stop_at_sharp=False,
                           trace_dir='BOTH'):
    result = {start_edge}
    limit = abs(steps)
    # 单边模式下负数为反向延伸
    if steps >= 0 or trace_dir == 'BOTH':
        eff_dir = trace_dir
    else:
        eff_dir = 'DIR_B' if trace_dir == 'DIR_A' else 'DIR_A'

    def _next_opp(face, from_edge):
        """返回满足所有限制的对边，否则返回 None"""
        opp = _get_opposite_edge_geometric(face, from_edge, parallel_factor)
        if not opp or opp in result:
            return None
        if stop_at_sharp and not opp.smooth:
            return None
        if max_angle < math.radians(90):
            cur_dir = (from_edge.verts[1].co - from_edge.verts[0].co).normalized()
            nxt_dir = (opp.verts[1].co - opp.verts[0].co).normalized()
            if abs(cur_dir.dot(nxt_dir)) < math.cos(max_angle):
                return None
        return opp

    def _expand_chain(start_face, from_edge):
        """单方向独立扩选：本侧的边栈与本侧步数计数，互不影响另一侧"""
        edge_stack = []
        opp = _next_opp(start_face, from_edge)
        if opp:
            result.add(opp)
            edge_stack.append(opp)

        steps_taken = 0
        while edge_stack and (limit <= 0 or steps_taken < limit):
            curr_edge = edge_stack.pop()
            for face in curr_edge.link_faces:
                nxt = _next_opp(face, curr_edge)
                if nxt:
                    result.add(nxt)
                    edge_stack.append(nxt)
            steps_taken += 1

    start_faces = list(start_edge.link_faces)
    if eff_dir in {'BOTH', 'DIR_A'} and len(start_faces) > 0:
        _expand_chain(start_faces[0], start_edge)
    if eff_dir in {'BOTH', 'DIR_B'} and len(start_faces) > 1:
        _expand_chain(start_faces[1], start_edge)
    return result


# ═══════════════════════════════════════════════════════════════
# 入口 A：批处理（先选边后点，纯 execute）
# ═══════════════════════════════════════════════════════════════

class BetterExperie_EdgeRingSettings(bpy.types.PropertyGroup):
    """并排边环交互选取的参数设置（挂载到 Scene）"""
    trace_dir: bpy.props.EnumProperty(
        name="延伸方向",
        items=[
            ('BOTH', "双向", ""),
            ('DIR_A', "方向 A", ""),
            ('DIR_B', "方向 B", ""),
        ], default='BOTH')
    steps: bpy.props.IntProperty(
        name="扩选次数", description="向两端扩选的段数（绝对值），0为不设限，单边模式下负数为反向延伸",
        default=0, min=-10000, max=10000)
    max_angle: bpy.props.FloatProperty(
        name="最大转向角", description="相邻环边的方向偏差超过此值则停止",
        default=math.radians(90), min=0.0, max=math.radians(180), unit='ROTATION')
    parallel_factor: bpy.props.FloatProperty(
        name="平行系数", description="对边匹配的严格程度，越大越严格", default=0.5, min=0.0, max=1.0)
    stop_at_sharp: bpy.props.BoolProperty(
        name="锐点处停止", description="遇到锐边时停止扩选", default=False)


def _get_ring_settings(context):
    return context.scene.better_experie_edge_ring_settings


class BetterExperie_OT_SelectEdgeRingGeo(bpy.types.Operator):
    bl_idname = "better_experie.select_edge_ring_geo"
    bl_label = "选择并排边环（批处理）"
    bl_description = "从当前选中的边出发，沿并排（Ring）方向几何算法扩选至非流形区域（0步为不设限，单边负数反向）"
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
    steps: bpy.props.IntProperty(
        name="扩选次数", description="向两端扩选的段数（绝对值），0为不设限，单边模式下负数为反向延伸",
        default=0, min=-10000, max=10000)
    max_angle: bpy.props.FloatProperty(
        name="最大转向角", description="相邻环边的方向偏差超过此值则停止",
        default=math.radians(90), min=0.0, max=math.radians(180), unit='ROTATION')
    parallel_factor: bpy.props.FloatProperty(
        name="平行系数", description="对边匹配的严格程度，越大越严格", default=0.5, min=0.0, max=1.0)
    stop_at_sharp: bpy.props.BoolProperty(
        name="锐点处停止", description="遇到锐边时停止扩选", default=False)

    def draw(self, context):
        layout = self.layout
        col = layout.column(align=True)
        col.prop(self, "trace_dir", expand=True)
        col.prop(self, "steps")
        col.separator()
        col.prop(self, "max_angle", slider=True)
        col.prop(self, "parallel_factor", slider=True)
        col.separator()
        col.prop(self, "stop_at_sharp")

    def execute(self, context):
        obj = context.edit_object
        bm = bmesh.from_edit_mesh(obj.data)
        bm.edges.ensure_lookup_table()
        bm.faces.ensure_lookup_table()

        start_edges = [e for e in bm.edges if e.select]
        if not start_edges:
            self.report({'WARNING'}, "请先选择至少一条边")
            return {'CANCELLED'}

        chain = set()
        for e in start_edges:
            chain.update(_expand_ring_from_edge(
                bm, e, self.steps, self.parallel_factor,
                self.max_angle, self.stop_at_sharp, self.trace_dir))

        for e in chain:
            e.select = True

        bmesh.update_edit_mesh(obj.data)
        return {'FINISHED'}


# ═══════════════════════════════════════════════════════════════
# 入口 B：交互式模态（GPU HUD 预览 + 点击选取）
# ═══════════════════════════════════════════════════════════════

def _draw_hud(self, context):
    try:
        if not self.preview_coords:
            return
        shader = gpu.shader.from_builtin('UNIFORM_COLOR')
        is_xray = False
        if context.space_data and hasattr(context.space_data.shading, 'show_xray'):
            is_xray = context.space_data.shading.show_xray
        try:
            gpu.state.line_width_set(3.0)
            gpu.state.depth_test_set('NONE' if is_xray else 'LESS_EQUAL')
            matrix = context.object.matrix_world
            world_coords = []
            for pair in self.preview_coords:
                world_coords.append(matrix @ pair[0])
                world_coords.append(matrix @ pair[1])
            batch = batch_for_shader(shader, 'LINES', {"pos": world_coords})
            shader.bind()
            shader.uniform_float("color", (0.0, 0.8, 1.0, 1.0))
            batch.draw(shader)
        finally:
            gpu.state.line_width_set(1.0)
            gpu.state.depth_test_set('LESS_EQUAL')
    except ReferenceError:
        pass
    except Exception:
        traceback.print_exc()


class BetterExperie_OT_SelectEdgeRingInteractive(bpy.types.Operator):
    bl_idname = "better_experie.select_edge_ring_interactive"
    bl_label = "选择并排边环（交互）"
    bl_description = "鼠标悬浮预览并排边环，左键选中（Shift加选 Ctrl减选），Shift滚轮调段数，Tab切换方向，右键取消"
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
    steps: bpy.props.IntProperty(
        name="扩选次数", description="向两端扩选的段数（绝对值），0为不设限，单边模式下负数为反向延伸",
        default=0, min=-10000, max=10000)
    max_angle: bpy.props.FloatProperty(
        name="最大转向角", description="相邻环边的方向偏差超过此值则停止",
        default=math.radians(90), min=0.0, max=math.radians(180), unit='ROTATION')
    parallel_factor: bpy.props.FloatProperty(
        name="平行系数", description="对边匹配的严格程度", default=0.5, min=0.0, max=1.0)
    stop_at_sharp: bpy.props.BoolProperty(
        name="锐点处停止", description="遇到锐边时停止扩选", default=False)
    target_edge_idx: bpy.props.IntProperty(default=-1, options={'HIDDEN'})
    select_mode: bpy.props.EnumProperty(
        items=[('SET', "设置", ""), ('ADD', "加选", ""), ('SUB', "减选", "")],
        default='SET', options={'HIDDEN'})

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._handle = None
        self._modal_border_handle = None
        self.preview_coords = []
        self.bvhtree = None

    def draw(self, context):
        s = _get_ring_settings(context)
        layout = self.layout
        col = layout.column(align=True)
        col.prop(s, "trace_dir", expand=True)
        col.prop(s, "steps")
        col.separator()
        col.prop(s, "max_angle", slider=True)
        col.prop(s, "parallel_factor", slider=True)
        col.separator()
        col.prop(s, "stop_at_sharp")

    def invoke(self, context, event):
        try:
            if not self.poll(context):
                self.report({'WARNING'}, "请在3D视图的编辑模式下运行")
                return {'CANCELLED'}

            bm = bmesh.from_edit_mesh(context.edit_object.data)
            self.bvhtree = BVHTree.FromBMesh(bm)
            args = (self, context)
            self._handle = bpy.types.SpaceView3D.draw_handler_add(
                _draw_hud, args, 'WINDOW', 'POST_VIEW')

            add_modal_border(self, context)
            context.window.cursor_modal_set('CROSSHAIR')
            self._update_status_text(context)
            context.window_manager.modal_handler_add(self)
            return {'RUNNING_MODAL'}
        except Exception:
            self._cleanup(context)
            return {'CANCELLED'}

    def _update_status_text(self, context):
        s = _get_ring_settings(context)
        base_dir = {'BOTH': '双向', 'DIR_A': '方向A', 'DIR_B': '方向B'}[s.trace_dir]
        if s.trace_dir == 'DIR_A':
            dir_name = '方向B' if s.steps < 0 else '方向A'
        elif s.trace_dir == 'DIR_B':
            dir_name = '方向A' if s.steps < 0 else '方向B'
        else:
            dir_name = base_dir
        steps_text = '不限' if s.steps == 0 else str(s.steps)
        text = (
            f"悬浮预览并排边环 | 步数:{steps_text}(Shift滚轮) | "
            f"方向:{dir_name}(Tab) | S设置 | 左键确定 | Shift加选 Ctrl减选 | 右键取消"
        )
        try:
            context.workspace.status_text_set(text)
        except Exception:
            pass

    def modal(self, context, event):
        try:
            context.area.tag_redraw()

            if event.type == 'MOUSEMOVE':
                self._update_hover(context, event)

            elif event.type == 'S' and event.value == 'PRESS':
                # S 调用独立设置面板，确认后返回当前模态继续
                bpy.ops.better_experie.edge_ring_settings('INVOKE_DEFAULT')
                self._update_status_text(context)
                return {'RUNNING_MODAL'}

            elif event.type == 'TAB' and event.value == 'PRESS':
                # Tab 切换延伸方向
                s = _get_ring_settings(context)
                order = ['BOTH', 'DIR_A', 'DIR_B']
                s.trace_dir = order[(order.index(s.trace_dir) + 1) % len(order)]
                self._update_hover(context, event)
                self._update_status_text(context)
                return {'RUNNING_MODAL'}

            elif event.type in {'WHEELUPMOUSE', 'WHEELDOWNMOUSE'} and event.shift:
                # Shift 滚轮增加/减少扩选段数
                s = _get_ring_settings(context)
                if event.type == 'WHEELUPMOUSE':
                    s.steps = min(s.steps + 1, 10000)
                else:
                    s.steps = max(s.steps - 1, -10000)
                self._update_hover(context, event)
                self._update_status_text(context)
                return {'RUNNING_MODAL'}

            elif event.type == 'LEFTMOUSE' and event.value == 'PRESS':
                if self.target_edge_idx != -1:
                    self.select_mode = 'ADD' if event.shift else ('SUB' if event.ctrl else 'SET')
                    self.execute(context)
                    # 持续选取：不退出，等待 Esc/右键
                    return {'RUNNING_MODAL'}

            elif event.type in {'RIGHTMOUSE', 'ESC'}:
                self._cleanup(context)
                return {'CANCELLED'}

            # 放行视口导航事件（中键旋转、滚轮缩放、触控板等）
            if event.type in {
                'MIDDLEMOUSE', 'WHEELUPMOUSE', 'WHEELDOWNMOUSE',
                'TRACKPADPAN', 'TRACKPADZOOM', 'NDOF_MOTION',
                'INBETWEEN_MOUSEMOVE',
            }:
                return {'PASS_THROUGH'}

            return {'RUNNING_MODAL'}
        except Exception:
            traceback.print_exc()
            self._cleanup(context)
            return {'CANCELLED'}

    def execute(self, context):
        if self.target_edge_idx == -1:
            self.report({'WARNING'}, "请先在交互模式中点击目标边")
            return {'CANCELLED'}

        s = _get_ring_settings(context)

        obj = context.edit_object
        bm = bmesh.from_edit_mesh(obj.data)
        bm.edges.ensure_lookup_table()
        bm.faces.ensure_lookup_table()

        target_edge = bm.edges[self.target_edge_idx]
        chain = _expand_ring_from_edge(
            bm, target_edge, s.steps, s.parallel_factor,
            s.max_angle, s.stop_at_sharp, s.trace_dir)

        if self.select_mode == 'SET':
            bpy.ops.mesh.select_all(action='DESELECT')
        target_state = False if self.select_mode == 'SUB' else True
        for e in chain:
            e.select = target_state

        bmesh.update_edit_mesh(obj.data)
        # 选择已生效、网格已刷新，重建 BVH 使后续射线检测引用最新网格
        self._rebuild_bvhtree(context)
        return {'FINISHED'}

    def _rebuild_bvhtree(self, context):
        try:
            obj = context.edit_object
            if obj and obj.type == 'MESH':
                bm = bmesh.from_edit_mesh(obj.data)
                self.bvhtree = BVHTree.FromBMesh(bm)
        except Exception:
            traceback.print_exc()

    def _update_hover(self, context, event):
        obj = context.edit_object
        bm = bmesh.from_edit_mesh(obj.data)
        s = _get_ring_settings(context)

        coord = event.mouse_region_x, event.mouse_region_y
        region = context.region
        rv3d = context.region_data
        view_vector = view3d_utils.region_2d_to_vector_3d(region, rv3d, coord)
        ray_origin = view3d_utils.region_2d_to_origin_3d(region, rv3d, coord)

        matrix_inv = obj.matrix_world.inverted()
        loc, norm, face_idx, dist = self.bvhtree.ray_cast(
            matrix_inv @ ray_origin,
            (matrix_inv @ (ray_origin + view_vector) - (matrix_inv @ ray_origin)).normalized()
        )

        if loc is not None:
            bm.faces.ensure_lookup_table()
            hit_face = bm.faces[face_idx]
            if hit_face.hide:
                self.preview_coords = []
                self.target_edge_idx = -1
                return
            min_d, best_e = float('inf'), None
            for e in hit_face.edges:
                if e.hide:
                    continue
                d = _dist_to_edge(loc, e.verts[0].co, e.verts[1].co)
                if d < min_d:
                    min_d = d
                    best_e = e
            if best_e:
                self.target_edge_idx = best_e.index
                chain = _expand_ring_from_edge(
                    bm, best_e, s.steps, s.parallel_factor,
                    s.max_angle, s.stop_at_sharp, s.trace_dir)
                self.preview_coords = [(e.verts[0].co.copy(), e.verts[1].co.copy()) for e in chain]
            else:
                self.preview_coords = []
                self.target_edge_idx = -1
        else:
            self.preview_coords = []
            self.target_edge_idx = -1

    def _cleanup(self, context):
        try:
            if self._handle:
                bpy.types.SpaceView3D.draw_handler_remove(self._handle, 'WINDOW')
                self._handle = None
        except Exception:
            pass
        remove_modal_border(self)
        if context and context.window:
            context.window.cursor_modal_restore()
            context.workspace.status_text_set(None)


class BetterExperie_OT_EdgeRingSettings(bpy.types.Operator):
    """并排边环交互选取参数设置面板：编辑场景属性组，确认后进入模态"""
    bl_idname = "better_experie.edge_ring_settings"
    bl_label = "并排边环选取设置"
    bl_description = "设置并排边环交互选取参数"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        return (
            context.active_object is not None
            and context.active_object.type == 'MESH'
            and context.mode == 'EDIT_MESH'
        )

    def draw(self, context):
        s = _get_ring_settings(context)
        layout = self.layout
        col = layout.column(align=True)
        col.prop(s, "trace_dir", expand=True)
        col.prop(s, "steps")
        col.separator()
        col.prop(s, "max_angle", slider=True)
        col.prop(s, "parallel_factor", slider=True)
        col.separator()
        col.prop(s, "stop_at_sharp")

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=320)

    def execute(self, context):
        return {'FINISHED'}


classes = (
    BetterExperie_EdgeRingSettings,
    BetterExperie_OT_SelectEdgeRingGeo,
    BetterExperie_OT_EdgeRingSettings,
    BetterExperie_OT_SelectEdgeRingInteractive,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.better_experie_edge_ring_settings = bpy.props.PointerProperty(
        type=BetterExperie_EdgeRingSettings)


def unregister():
    if hasattr(bpy.types.Scene, "better_experie_edge_ring_settings"):
        del bpy.types.Scene.better_experie_edge_ring_settings
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
