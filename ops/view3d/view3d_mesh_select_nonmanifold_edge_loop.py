# 非流形循环边选择：两个入口 — 批处理（先选边后点）与交互式模态（GPU HUD 预览）

import bpy
import bmesh
import math
import gpu
import traceback
from gpu_extras.batch import batch_for_shader
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from bpy_extras import view3d_utils
from ...utils.modal_border import add_modal_border, remove_modal_border


def _is_vertex_sharp(vertex):
    return any(not e.smooth for e in vertex.link_edges)


def _find_next_step(current_edge, vertex, max_angle_rad, jump_dist, visited_verts):
    v_co = vertex.co
    other_v = current_edge.other_vert(vertex)
    in_vec = (v_co - other_v.co).normalized()
    candidates = []
    dot_threshold = math.cos(max_angle_rad)

    for e in vertex.link_edges:
        if e == current_edge or e.hide:
            continue
        nv = e.other_vert(vertex)
        dot = in_vec.dot((nv.co - v_co).normalized())
        if dot > dot_threshold:
            is_closing = 1 if nv in visited_verts else 0
            candidates.append((is_closing, 0, dot, e, nv))

    if jump_dist > 0:
        for e_link in vertex.link_edges:
            v_neighbor = e_link.other_vert(vertex)
            if (v_neighbor.co - v_co).length <= jump_dist:
                for e_next in v_neighbor.link_edges:
                    if e_next == e_link or e_next.hide:
                        continue
                    v_far = e_next.other_vert(v_neighbor)
                    dot = in_vec.dot((v_far.co - v_neighbor.co).normalized())
                    if dot > dot_threshold:
                        is_closing = 1 if v_far in visited_verts else 0
                        candidates.append((is_closing, 1, dot, e_next, v_far))

    if not candidates:
        return None, None
    candidates.sort(key=lambda x: (x[0], 1 - x[1], x[2]), reverse=True)
    return candidates[0][3], candidates[0][4]


def _trace_path(start_edge, max_angle, jump_dist, stop_at_sharp, steps, direction_mode):
    final_edges = {start_edge}
    visited_verts = {v for v in start_edge.verts}
    verts = list(start_edge.verts)
    v_a, v_b = verts[0], verts[1]
    limit = abs(steps)

    tasks = []
    if direction_mode == 'BOTH':
        tasks = [v_a, v_b]
    elif direction_mode == 'DIR_A':
        # 正数沿 A 端延伸；负数自动反向到 B 端
        tasks = [v_a if steps >= 0 else v_b]
    elif direction_mode == 'DIR_B':
        # 正数沿 B 端延伸；负数自动反向到 A 端
        tasks = [v_b if steps >= 0 else v_a]

    for start_v in tasks:
        curr_e, curr_v = start_edge, start_v
        step_count = 0
        while limit <= 0 or step_count < limit:
            if stop_at_sharp and _is_vertex_sharp(curr_v):
                break
            next_e, next_v = _find_next_step(curr_e, curr_v, max_angle, jump_dist, visited_verts)
            if not next_e or next_e in final_edges:
                break
            final_edges.add(next_e)
            visited_verts.add(next_v)
            curr_e, curr_v = next_e, next_v
            step_count += 1
            if len(final_edges) > 10000:
                break
    return final_edges


# ═══════════════════════════════════════════════════════════════
# 入口 A：批处理（先选边后点，纯 execute）
# ═══════════════════════════════════════════════════════════════

class BetterExperie_NonManifoldEdgeLoopSettings(bpy.types.PropertyGroup):
    """非流形循环边交互选取的参数设置（挂载到 Scene）"""
    max_angle: bpy.props.FloatProperty(
        name="最大转向角", default=math.radians(30.0),
        min=0.0, max=math.radians(90.0), unit='ROTATION')
    jump_threshold: bpy.props.FloatProperty(
        name="跳跃阈值", default=0.1, min=0.0, max=1.0)
    steps: bpy.props.IntProperty(
        name="延伸步数", description="向两端延伸的段数（绝对值），0为不设限，单边模式下负数为反向延伸",
        default=0, min=-10000, max=10000)
    trace_dir: bpy.props.EnumProperty(
        name="延伸方向",
        items=[
            ('BOTH', "双向", ""),
            ('DIR_A', "方向 A", ""),
            ('DIR_B', "方向 B", ""),
        ], default='BOTH')
    stop_at_sharp: bpy.props.BoolProperty(
        name="锐点处停止", description="如果顶点连接了锐边，则停止追踪", default=True)


def _get_loop_settings(context):
    return context.scene.better_experie_nonmanifold_edge_loop_settings


class BetterExperie_OT_SelectNonManifoldEdgeLoopBatch(bpy.types.Operator):
    bl_idname = "better_experie.select_nonmanifold_edge_loop_batch"
    bl_label = "选择非流形循环边（批处理）"
    bl_description = "从当前选中的边出发，沿循环（Loop）方向追溯选择非流形链（0步为不设限，单边负数反向）"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return (
            context.active_object is not None
            and context.active_object.type == 'MESH'
            and context.mode == 'EDIT_MESH'
        )

    max_angle: bpy.props.FloatProperty(
        name="最大转向角", default=math.radians(30.0),
        min=0.0, max=math.radians(90.0), unit='ROTATION')
    jump_threshold: bpy.props.FloatProperty(
        name="跳跃阈值", default=0.1, min=0.0, max=1.0)
    steps: bpy.props.IntProperty(
        name="延伸步数", description="向两端延伸的段数（绝对值），0为不设限，单边模式下负数为反向延伸",
        default=0, min=-10000, max=10000)
    trace_dir: bpy.props.EnumProperty(
        name="延伸方向",
        items=[
            ('BOTH', "双向", ""),
            ('DIR_A', "方向 A", ""),
            ('DIR_B', "方向 B", ""),
        ], default='BOTH')
    stop_at_sharp: bpy.props.BoolProperty(
        name="锐点处停止", default=True)

    def draw(self, context):
        layout = self.layout
        col = layout.column(align=True)
        col.prop(self, "trace_dir", expand=True)
        col.prop(self, "steps")
        col.separator()
        col.prop(self, "max_angle", slider=True)
        col.prop(self, "jump_threshold", slider=True)
        col.separator()
        col.prop(self, "stop_at_sharp")

    def execute(self, context):
        obj = context.edit_object
        bm = bmesh.from_edit_mesh(obj.data)
        bm.edges.ensure_lookup_table()

        start_edges = [e for e in bm.edges if e.select]
        if not start_edges:
            self.report({'WARNING'}, "请先选择至少一条边")
            return {'CANCELLED'}

        chain = set()
        for e in start_edges:
            chain.update(_trace_path(e, self.max_angle, self.jump_threshold,
                                     self.stop_at_sharp, self.steps, self.trace_dir))

        for e in chain:
            e.select = True

        bmesh.update_edit_mesh(obj.data)
        return {'FINISHED'}


# ═══════════════════════════════════════════════════════════════
# 入口 B：交互式模态（GPU HUD 预览 + 点击选取）
# ═══════════════════════════════════════════════════════════════

def _draw_callback(self, context):
    try:
        if not self.preview_coords:
            return
        shader = gpu.shader.from_builtin('UNIFORM_COLOR')
        is_xray = False
        if context.space_data and hasattr(context.space_data.shading, 'show_xray'):
            is_xray = context.space_data.shading.show_xray
        try:
            gpu.state.line_width_set(3.0)
            if is_xray:
                gpu.state.depth_test_set('NONE')
            else:
                gpu.state.depth_test_set('LESS_EQUAL')
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


class BetterExperie_OT_SelectNonManifoldEdgeLoop(bpy.types.Operator):
    bl_idname = "better_experie.select_nonmanifold_edge_loop"
    bl_label = "选择非流形循环边（交互）"
    bl_description = "鼠标悬浮预览非流形循环边链，左键选中（Shift加选 Ctrl减选），Shift滚轮调边数，Tab切换方向，右键取消"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return (
            context.active_object is not None
            and context.active_object.type == 'MESH'
            and context.mode == 'EDIT_MESH'
        )

    max_angle: bpy.props.FloatProperty(
        name="最大转向角", default=math.radians(30.0),
        min=0.0, max=math.radians(90.0), unit='ROTATION')
    jump_threshold: bpy.props.FloatProperty(
        name="跳跃阈值", default=0.1, min=0.0, max=1.0)
    steps: bpy.props.IntProperty(
        name="延伸步数", description="向两端延伸的段数（绝对值），0为不设限，单边模式下负数为反向延伸",
        default=0, min=-10000, max=10000)
    trace_dir: bpy.props.EnumProperty(
        name="延伸方向",
        items=[
            ('BOTH', "双向", "向起始边的两个端点延伸"),
            ('DIR_A', "方向 A", "仅向端点 A 延伸"),
            ('DIR_B', "方向 B", "仅向端点 B 延伸"),
        ], default='BOTH')
    stop_at_sharp: bpy.props.BoolProperty(
        name="锐点处停止", description="如果顶点连接了锐边，则停止追踪", default=True)
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
        s = _get_loop_settings(context)
        layout = self.layout
        col = layout.column(align=True)
        col.prop(s, "trace_dir", expand=True)
        col.prop(s, "steps")
        col.separator()
        col.prop(s, "max_angle", slider=True)
        col.prop(s, "jump_threshold", slider=True)
        col.separator()
        col.prop(s, "stop_at_sharp")

    def invoke(self, context, event):
        try:
            if not self.poll(context):
                self.report({'WARNING'}, "请在3D视图的编辑模式下运行")
                return {'CANCELLED'}
            bm = bmesh.from_edit_mesh(context.edit_object.data)
            self.bvhtree = BVHTree.FromBMesh(bm)
            self._handle = bpy.types.SpaceView3D.draw_handler_add(
                _draw_callback, (self, context), 'WINDOW', 'POST_VIEW')
            add_modal_border(self, context)
            context.window.cursor_modal_set('CROSSHAIR')
            self._update_status_text(context)
            context.window_manager.modal_handler_add(self)
            return {'RUNNING_MODAL'}
        except Exception:
            self._cleanup(context)
            return {'CANCELLED'}

    def _update_status_text(self, context):
        s = _get_loop_settings(context)
        # 单边模式下负数表示反向延伸，方向名随符号翻转
        base_dir = {'BOTH': '双向', 'DIR_A': '方向A', 'DIR_B': '方向B'}[s.trace_dir]
        if s.trace_dir == 'DIR_A':
            dir_name = '方向B' if s.steps < 0 else '方向A'
        elif s.trace_dir == 'DIR_B':
            dir_name = '方向A' if s.steps < 0 else '方向B'
        else:
            dir_name = base_dir
        steps_text = '不限' if s.steps == 0 else str(s.steps)
        text = (
            f"悬浮预览非流形循环边链 | 边数:{steps_text}(Shift滚轮) | "
            f"方向:{dir_name}(Tab) | S设置 | 左键确定 | Shift加选 Ctrl减选 | 右键/ESC退出"
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
                bpy.ops.better_experie.nonmanifold_edge_loop_settings('INVOKE_DEFAULT')
                self._update_status_text(context)
                return {'RUNNING_MODAL'}

            elif event.type == 'TAB' and event.value == 'PRESS':
                # Tab 切换延伸方向
                s = _get_loop_settings(context)
                order = ['BOTH', 'DIR_A', 'DIR_B']
                s.trace_dir = order[(order.index(s.trace_dir) + 1) % len(order)]
                self._update_hover(context, event)
                self._update_status_text(context)
                return {'RUNNING_MODAL'}

            elif event.type in {'WHEELUPMOUSE', 'WHEELDOWNMOUSE'} and event.shift:
                # Shift 滚轮增加/减少延伸边数
                s = _get_loop_settings(context)
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

    def _update_hover(self, context, event):
        obj = context.edit_object
        bm = bmesh.from_edit_mesh(obj.data)
        s = _get_loop_settings(context)
        coord = event.mouse_region_x, event.mouse_region_y
        region, rv3d = context.region, context.region_data
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
                v1, v2 = e.verts[0].co, e.verts[1].co
                line_vec = v2 - v1
                l2 = line_vec.length_squared
                if l2 == 0:
                    continue
                t = max(0.0, min(1.0, (loc - v1).dot(line_vec) / l2))
                d = (loc - (v1 + t * line_vec)).length
                if d < min_d:
                    min_d = d
                    best_e = e
            if best_e:
                self.target_edge_idx = best_e.index
                final_edges = _trace_path(best_e, s.max_angle, s.jump_threshold,
                                          s.stop_at_sharp, s.steps, s.trace_dir)
                self.preview_coords = [(e.verts[0].co.copy(), e.verts[1].co.copy()) for e in final_edges]
            else:
                self.preview_coords = []
                self.target_edge_idx = -1
        else:
            self.preview_coords = []
            self.target_edge_idx = -1

    def execute(self, context):
        if self.target_edge_idx == -1:
            return {'FINISHED'}
        s = _get_loop_settings(context)
        obj = context.edit_object
        bm = bmesh.from_edit_mesh(obj.data)
        bm.edges.ensure_lookup_table()
        start_edge = bm.edges[self.target_edge_idx]
        final_edges = _trace_path(start_edge, s.max_angle, s.jump_threshold,
                                  s.stop_at_sharp, s.steps, s.trace_dir)
        if self.select_mode == 'SET':
            bpy.ops.mesh.select_all(action='DESELECT')
        target_state = False if self.select_mode == 'SUB' else True
        for e in final_edges:
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


class BetterExperie_OT_NonManifoldEdgeLoopSettings(bpy.types.Operator):
    """非流形循环边交互选取参数设置面板：编辑场景属性组，确认后进入模态"""
    bl_idname = "better_experie.nonmanifold_edge_loop_settings"
    bl_label = "循环边选取设置"
    bl_description = "设置非流形循环边交互选取参数"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        return (
            context.active_object is not None
            and context.active_object.type == 'MESH'
            and context.mode == 'EDIT_MESH'
        )

    def draw(self, context):
        s = _get_loop_settings(context)
        layout = self.layout
        col = layout.column(align=True)
        col.prop(s, "trace_dir", expand=True)
        col.prop(s, "steps")
        col.separator()
        col.prop(s, "max_angle", slider=True)
        col.prop(s, "jump_threshold", slider=True)
        col.separator()
        col.prop(s, "stop_at_sharp")

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=320)

    def execute(self, context):
        return {'FINISHED'}


classes = (
    BetterExperie_NonManifoldEdgeLoopSettings,
    BetterExperie_OT_SelectNonManifoldEdgeLoopBatch,
    BetterExperie_OT_NonManifoldEdgeLoopSettings,
    BetterExperie_OT_SelectNonManifoldEdgeLoop,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.better_experie_nonmanifold_edge_loop_settings = bpy.props.PointerProperty(
        type=BetterExperie_NonManifoldEdgeLoopSettings)


def unregister():
    if hasattr(bpy.types.Scene, "better_experie_nonmanifold_edge_loop_settings"):
        del bpy.types.Scene.better_experie_nonmanifold_edge_loop_settings
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
