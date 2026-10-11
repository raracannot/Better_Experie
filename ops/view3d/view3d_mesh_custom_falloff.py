# 自定义比例衰减编辑：用原生曲线编辑器驱动网格 / 曲线编辑模式的衰减变形
# 参考自 绗缝贴图 0.6.1 by 61+ 的「衰减编辑自定义」实现
#
# 设计要点：
# - 不覆写核心面板，仅在原生比例编辑面板底部 append 一个启用/退出按钮区
# - G/R/S 常驻注册于 addon keymap，由算子 poll（读场景布尔）门控，未启用时落回原生
# - 启用状态为场景布尔，默认关闭，随 .blend 保存；退出时清理隐藏节点
# - 模态交互对齐原生：单轴/平面锁定、Shift 精度、中途切 G/R/S、状态栏提示、移动几何吸附

import math
import heapq
import json
import time
import traceback

import bpy
import bmesh
import gpu
from mathutils import Vector, Quaternion, Matrix
from mathutils.kdtree import KDTree
from bpy_extras import view3d_utils
from gpu_extras.batch import batch_for_shader
from bpy.props import BoolProperty, PointerProperty, StringProperty, EnumProperty, FloatProperty, FloatVectorProperty

from ...utils.rara_snapper import RaraSnapper
from ...utils.modal_border import add_modal_border, remove_modal_border
from ...utils.transform_orientation import slot_orientation, local_orientation

# 隐藏曲线控件使用的节点树 / 节点名
_TREE_NAME = 'Custom Falloff Editor'
_NODE_NAME = 'Custom Falloff'

# 模态行为常量
_PRECISION = 0.1          # Shift 精度倍率
_SNAP_RADIUS = 25.0       # 吸附像素半径
_RADIUS_FADE = 0.8        # 半径圆环淡出时长（秒）
_RADIUS_TICK = 0.02       # 淡出刷新间隔（秒）
_KIND_KEYS = {'G': 'MOVE', 'R': 'ROTATE', 'S': 'SCALE'}
_KIND_LABELS = {'MOVE': '移动', 'ROTATE': '旋转', 'SCALE': '缩放'}
# 仅在这些模式下支持（自定义衰减变形算子）
_SUPPORTED_MODES = {'EDIT_MESH', 'EDIT_CURVE'}
_STATUS_HINT = ("移动 / 旋转 / 缩放  |  X/Y/Z 锁定  |  Shift+轴 平面  |  双击同轴 切局部  |  "
                "Ctrl/捕捉开关 吸附  |  Shift 精度  |  滚轮 半径  |  G/R/S 切换  |  左键/回车 确认 · 右键/ESC 取消")

# addon keymap 中常驻注册的 G/R/S（由 poll 门控）
_keymaps = []

# 轴颜色（用于 gizmo）
_AXIS_COLORS = {'X': (1.0, 0.25, 0.25), 'Y': (0.3, 1.0, 0.3), 'Z': (0.35, 0.5, 1.0)}


def _plane_basis(axis):
    """给定平面法线，返回平面内正交基 (b1, b2)"""
    up = Vector((0.0, 0.0, 1.0))
    if abs(axis.dot(up)) > 0.99:
        up = Vector((0.0, 1.0, 0.0))
    b1 = axis.cross(up).normalized()
    b2 = axis.cross(b1).normalized()
    return b1, b2


class CurvePoint:
    """曲线对象上的一个可参与衰减变形的点（控制点 / 手柄）"""

    def __init__(self, point, attribute, selected):
        self.point = point
        self.attribute = attribute
        self.select = selected

    @property
    def co(self):
        return Vector(getattr(self.point, self.attribute)[:3])

    @co.setter
    def co(self, value):
        original = getattr(self.point, self.attribute)
        setattr(self.point, self.attribute, (*value, original[3]) if len(original) == 4 else value)


def update_geometry(obj):
    if obj.type == 'MESH':
        mesh = bmesh.from_edit_mesh(obj.data)
        mesh.normal_update()
        bmesh.update_edit_mesh(obj.data, loop_triangles=False, destructive=False)
    else:
        obj.data.update_tag()


def curve_node(scene):
    """按需返回隐藏的曲线控件节点（启用时才构建）"""
    tree = getattr(scene, 'better_experie_custom_falloff_tree', None)
    if not tree:
        tree = bpy.data.node_groups.new(_TREE_NAME, 'ShaderNodeTree')
        scene.better_experie_custom_falloff_tree = tree
    node = tree.nodes.get(_NODE_NAME)
    if not node:
        node = tree.nodes.new('ShaderNodeFloatCurve')
        node.name = _NODE_NAME
        node.mapping.initialize()
        for point in node.mapping.curves[0].points:
            point.select = False
        node.mapping.update()
    return node


def existing_curve_node(scene):
    tree = getattr(scene, 'better_experie_custom_falloff_tree', None)
    return tree.nodes.get(_NODE_NAME) if tree else None


def _cleanup_scene(scene):
    """清除场景指针并移除隐藏节点（仅在退出启用 / 加载时调用）"""
    tree = getattr(scene, 'better_experie_custom_falloff_tree', None)
    if not tree:
        return
    try:
        scene.better_experie_custom_falloff_tree = None
    except Exception:
        pass
    try:
        if tree.users == 0:
            bpy.data.node_groups.remove(tree)
    except Exception:
        pass


def _redraw_view3d(context):
    try:
        for window in context.window_manager.windows:
            for area in window.screen.areas:
                if area.type == 'VIEW_3D':
                    area.tag_redraw()
    except Exception:
        pass


class BetterExperie_OT_EnableCustomFalloff(bpy.types.Operator):
    bl_idname = 'better_experie.enable_custom_falloff'
    bl_label = '启用自定义衰减'
    bl_description = '启用曲线驱动的比例衰减并接管编辑模式 G/R/S；为本场景构建隐藏曲线节点'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return not getattr(context.scene, 'better_experie_custom_falloff_active', False)

    def execute(self, context):
        scene = context.scene
        scene.better_experie_custom_falloff_active = True
        if curve_node(scene) is None:
            scene.better_experie_custom_falloff_active = False
            self.report({'WARNING'}, '启用自定义衰减失败')
            return {'CANCELLED'}
        try:
            if context.mode == 'OBJECT':
                context.tool_settings.use_proportional_edit_objects = True
            else:
                context.tool_settings.use_proportional_edit = True
        except Exception:
            pass
        self.report({'INFO'}, '已启用自定义衰减')
        _redraw_view3d(context)
        return {'FINISHED'}


class BetterExperie_OT_DisableCustomFalloff(bpy.types.Operator):
    bl_idname = 'better_experie.disable_custom_falloff'
    bl_label = '退出自定义衰减'
    bl_description = '退出自定义衰减并清理本场景的隐藏曲线节点'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return getattr(context.scene, 'better_experie_custom_falloff_active', False)

    def execute(self, context):
        context.scene.better_experie_custom_falloff_active = False
        _cleanup_scene(context.scene)
        _redraw_view3d(context)
        return {'FINISHED'}


def custom_falloff_draw(self, context):
    """追加到原生比例编辑面板底部：启用 / 退出自定义衰减 + 曲线控件

    仅在算子支持的模式（网格 / 曲线编辑）下绘制，避免在其它模式造成误导。
    """
    if context.mode not in _SUPPORTED_MODES:
        return
    layout = self.layout
    scene = context.scene
    layout.separator()
    active = getattr(scene, 'better_experie_custom_falloff_active', False)
    if active:
        layout.operator(BetterExperie_OT_DisableCustomFalloff.bl_idname, text='退出自定义衰减', icon='CANCEL', depress=True)
        layout.label(text='原生衰减将被忽略')
        node = existing_curve_node(scene)
        if node:
            layout.template_curve_mapping(node, 'mapping', type='NONE')
    else:
        layout.operator(BetterExperie_OT_EnableCustomFalloff.bl_idname,
                        text='启用自定义衰减', icon='FCURVE')


class BetterExperie_OT_CustomProportional(bpy.types.Operator):
    bl_idname = 'better_experie.custom_proportional'
    bl_label = '自定义衰减变形'
    bl_description = '按自定义曲线进行网格顶点衰减变形'
    bl_options = {'REGISTER', 'UNDO', 'BLOCKING'}

    kind: EnumProperty(items=(('MOVE', '移动', ''), ('ROTATE', '旋转', ''), ('SCALE', '缩放', '')))
    translation: FloatVectorProperty(name='移动', subtype='TRANSLATION', size=3)
    angle: FloatProperty(name='角度', subtype='ANGLE')
    factor: FloatProperty(name='缩放', default=1)
    radius: FloatProperty(name='衰减编辑区大小', default=1, min=1e-6, subtype='DISTANCE')
    connected: BoolProperty(name='相连项')
    projected: BoolProperty(name='投射式 (2D)')
    constraint: EnumProperty(name='轴向', items=(
        ('NONE', '视图 / 全部', ''),
        ('X', 'X', ''), ('Y', 'Y', ''), ('Z', 'Z', ''),
        ('PLANE_X', '平面 X', ''), ('PLANE_Y', '平面 Y', ''), ('PLANE_Z', '平面 Z', ''),
    ))
    local: BoolProperty(name='局部坐标')
    rotation_axis: FloatVectorProperty(size=3, default=(0, 0, 1), options={'HIDDEN'})
    selection_snapshot: StringProperty(options={'HIDDEN'})

    @classmethod
    def poll(cls, context):
        return (context.area is not None and context.area.type == 'VIEW_3D' and context.mode in _SUPPORTED_MODES
                and getattr(context.scene, 'better_experie_custom_falloff_active', False)
                and context.tool_settings.use_proportional_edit)

    # ── 生命周期 ──────────────────────────────────────────────
    def invoke(self, context, event):
        self._modal_border_handle = None
        self._guide_handle = None
        try:
            self.selection_snapshot = ''
            self.radius = max(context.tool_settings.proportional_size, 1e-6)
            self.connected = context.tool_settings.use_proportional_connected
            self.projected = context.tool_settings.use_proportional_projected
            self.capture(context)
            if not any(self.selected):
                return {'CANCELLED'}
            self.start = Vector((event.mouse_region_x, event.mouse_region_y))
            self.mouse = self.start.copy()
            self.axis_name = None
            self.plane = False
            self.local = False
            self.numeric = ''
            self.constraint = 'NONE'
            self.precision = bool(event.shift)
            self._snap_active = bool(event.ctrl) or bool(getattr(context.tool_settings, 'use_snap', False))
            self._snap_tag = 'NONE'
            self.snapper = None
            self._snap_built = False
            self._radius_alpha = 0.0
            self._radius_deadline = 0.0
            self._radius_timer = None
            self.orient = slot_orientation(context, view=getattr(self, 'view', None))
            self.snap_source = self._compute_snap_source()
            add_modal_border(self, context)
            self._guide_handle = bpy.types.SpaceView3D.draw_handler_add(
                BetterExperie_OT_CustomProportional._draw_guide, (self,), 'WINDOW', 'POST_VIEW')
            context.window_manager.modal_handler_add(self)
            self._status(context)
            self.apply(context, None)
            return {'RUNNING_MODAL'}
        except Exception as error:
            try:
                self._end(context)
            except Exception:
                pass
            self.report({'WARNING'}, str(error))
            return {'CANCELLED'}

    def execute(self, context):
        try:
            self.capture(context)
            if not any(self.selected):
                return {'CANCELLED'}
            self._sync_constraint_from_prop()
            self.precision = False
            self._snap_active = False
            self._snap_tag = 'NONE'
            self.orient = slot_orientation(context, view=getattr(self, 'view', None))
            value = Vector(self.translation) if self.kind == 'MOVE' else self.angle if self.kind == 'ROTATE' else self.factor
            axis = Vector(self.rotation_axis).normalized() if self.kind == 'ROTATE' else self.axis()
            if self.kind == 'ROTATE' and self.axis_name:
                axis = self.axis()
            self.write_transform(value, axis)
            context.tool_settings.proportional_size = self.radius
            context.tool_settings.use_proportional_connected = self.connected
            context.tool_settings.use_proportional_projected = self.projected
            return {'FINISHED'}
        except (ReferenceError, RuntimeError) as error:
            self.report({'WARNING'}, str(error))
            return {'CANCELLED'}

    # ── 捕获 / 解析 ──────────────────────────────────────────
    def capture(self, context):
        saved_selection = json.loads(self.selection_snapshot) if getattr(self, 'selection_snapshot', '') else None
        saved_selection = set(tuple(item) for item in saved_selection) if saved_selection is not None else None
        self.region = context.region
        self.view = context.region_data
        if self.view is None:
            self.region = next((r for r in context.area.regions if r.type == 'WINDOW'), self.region)
            self.view = context.area.spaces.active.region_3d
        self.records = []
        self.selected = []
        self.point_refs = []
        self.topology = {}
        # 节点创建可能重建编辑数据，需在捕获几何前完成
        node = curve_node(context.scene)
        if node is None:
            raise RuntimeError('自定义衰减未启用')
        self.mapping = node.mapping
        for obj in context.objects_in_mode_unique_data:
            if obj.type == 'MESH':
                mesh = bmesh.from_edit_mesh(obj.data)
                mesh.verts.ensure_lookup_table()
                mesh.verts.index_update()
                self.topology[obj] = (obj.data.as_pointer(), len(mesh.verts), len(mesh.edges), len(mesh.faces))
                vertices = [v for v in mesh.verts if not v.hide]
            elif obj.type == 'CURVE':
                vertices = []
                for spline in obj.data.splines:
                    for p in spline.bezier_points:
                        if p.hide:
                            continue
                        vertices.extend((CurvePoint(p, 'co', p.select_control_point),
                                         CurvePoint(p, 'handle_left', p.select_left_handle),
                                         CurvePoint(p, 'handle_right', p.select_right_handle)))
                    vertices.extend(CurvePoint(p, 'co', p.select) for p in spline.points if not p.hide)
            else:
                continue
            matrix = obj.matrix_world.copy()
            for index, vertex in enumerate(vertices):
                point = matrix @ vertex.co
                self.records.append((obj, vertex.index if obj.type == 'MESH' else vertex, vertex.co.copy(), point))
                identifier = vertex.index if obj.type == 'MESH' else index
                self.selected.append(vertex.select if saved_selection is None else (obj.name_full, identifier) in saved_selection)
                self.point_refs.append((obj, vertex.index if obj.type == 'MESH' else index))
        self.objs = {r[0] for r in self.records}
        chosen = [r[3] for r, s in zip(self.records, self.selected) if s]
        if not chosen:
            return
        if saved_selection is None:
            self.selection_snapshot = json.dumps([(obj.name_full, index) for (obj, index), selected
                                                  in zip(self.point_refs, self.selected) if selected])
        self.pivot = sum(chosen, Vector()) / len(chosen)
        if context.tool_settings.transform_pivot_point == 'CURSOR':
            self.pivot = context.scene.cursor.location.copy()
        self.distances = self.get_distances(context, chosen)
        self.area = context.area
        # 预计算：逆矩阵 / 轴心局部坐标 / 世界偏移 / 活动子集（性能优化）
        self.inv_full = {}
        self.inv3 = {}
        self.pivot_local = {}
        for obj in self.objs:
            inv = obj.matrix_world.inverted_safe()
            self.inv_full[obj] = inv
            self.inv3[obj] = inv.to_3x3()
            self.pivot_local[obj] = inv @ self.pivot
        self.offsets = [r[3] - self.pivot for r in self.records]
        self.selected_idx = [i for i, s in enumerate(self.selected) if s]
        self.unsel_order = sorted((i for i in range(len(self.records)) if not self.selected[i]),
                                  key=lambda i: self.distances[i])
        self._weights = []
        self._weights_radius = None

    def _meshes(self):
        """按物体取编辑 BMesh 并校验拓扑（每帧 O(物体数)）"""
        meshes = {}
        for obj in self.objs:
            if obj.type != 'MESH':
                continue
            if obj.mode != 'EDIT':
                raise RuntimeError('编辑模式已改变，已停止自定义变形')
            bm = bmesh.from_edit_mesh(obj.data)
            expected = self.topology.get(obj)
            if expected is not None:
                actual = (obj.data.as_pointer(), len(bm.verts), len(bm.edges), len(bm.faces))
                if actual != expected:
                    raise RuntimeError('网格拓扑已改变，已停止自定义变形')
            bm.verts.ensure_lookup_table()
            meshes[obj] = bm
        self.edit_meshes = meshes
        return meshes

    def restore(self):
        meshes = self._meshes()
        for obj, key, original, _ in self.records:
            if obj.type == 'MESH':
                meshes[obj].verts[key].co = original
            else:
                key.co = original
        for obj in meshes:
            update_geometry(obj)

    # ── 距离 / 权重 ──────────────────────────────────────────
    def get_distances(self, context, chosen):
        projected = self.projected and not self.connected

        def space(point):
            if not projected:
                return point
            pixel = view3d_utils.location_3d_to_region_2d(self.region, self.view, point)
            return Vector((pixel.x, pixel.y, 0)) if pixel is not None else Vector((1e12, 1e12, 0))

        tree = KDTree(len(chosen))
        for index, point in enumerate(chosen):
            tree.insert(space(point), index)
        tree.balance()
        distances = [tree.find(space(record[3]))[2] for record in self.records]
        if projected:
            p = space(self.pivot)
            right = self.view.view_rotation @ Vector((1, 0, 0))
            pixel_scale = (space(self.pivot + right) - p).length
            distances = [d / max(pixel_scale, 1e-6) for d in distances]
        if self.connected and context.mode == 'EDIT_MESH':
            meshes = self._meshes()
            lookup = {ref: index for index, ref in enumerate(self.point_refs)}
            distances = [0.0 if s else math.inf for s in self.selected]
            queue = [(0.0, i) for i, s in enumerate(self.selected) if s]
            heapq.heapify(queue)
            while queue:
                distance, index = heapq.heappop(queue)
                if distance != distances[index]:
                    continue
                obj, key, _, point = self.records[index]
                if obj.type != 'MESH':
                    continue
                vertex = meshes[obj].verts[key]
                for edge in vertex.link_edges:
                    other = edge.other_vert(vertex)
                    neighbor = lookup.get((obj, other.index))
                    if neighbor is None:
                        continue
                    candidate = distance + (self.records[neighbor][3] - point).length
                    if candidate < distances[neighbor]:
                        distances[neighbor] = candidate
                        heapq.heappush(queue, (candidate, neighbor))
        return distances

    def _build_weights(self):
        """仅在半径变化时重算受影响顶点权重（含选中权重=1，其余按曲线、仅半径内）"""
        radius = self.radius
        curve = self.mapping.curves[0]
        pairs = [(i, 1.0) for i in self.selected_idx]
        for i in self.unsel_order:
            distance = self.distances[i]
            if distance >= radius:
                break
            weight = self.mapping.evaluate(curve, 1 - distance / radius)
            if weight > 0.0:
                pairs.append((i, weight))
        self._weights = pairs
        self._weights_radius = radius

    # ── 约束 / 朝向 ──────────────────────────────────────────
    def _constraint_id(self):
        if not self.axis_name:
            return 'NONE'
        return ('PLANE_' if self.plane else '') + self.axis_name

    def _sync_constraint_from_prop(self):
        value = self.constraint
        if value and value.startswith('PLANE_'):
            self.plane = True
            self.axis_name = value[6:]
        elif value in ('X', 'Y', 'Z'):
            self.plane = False
            self.axis_name = value
        else:
            self.plane = False
            self.axis_name = None

    def axis(self):
        if not self.axis_name:
            return None
        basis = Vector(tuple(1 if name == self.axis_name else 0 for name in ('X', 'Y', 'Z')))
        if self.local:
            matrix = local_orientation(self.records[0][0] if self.records else None)
        else:
            matrix = getattr(self, 'orient', None) or Matrix.Identity(3)
        return (matrix @ basis).normalized()

    def _constrain_vector(self, vector, axis):
        if axis is None:
            return vector
        along = axis * vector.dot(axis)
        return (vector - along) if self.plane else along

    # ── 吸附 ────────────────────────────────────────────────
    def _compute_snap_source(self):
        best = None
        best_distance = None
        for (obj, key, original, point), selected in zip(self.records, self.selected):
            if not selected:
                continue
            pixel = view3d_utils.location_3d_to_region_2d(self.region, self.view, point)
            if pixel is None:
                continue
            distance = (pixel - self.start).length
            if best_distance is None or distance < best_distance:
                best_distance = distance
                best = point
        return best

    def _snap_target(self, context, event):
        if not self._snap_active or event is None or self.snap_source is None:
            return None
        if self.snapper is None:
            try:
                self.snapper = RaraSnapper()
            except Exception:
                self._snap_active = False
                return None
        if not self._snap_built:
            try:
                self.snapper.build_cache(context, scope='ALL', include_non_mesh=True)
            except Exception:
                pass
            self._snap_built = True
        try:
            target, tag = self.snapper.find_nearest(
                context, event, radius=_SNAP_RADIUS,
                snap_vertex=True, snap_half=True, snap_third=False,
                snap_edge=True, snap_face=True, penetrate=False)
        except Exception:
            return None
        if target is None or tag == 'NONE':
            return None
        self._snap_tag = tag
        return target

    # ── 应用 ────────────────────────────────────────────────
    def apply(self, context, event=None):
        axis = self.axis()
        number = None
        if self.numeric:
            try:
                number = float(self.numeric)
            except ValueError:
                number = None
        if self.kind == 'MOVE':
            start = view3d_utils.region_2d_to_location_3d(self.region, self.view, self.start, self.pivot)
            end = view3d_utils.region_2d_to_location_3d(self.region, self.view, self.mouse, self.pivot)
            value = end - start
            if number is not None:
                value = (axis or (self.view.view_rotation @ Vector((1, 0, 0)))) * number
            else:
                if self.precision:
                    value = value * _PRECISION
                self._snap_tag = 'NONE'
                target = self._snap_target(context, event)
                if target is not None:
                    value = target - self.snap_source
                value = self._constrain_vector(value, axis)
        elif self.kind == 'SCALE':
            center = view3d_utils.location_3d_to_region_2d(self.region, self.view, self.pivot)
            value = (self.mouse - center).length / max((self.start - center).length, 1) if center else 1
            if number is not None:
                value = number
            elif self.precision:
                value = 1 + (value - 1) * _PRECISION
        else:
            center = view3d_utils.location_3d_to_region_2d(self.region, self.view, self.pivot)
            a = self.start - center if center else self.start
            b = self.mouse - center if center else self.mouse
            value = math.atan2(b.y, b.x) - math.atan2(a.y, a.x)
            if number is not None:
                value = math.radians(number)
            elif self.precision:
                value = value * _PRECISION
            axis = axis or (self.view.view_rotation @ Vector((0, 0, -1)))
        self.constraint = self._constraint_id()
        if self.kind == 'MOVE':
            self.translation = value
        elif self.kind == 'SCALE':
            self.factor = value
        else:
            self.angle = value
            self.rotation_axis = axis
        self.write_transform(value, axis)
        if self.area:
            precision = ' 精度' if self.precision and number is None else ''
            snap = f' 吸附:{self._snap_tag}' if self._snap_tag != 'NONE' else ''
            self.area.header_text_set(
                f'{_KIND_LABELS[self.kind]} · 半径 {self.radius:.4g} · {self.axis_name or "视图"}{precision}{snap} {self.numeric}')
            self.area.tag_redraw()

    def write_transform(self, value, axis):
        if self._weights_radius != self.radius:
            self._build_weights()
        meshes = self._meshes()
        records = self.records
        inv3 = self.inv3
        touched = set()
        if self.kind == 'MOVE':
            local_delta = {obj: inv3[obj] @ value for obj in inv3}
            for index, weight in self._weights:
                obj, key, original, _ = records[index]
                local = original + local_delta[obj] * weight
                if obj.type == 'MESH':
                    meshes[obj].verts[key].co = local
                else:
                    key.co = local
                touched.add(obj)
        elif self.kind == 'SCALE':
            for index, weight in self._weights:
                obj, key, _, _ = records[index]
                offset = self.offsets[index]
                if axis is None:
                    local = self.pivot_local[obj] + inv3[obj] @ (offset * (1 + (value - 1) * weight))
                elif not self.plane:
                    local = self.pivot_local[obj] + inv3[obj] @ (offset + axis * offset.dot(axis) * ((value - 1) * weight))
                else:
                    along = axis * offset.dot(axis)
                    local = self.pivot_local[obj] + inv3[obj] @ (along + (offset - along) * (1 + (value - 1) * weight))
                if obj.type == 'MESH':
                    meshes[obj].verts[key].co = local
                else:
                    key.co = local
                touched.add(obj)
        else:
            for index, weight in self._weights:
                obj, key, _, _ = records[index]
                rotation = Quaternion(axis, value * weight)
                local = self.pivot_local[obj] + inv3[obj] @ (rotation @ self.offsets[index])
                if obj.type == 'MESH':
                    meshes[obj].verts[key].co = local
                else:
                    key.co = local
                touched.add(obj)
        for obj in touched:
            update_geometry(obj)
        if self.area:
            self.area.tag_redraw()

    # ── 模态 ────────────────────────────────────────────────
    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        layout.prop(self, 'translation' if self.kind == 'MOVE' else 'angle' if self.kind == 'ROTATE' else 'factor')
        if self.kind != 'MOVE':
            layout.prop(self, 'constraint')
            layout.prop(self, 'local')
        layout.prop(self, 'radius')
        layout.prop(self, 'connected')
        row = layout.row()
        row.enabled = not self.connected
        row.prop(self, 'projected')
        node = existing_curve_node(context.scene)
        if node:
            layout.template_curve_mapping(node, 'mapping', type='NONE')

    def _status(self, context):
        try:
            context.workspace.status_text_set(_STATUS_HINT)
        except Exception:
            pass

    def _bump_radius_display(self, context):
        """半径变化时短暂显示圆环，并确保淡出计时器在运行"""
        self._radius_alpha = 1.0
        self._radius_deadline = time.time() + _RADIUS_FADE
        if self._radius_timer is None:
            try:
                self._radius_timer = context.window_manager.event_timer_add(_RADIUS_TICK, window=context.window)
            except Exception:
                self._radius_timer = None

    def _stop_radius_timer(self, context):
        if getattr(self, '_radius_timer', None):
            try:
                context.window_manager.event_timer_remove(self._radius_timer)
            except Exception:
                pass
            self._radius_timer = None

    @staticmethod
    def _draw_guide(owner):
        """POST_VIEW：绘制比例半径圆环 + 轴向/平面指示 gizmo"""
        try:
            region = getattr(owner, 'region', None)
            rv = getattr(owner, 'view', None)
            if region is None or rv is None:
                return
            pivot = owner.pivot
            radius = owner.radius
            right = rv.view_rotation @ Vector((1.0, 0.0, 0.0))
            up = rv.view_rotation @ Vector((0.0, 1.0, 0.0))
            shader = gpu.shader.from_builtin('UNIFORM_COLOR')
            gpu.state.blend_set('ALPHA')
            gpu.state.depth_test_set('NONE')
            shader.bind()
            # 半径圆环：仅半径变化时短暂显示并淡出
            alpha = getattr(owner, '_radius_alpha', 0.0)
            if alpha > 0.0:
                steps = 64
                ring = [tuple(pivot + (right * math.cos(a) + up * math.sin(a)) * radius)
                        for a in (i * 2.0 * math.pi / steps for i in range(steps + 1))]
                gpu.state.line_width_set(1.0 + 2.0 * alpha)
                ring_batch = batch_for_shader(shader, 'LINE_STRIP', {"pos": ring})
                shader.uniform_float("color", (1.0, 1.0, 1.0, 0.9 * alpha))
                ring_batch.draw(shader)
            # 轴向 / 平面指示
            axis_name = getattr(owner, 'axis_name', None)
            if axis_name:
                axis = owner.axis()
                if axis is not None:
                    color = _AXIS_COLORS.get(axis_name, (1.0, 1.0, 1.0))
                    gpu.state.line_width_set(2.0)
                    if getattr(owner, 'plane', False):
                        b1, b2 = _plane_basis(axis)
                        corners = [tuple(pivot + (b1 + b2) * radius), tuple(pivot + (b1 - b2) * radius),
                                   tuple(pivot + (-b1 - b2) * radius), tuple(pivot + (-b1 + b2) * radius),
                                   tuple(pivot + (b1 + b2) * radius)]
                        plane_batch = batch_for_shader(shader, 'LINE_STRIP', {"pos": corners})
                        shader.uniform_float("color", (color[0], color[1], color[2], 0.9))
                        plane_batch.draw(shader)
                    else:
                        length = max(radius, 1e-6) * 3.0
                        line_batch = batch_for_shader(shader, 'LINES', {
                            "pos": [tuple(pivot - axis * length), tuple(pivot + axis * length)]})
                        shader.uniform_float("color", (color[0], color[1], color[2], 0.9))
                        line_batch.draw(shader)
        except ReferenceError:
            pass
        except Exception:
            traceback.print_exc()
        finally:
            gpu.state.blend_set('NONE')
            gpu.state.depth_test_set('LESS_EQUAL')
            gpu.state.line_width_set(1.0)
            gpu.state.point_size_set(1.0)

    def _end(self, context):
        if getattr(self, 'area', None):
            self.area.header_text_set(None)
        try:
            context.workspace.status_text_set(None)
        except Exception:
            pass
        handle = getattr(self, '_guide_handle', None)
        if handle:
            try:
                bpy.types.SpaceView3D.draw_handler_remove(handle, 'WINDOW')
            except Exception:
                pass
            self._guide_handle = None
        self._stop_radius_timer(context)
        remove_modal_border(self)
        self.snapper = None

    def modal(self, context, event):
        try:
            return self.modal_event(context, event)
        except Exception as error:
            try:
                self.restore()
            except Exception:
                pass
            self._end(context)
            self.report({'WARNING'}, str(error))
            return {'CANCELLED'}

    def modal_event(self, context, event):
        self.precision = bool(event.shift)
        self._snap_active = bool(event.ctrl) or bool(getattr(context.tool_settings, 'use_snap', False))
        if event.type == 'TIMER':
            if self._radius_timer is None:
                return {'RUNNING_MODAL'}
            remaining = self._radius_deadline - time.time()
            if remaining <= 0.0:
                self._radius_alpha = 0.0
                self._stop_radius_timer(context)
            else:
                self._radius_alpha = remaining / _RADIUS_FADE
            if self.area:
                self.area.tag_redraw()
            return {'RUNNING_MODAL'}
        if event.type in {'ESC', 'RIGHTMOUSE'}:
            self.restore()
            self._end(context)
            return {'CANCELLED'}
        if event.type in {'LEFTMOUSE', 'RET', 'NUMPAD_ENTER'} and event.value == 'PRESS':
            self._meshes()
            self._end(context)
            return {'FINISHED'}
        changed = False
        if event.type == 'MOUSEMOVE':
            self.mouse = Vector((event.mouse_region_x, event.mouse_region_y))
            changed = True
        elif event.type in {'WHEELUPMOUSE', 'WHEELDOWNMOUSE'}:
            self.radius = max(1e-6, self.radius * (1.1 if event.type == 'WHEELUPMOUSE' else 1 / 1.1))
            context.tool_settings.proportional_size = self.radius
            self._bump_radius_display(context)
            changed = True
        elif event.value == 'PRESS':
            if event.type in _KIND_KEYS and not event.ctrl and not event.alt:
                new_kind = _KIND_KEYS[event.type]
                if new_kind != self.kind:
                    self.kind = new_kind
                    self.numeric = ''
                    self._status(context)
                    changed = True
            elif event.type in {'X', 'Y', 'Z'}:
                if event.shift:
                    self.plane = True
                    self.axis_name = event.type
                elif self.axis_name == event.type:
                    if self.plane:
                        self.plane = False
                    else:
                        self.local = not self.local
                else:
                    self.plane = False
                    self.axis_name = event.type
                changed = True
            elif event.type == 'BACK_SPACE':
                self.numeric = self.numeric[:-1]
                changed = True
            elif event.ascii and event.ascii in '0123456789.-':
                self.numeric += event.ascii
                changed = True
        if changed:
            self.apply(context, event)
        return {'RUNNING_MODAL'}


classes = (
    BetterExperie_OT_EnableCustomFalloff,
    BetterExperie_OT_DisableCustomFalloff,
    BetterExperie_OT_CustomProportional,
)


# ============================== 注册辅助 ==============================

def _append_panel():
    try:
        bpy.types.VIEW3D_PT_proportional_edit.append(custom_falloff_draw)
    except Exception:
        pass


def _remove_panel():
    try:
        bpy.types.VIEW3D_PT_proportional_edit.remove(custom_falloff_draw)
    except Exception:
        pass


def _register_keymaps():
    """常驻注册 G/R/S 到 addon keymap；未启用时由 poll 落回原生"""
    if _keymaps:
        return
    kc = bpy.context.window_manager.keyconfigs.addon
    if not kc:
        return
    for name in ('Mesh', 'Curve'):
        km = kc.keymaps.get(name)
        if not km:
            km = kc.keymaps.new(name=name, space_type='EMPTY')
        for key, kind in (('G', 'MOVE'), ('R', 'ROTATE'), ('S', 'SCALE')):
            try:
                item = km.keymap_items.new(BetterExperie_OT_CustomProportional.bl_idname, key, 'PRESS')
                item.properties.kind = kind
                _keymaps.append((km, item))
            except Exception as error:
                print(f'[custom_falloff] 注册快捷键 {key} 失败: {error}')


def _unregister_keymaps():
    for km, item in _keymaps:
        try:
            km.keymap_items.remove(item)
        except Exception:
            pass
    _keymaps.clear()


def register():
    for cls in classes:
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.better_experie_custom_falloff_active = BoolProperty(default=False)
    bpy.types.Scene.better_experie_custom_falloff_tree = PointerProperty(type=bpy.types.NodeTree)
    _append_panel()
    _register_keymaps()


def unregister():
    _remove_panel()
    _unregister_keymaps()
    try:
        del bpy.types.Scene.better_experie_custom_falloff_active
    except Exception:
        pass
    try:
        del bpy.types.Scene.better_experie_custom_falloff_tree
    except Exception:
        pass
    for cls in reversed(classes):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass
