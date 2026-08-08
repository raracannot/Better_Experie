# 空物体组边界框 HUD

import bpy
import gpu
import mathutils
import time

from ...utils import get_pref

last_click_time = 0.0

def is_double_click(diff=0.3):
    global last_click_time
    current_time = time.time()
    time_diff = current_time - last_click_time
    last_click_time = current_time
    return time_diff < diff


# 以原点为中心的 1x1x1 立方体顶点坐标
_cube_verts = [
    (-0.5, -0.5, -0.5), (0.5, -0.5, -0.5), (0.5, 0.5, -0.5), (-0.5, 0.5, -0.5),
    (-0.5, -0.5, 0.5), (0.5, -0.5, 0.5), (0.5, 0.5, 0.5), (-0.5, 0.5, 0.5)
]

_cube_edges = [
    (0, 1), (1, 2), (2, 3), (3, 0),
    (4, 5), (5, 6), (6, 7), (7, 4),
    (0, 4), (1, 5), (2, 6), (3, 7)
]

_line_verts = []
for edge in _cube_edges:
    _line_verts.append(_cube_verts[edge[0]])
    _line_verts.append(_cube_verts[edge[1]])

_custom_shape = bpy.types.Gizmo.new_custom_shape('LINES', _line_verts)


def get_children_local_bbox_matrix(empty_obj):
    min_vec = mathutils.Vector((float('inf'), float('inf'), float('inf')))
    max_vec = mathutils.Vector((float('-inf'), float('-inf'), float('-inf')))
    has_geometry = False

    try:
        inv_matrix = empty_obj.matrix_world.inverted()
    except ValueError:
        return None

    def process_obj(obj):
        nonlocal min_vec, max_vec, has_geometry
        if obj.type in {'MESH', 'CURVE', 'SURFACE', 'META', 'FONT'} and obj.bound_box:
            for corner in obj.bound_box:
                world_pt = obj.matrix_world @ mathutils.Vector(corner)
                local_pt = inv_matrix @ world_pt
                min_vec.x = min(min_vec.x, local_pt.x)
                min_vec.y = min(min_vec.y, local_pt.y)
                min_vec.z = min(min_vec.z, local_pt.z)
                max_vec.x = max(max_vec.x, local_pt.x)
                max_vec.y = max(max_vec.y, local_pt.y)
                max_vec.z = max(max_vec.z, local_pt.z)
                has_geometry = True
        else:
            world_pt = obj.matrix_world.translation
            local_pt = inv_matrix @ world_pt
            min_vec.x = min(min_vec.x, local_pt.x)
            min_vec.y = min(min_vec.y, local_pt.y)
            min_vec.z = min(min_vec.z, local_pt.z)
            max_vec.x = max(max_vec.x, local_pt.x)
            max_vec.y = max(max_vec.y, local_pt.y)
            max_vec.z = max(max_vec.z, local_pt.z)
            has_geometry = True
        for child in obj.children:
            process_obj(child)

    for child in empty_obj.children:
        process_obj(child)

    if not has_geometry:
        return None

    center = (min_vec + max_vec) / 2.0
    scale = max_vec - min_vec

    scale.x = max(scale.x, 0.001)
    scale.y = max(scale.y, 0.001)
    scale.z = max(scale.z, 0.001)

    S = mathutils.Matrix.Diagonal((scale.x, scale.y, scale.z, 1.0))
    T = mathutils.Matrix.Translation(center)

    return T @ S


class BetterExperie_OT_SelectEmptyGizmo(bpy.types.Operator):
    bl_idname = "better_experie.select_empty_gizmo"
    bl_label = "选择空物体 Gizmo"
    bl_description = "点击 Gizmo 时选中对应的空物体，Shift 追加，Ctrl 排除，双击递归选择子集"
    bl_options = {'INTERNAL', 'UNDO'}

    obj_name: bpy.props.StringProperty()

    def invoke(self, context, event):
        if event.type != 'LEFTMOUSE' or event.value != 'PRESS':
            return {'PASS_THROUGH'}

        obj = context.view_layer.objects.get(self.obj_name)
        if not obj or not obj.visible_get():
            return {'CANCELLED'}

        double_clicked = is_double_click()

        def apply_selection(target_obj, is_main_target=False):
            if event.ctrl:
                target_obj.select_set(False)
                if context.view_layer.objects.active == target_obj:
                    context.view_layer.objects.active = None
            else:
                target_obj.select_set(True)
                if is_main_target:
                    context.view_layer.objects.active = target_obj

        if not event.shift and not event.ctrl:
            bpy.ops.object.select_all(action='DESELECT')

        apply_selection(obj, is_main_target=True)

        if double_clicked:
            def process_children(parent_obj):
                for child in parent_obj.children:
                    if child.visible_get():
                        apply_selection(child, is_main_target=False)
                    process_children(child)
            process_children(obj)

        return {'FINISHED'}


class EMPTY_GZ_wireframe(bpy.types.Gizmo):
    bl_idname = "EMPTY_GZ_wireframe"

    __slots__ = (
        "empty_obj",
        "custom_shape",
    )

    def _get_bbox_matrix(self):
        if not self.empty_obj or not self.empty_obj.visible_get():
            return None
        bbox_matrix = get_children_local_bbox_matrix(self.empty_obj)
        if bbox_matrix is None:
            return None
        return self.empty_obj.matrix_world @ bbox_matrix

    def draw(self, context):
        try:
            matrix = self._get_bbox_matrix()
            if matrix is None:
                return
        except ReferenceError:
            return

        if self.is_highlight:
            gpu.state.line_width_set(3.0)
            gpu.state.blend_set('ALPHA')
            gpu.state.depth_test_set('NONE')
        else:
            gpu.state.line_width_set(1.5)
            gpu.state.blend_set('ALPHA')
            gpu.state.depth_test_set('LESS_EQUAL')

        self.draw_custom_shape(self.custom_shape, matrix=matrix)

        gpu.state.depth_test_set('NONE')
        gpu.state.blend_set('NONE')
        gpu.state.line_width_set(1.0)

    def draw_select(self, context, select_id):
        try:
            matrix = self._get_bbox_matrix()
            if matrix is None:
                return
        except ReferenceError:
            return

        gpu.state.line_width_set(3.0)
        self.draw_custom_shape(self.custom_shape, matrix=matrix, select_id=select_id)
        gpu.state.line_width_set(1.0)


class EMPTY_GGT_wireframe_group(bpy.types.GizmoGroup):
    bl_idname = "EMPTY_GGT_wireframe_group"
    bl_label = "空物体线框 HUD"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'WINDOW'
    bl_options = {'3D', 'PERSISTENT'}

    @classmethod
    def poll(cls, context):
        if context.space_data.type != 'VIEW_3D':
            return False
        try:
            prefs = get_pref()
        except (KeyError, AttributeError):
            return False
        return getattr(prefs, "show_empty_wireframe_hud", False)

    def setup(self, context):
        self.my_gizmos = []
        self.last_empty_names = set()

    def draw_prepare(self, context):
        current_empties = [
            obj for obj in context.view_layer.objects
            if obj.type == 'EMPTY'
            and obj.visible_get()
            and not obj.parent
            and len(obj.children) > 0
        ]
        current_empty_names = {obj.name for obj in current_empties}

        needs_rebuild = (self.last_empty_names != current_empty_names)

        if not needs_rebuild:
            for gz in self.my_gizmos:
                try:
                    _ = gz.empty_obj.name
                except ReferenceError:
                    needs_rebuild = True
                    break

        if needs_rebuild:
            for gz in self.my_gizmos:
                try:
                    self.gizmos.remove(gz)
                except ReferenceError:
                    pass
            self.my_gizmos.clear()

            for obj in current_empties:
                gz = self.gizmos.new(EMPTY_GZ_wireframe.bl_idname)
                gz.empty_obj = obj
                gz.custom_shape = _custom_shape

                gz.alpha = 1.0
                gz.color = (0.7, 0.8, 1.0)

                gz.alpha_highlight = 1.0
                gz.color_highlight = (1.0, 1.0, 1.0)

                props = gz.target_set_operator(BetterExperie_OT_SelectEmptyGizmo.bl_idname)
                props.obj_name = obj.name

                self.my_gizmos.append(gz)

            self.last_empty_names = current_empty_names

        for gz in self.my_gizmos:
            try:
                if gz.empty_obj:
                    gz.matrix_basis = gz.empty_obj.matrix_world
                    # 对象被选中时高亮显示为暖色
                    gz.color = (1.0, 1.0, 0.8) if gz.empty_obj.select_get() else (0.7, 0.8, 1.0)
            except ReferenceError:
                pass


def custom_draw_gizmo_menu(self, context):
    from ...utils import get_pref
    try:
        prefs = get_pref()
    except (KeyError, AttributeError):
        return
    self.layout.separator()
    self.layout.prop(prefs, "show_empty_wireframe_hud", text="空物体线框 HUD")


classes = (
    BetterExperie_OT_SelectEmptyGizmo,
    EMPTY_GZ_wireframe,
    EMPTY_GGT_wireframe_group,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.VIEW3D_PT_gizmo_display.append(custom_draw_gizmo_menu)


def unregister():
    bpy.types.VIEW3D_PT_gizmo_display.remove(custom_draw_gizmo_menu)
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
