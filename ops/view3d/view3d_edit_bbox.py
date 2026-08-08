# 网格边界框调整

import bpy
import bmesh
import mathutils

_global_bbox_sign_cache = {}

def get_orientation_matrix(context, obj):
    orient_type = context.scene.transform_orientation_slots[0].type

    if orient_type == 'GLOBAL':
        return mathutils.Matrix.Identity(3)
    elif orient_type == 'LOCAL':
        return obj.matrix_world.to_3x3()
    elif orient_type == 'CURSOR':
        return context.scene.cursor.matrix.to_3x3()
    elif orient_type == 'VIEW':
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                return area.spaces[0].region_3d.view_matrix.inverted().to_3x3()
        return mathutils.Matrix.Identity(3)
    elif orient_type == 'PARENT' and obj.parent:
        return obj.parent.matrix_world.to_3x3()

    return obj.matrix_world.to_3x3()


def get_pivot_point(context, obj, bm, sel_verts, min_v, max_v):
    pivot_type = context.scene.tool_settings.transform_pivot_point

    if pivot_type == 'CURSOR':
        return obj.matrix_world.inverted() @ context.scene.cursor.location
    elif pivot_type == 'MEDIAN_POINT':
        avg = mathutils.Vector((0.0, 0.0, 0.0))
        for v in sel_verts:
            avg += v.co
        return avg / len(sel_verts)
    elif pivot_type == 'ACTIVE_ELEMENT':
        active = bm.select_history.active
        if active and isinstance(active, bmesh.types.BMVert):
            return active.co
        elif active and isinstance(active, (bmesh.types.BMEdge, bmesh.types.BMFace)):
            return sum([v.co for v in active.verts], mathutils.Vector()) / len(active.verts)
    return (min_v + max_v) / 2.0


def get_edit_bbox_size(self):
    if self.mode != 'EDIT':
        return self.dimensions

    context = bpy.context
    bm = bmesh.from_edit_mesh(self.data)
    sel_verts = [v for v in bm.verts if v.select]

    if not sel_verts:
        return mathutils.Vector((0.0, 0.0, 0.0))

    orient_mat = get_orientation_matrix(context, self)
    orient_mat_inv = orient_mat.inverted()
    world_mat = self.matrix_world
    transformed_cos = [orient_mat_inv @ (world_mat @ v.co) for v in sel_verts]

    min_v = mathutils.Vector((
        min([co[0] for co in transformed_cos]),
        min([co[1] for co in transformed_cos]),
        min([co[2] for co in transformed_cos])))
    max_v = mathutils.Vector((
        max([co[0] for co in transformed_cos]),
        max([co[1] for co in transformed_cos]),
        max([co[2] for co in transformed_cos])))

    abs_size = max_v - min_v

    obj_id = self.as_pointer()
    cached_sign = _global_bbox_sign_cache.get(obj_id, [1.0, 1.0, 1.0])

    return mathutils.Vector((
        abs_size[0] * cached_sign[0],
        abs_size[1] * cached_sign[1],
        abs_size[2] * cached_sign[2]))


def set_edit_bbox_size(self, value):
    if self.mode != 'EDIT':
        self.dimensions = value
        return

    context = bpy.context
    bm = bmesh.from_edit_mesh(self.data)
    sel_verts = [v for v in bm.verts if v.select]

    if not sel_verts:
        return

    orient_mat = get_orientation_matrix(context, self)
    orient_mat_inv = orient_mat.inverted()
    world_mat = self.matrix_world
    world_mat_inv = world_mat.inverted()

    transformed_cos = [orient_mat_inv @ (world_mat @ v.co) for v in sel_verts]
    min_v_orient = mathutils.Vector((
        min([co[0] for co in transformed_cos]),
        min([co[1] for co in transformed_cos]),
        min([co[2] for co in transformed_cos])))
    max_v_orient = mathutils.Vector((
        max([co[0] for co in transformed_cos]),
        max([co[1] for co in transformed_cos]),
        max([co[2] for co in transformed_cos])))

    current_abs_size = max_v_orient - min_v_orient

    obj_id = self.as_pointer()
    cached_sign = _global_bbox_sign_cache.get(obj_id, [1.0, 1.0, 1.0])

    scale = [1.0, 1.0, 1.0]
    new_sign = [1.0, 1.0, 1.0]

    for i in range(3):
        new_sign[i] = 1.0 if value[i] >= 0 else -1.0
        current_ui_val = current_abs_size[i] * cached_sign[i]
        if abs(current_ui_val) > 0.00001:
            scale[i] = value[i] / current_ui_val

    _global_bbox_sign_cache[obj_id] = new_sign

    min_v_local = mathutils.Vector((
        min([v.co[0] for v in sel_verts]),
        min([v.co[1] for v in sel_verts]),
        min([v.co[2] for v in sel_verts])))
    max_v_local = mathutils.Vector((
        max([v.co[0] for v in sel_verts]),
        max([v.co[1] for v in sel_verts]),
        max([v.co[2] for v in sel_verts])))

    pivot_local = get_pivot_point(context, self, bm, sel_verts, min_v_local, max_v_local)

    pivot_world = world_mat @ pivot_local
    pivot_orient = orient_mat_inv @ pivot_world

    for v in sel_verts:
        v_world = world_mat @ v.co
        v_orient = orient_mat_inv @ v_world

        v_orient.x = pivot_orient.x + (v_orient.x - pivot_orient.x) * scale[0]
        v_orient.y = pivot_orient.y + (v_orient.y - pivot_orient.y) * scale[1]
        v_orient.z = pivot_orient.z + (v_orient.z - pivot_orient.z) * scale[2]

        v_world_new = orient_mat @ v_orient
        v.co = world_mat_inv @ v_world_new

    bmesh.update_edit_mesh(self.data)


class BETTER_EXPERIE_PT_edit_bbox_panel(bpy.types.Panel):
    bl_label = "网格边界框调整"
    bl_idname = "BETTER_EXPERIE_PT_edit_bbox_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Item"
    bl_options = {'DEFAULT_CLOSED'}
    
    @classmethod
    def poll(cls, context):
        return context.mode == 'EDIT_MESH' and context.active_object and context.active_object.type == 'MESH'

    def draw(self, context):
        layout = self.layout
        obj = context.active_object
        col = layout.column(align=True)
        col.prop(obj, "better_experie_edit_bbox_size", index=0, text="X")
        col.prop(obj, "better_experie_edit_bbox_size", index=1, text="Y")
        col.prop(obj, "better_experie_edit_bbox_size", index=2, text="Z")


classes = (
    BETTER_EXPERIE_PT_edit_bbox_panel,
)


def register():
    bpy.types.Object.better_experie_edit_bbox_size = bpy.props.FloatVectorProperty(
        name="Bounding Box", subtype='XYZ', unit='LENGTH',
        get=get_edit_bbox_size, set=set_edit_bbox_size)

    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

    del bpy.types.Object.better_experie_edit_bbox_size
