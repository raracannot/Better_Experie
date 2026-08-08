# 父级增量变换

import bpy
import math
import mathutils

_global_rot_cache = {}


def get_rel_matrix(obj):
    if obj.parent:
        return obj.matrix_parent_inverse @ obj.matrix_basis
    return obj.matrix_basis


def set_rel_matrix(obj, new_rel_matrix):
    if obj.parent:
        obj.matrix_basis = obj.matrix_parent_inverse.inverted() @ new_rel_matrix
    else:
        obj.matrix_basis = new_rel_matrix


def _snap_integer(value, eps):
    """值在容差内接近整数时取整显示，否则保留原值"""
    r = round(value)
    if abs(value - r) <= eps:
        return float(r)
    return value


def get_c4d_loc(self):
    v = get_rel_matrix(self).to_translation()
    # 钳制浮点残差，所有接近整数的值均取整显示（含 0）
    return mathutils.Vector((
        _snap_integer(v.x, 1e-6),
        _snap_integer(v.y, 1e-6),
        _snap_integer(v.z, 1e-6),
    ))


def set_c4d_loc(self, value):
    M_rel = get_rel_matrix(self)
    _, rot, sca = M_rel.decompose()
    new_M_rel = mathutils.Matrix.LocRotScale(value, rot, sca)
    set_rel_matrix(self, new_M_rel)


def get_c4d_rot(self):
    rot_mode = self.rotation_mode if self.rotation_mode in ['XYZ', 'XZY', 'YXZ', 'YZX', 'ZXY', 'ZYX'] else 'XYZ'
    m_rel = get_rel_matrix(self)
    obj_id = self.as_pointer()
    prev_rot = _global_rot_cache.get(obj_id, [0.0, 0.0, 0.0])
    prev_euler = mathutils.Euler(prev_rot, rot_mode)
    eu = m_rel.to_euler(rot_mode, prev_euler)
    _global_rot_cache[obj_id] = [eu.x, eu.y, eu.z]
    # 钳制浮点残差：转角度域取整，再转回弧度（含 0）
    return mathutils.Euler((
        math.radians(_snap_integer(math.degrees(eu.x), 1e-4)),
        math.radians(_snap_integer(math.degrees(eu.y), 1e-4)),
        math.radians(_snap_integer(math.degrees(eu.z), 1e-4)),
    ), rot_mode)


def set_c4d_rot(self, value):
    rot_mode = self.rotation_mode if self.rotation_mode in ['XYZ', 'XZY', 'YXZ', 'YZX', 'ZXY', 'ZYX'] else 'XYZ'
    M_rel = get_rel_matrix(self)
    loc, _, sca = M_rel.decompose()
    euler_rot = mathutils.Euler(value, rot_mode)
    obj_id = self.as_pointer()
    _global_rot_cache[obj_id] = [euler_rot.x, euler_rot.y, euler_rot.z]
    new_M_rel = mathutils.Matrix.LocRotScale(loc, euler_rot, sca)
    set_rel_matrix(self, new_M_rel)


def get_c4d_scale(self):
    s = get_rel_matrix(self).to_scale()
    # 钳制浮点残差，所有接近整数的缩放值均取整显示（含 1）
    return mathutils.Vector((
        _snap_integer(s.x, 1e-6),
        _snap_integer(s.y, 1e-6),
        _snap_integer(s.z, 1e-6),
    ))


def set_c4d_scale(self, value):
    M_rel = get_rel_matrix(self)
    loc, rot, _ = M_rel.decompose()
    new_M_rel = mathutils.Matrix.LocRotScale(loc, rot, value)
    set_rel_matrix(self, new_M_rel)


class BetterExperie_OT_ClearDeltaTransform(bpy.types.Operator):
    bl_idname = "better_experie.clear_delta_transform"
    bl_label = "清空增量变换"
    bl_description = "将增量变换叠加回原始变换中，并将增量变换归零"
    bl_options = {'REGISTER', 'UNDO'}

    mode: bpy.props.EnumProperty(
        items=[
            ('ALL', "全部", "清空全部"),
            ('LOC', "位置", "仅清空位置"),
            ('ROT', "旋转", "仅清空旋转"),
            ('SCALE', "缩放", "仅清空缩放"),
        ],
        name="模式",
        default='ALL')

    def execute(self, context):
        obj = context.active_object
        if not obj:
            return {'CANCELLED'}

        if self.mode in {'ALL', 'LOC'}:
            obj.location[0] += obj.delta_location[0]
            obj.location[1] += obj.delta_location[1]
            obj.location[2] += obj.delta_location[2]
            obj.delta_location = (0.0, 0.0, 0.0)

        if self.mode in {'ALL', 'ROT'}:
            if obj.rotation_mode == 'QUATERNION':
                obj.rotation_quaternion = obj.delta_rotation_quaternion @ obj.rotation_quaternion
                obj.delta_rotation_quaternion = (1.0, 0.0, 0.0, 0.0)
            elif obj.rotation_mode == 'AXIS_ANGLE':
                self.report({'WARNING'}, f"物体 '{obj.name}' 使用的是坐标轴角度模式，不支持增量旋转变换！")
            else:
                obj.rotation_euler[0] += obj.delta_rotation_euler[0]
                obj.rotation_euler[1] += obj.delta_rotation_euler[1]
                obj.rotation_euler[2] += obj.delta_rotation_euler[2]
                obj.delta_rotation_euler = (0.0, 0.0, 0.0)

        if self.mode in {'ALL', 'SCALE'}:
            obj.scale[0] *= obj.delta_scale[0]
            obj.scale[1] *= obj.delta_scale[1]
            obj.scale[2] *= obj.delta_scale[2]
            obj.delta_scale = (1.0, 1.0, 1.0)

        return {'FINISHED'}



class BetterExperie_OT_ResetC4DTransform(bpy.types.Operator):
    bl_idname = "better_experie.reset_c4d_transform"
    bl_label = "复位相对变换"
    bl_description = "将物体相对于父级的变换归零。Ctrl/Shift/Alt+点击时对所有选中物体执行"
    bl_options = {'REGISTER', 'UNDO'}

    reset_mode: bpy.props.EnumProperty(
        items=[
            ('ALL', "全部", "复位所有变换"),
            ('LOC', "位移", "仅复位位移"),
            ('ROT', "旋转", "仅复位旋转"),
            ('SCALE', "缩放", "仅复位缩放"),
        ],
        name="复位模式",
        default='ALL')

    apply_to_selected: bpy.props.BoolProperty(default=False, options={'HIDDEN'})

    def invoke(self, context, event):
        # 修饰键点击 → 应用到所有选中对象
        self.apply_to_selected = bool(event.ctrl or event.shift or event.alt)
        return self.execute(context)

    def _reset_obj(self, obj):
        M_rel = get_rel_matrix(obj)
        loc, rot, sca = M_rel.decompose()

        if self.reset_mode in {'ALL', 'LOC'}:
            loc = mathutils.Vector((0.0, 0.0, 0.0))

        if self.reset_mode in {'ALL', 'ROT'}:
            rot = mathutils.Quaternion((1.0, 0.0, 0.0, 0.0))
            obj_id = obj.as_pointer()
            if obj_id in _global_rot_cache:
                _global_rot_cache[obj_id] = [0.0, 0.0, 0.0]

        if self.reset_mode in {'ALL', 'SCALE'}:
            sca = mathutils.Vector((1.0, 1.0, 1.0))

        new_M_rel = mathutils.Matrix.LocRotScale(loc, rot, sca)
        set_rel_matrix(obj, new_M_rel)

    def execute(self, context):
        if self.apply_to_selected:
            objs = [o for o in context.selected_objects if o]
            if not objs:
                self.report({'WARNING'}, "未选中任何对象")
                return {'CANCELLED'}
            for obj in objs:
                self._reset_obj(obj)
            return {'FINISHED'}

        obj = context.active_object
        if not obj:
            return {'CANCELLED'}
        self._reset_obj(obj)
        return {'FINISHED'}


class BETTER_EXPERIE_PT_parent_transform_base(bpy.types.Panel):
    bl_label = "父级变换"
    bl_idname = "BETTER_EXPERIE_PT_parent_transform_base"
    
    @classmethod
    def poll(cls, context):
        return context.active_object is not None

    def draw(self, context):
        layout = self.layout
        obj = context.active_object
        if obj.parent:
            layout.label(text=f"相对于父级：{obj.parent.name}", icon='OUTLINER_OB_EMPTY')
        else:
            layout.label(text="相对于世界：无父级", icon='WORLD')

        row = layout.row(align=True)
        op_all = row.operator("better_experie.reset_c4d_transform", text="", icon='FILE_REFRESH')
        op_all.reset_mode = 'ALL'
        op_loc = row.operator("better_experie.reset_c4d_transform", text="位移")
        op_loc.reset_mode = 'LOC'
        op_rot = row.operator("better_experie.reset_c4d_transform", text="旋转")
        op_rot.reset_mode = 'ROT'
        op_scale = row.operator("better_experie.reset_c4d_transform", text="缩放")
        op_scale.reset_mode = 'SCALE'

        row = layout.row(align=True)
        row.label(text="", icon='EVENT_X')
        row.prop(obj, "better_experie_c4d_loc", index=0, text="X 位移")
        row.prop(obj, "better_experie_c4d_rot", index=0, text="X 旋转")
        row.prop(obj, "better_experie_c4d_scale", index=0, text="X 缩放")

        row = layout.row(align=True)
        row.label(text="", icon='EVENT_Y')
        row.prop(obj, "better_experie_c4d_loc", index=1, text="Y 位移")
        row.prop(obj, "better_experie_c4d_rot", index=1, text="Y 旋转")
        row.prop(obj, "better_experie_c4d_scale", index=1, text="Y 缩放")

        row = layout.row(align=True)
        row.label(text="", icon='EVENT_Z')
        row.prop(obj, "better_experie_c4d_loc", index=2, text="Z 位移")
        row.prop(obj, "better_experie_c4d_rot", index=2, text="Z 旋转")
        row.prop(obj, "better_experie_c4d_scale", index=2, text="Z 缩放")

class BETTER_EXPERIE_PT_parent_transform_object(BETTER_EXPERIE_PT_parent_transform_base):
    bl_label = "父级变换"
    bl_idname = "BETTER_EXPERIE_PT_parent_transform_object"
    bl_parent_id = "OBJECT_PT_transform"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "object"
    bl_options = {'DEFAULT_CLOSED'}

class BETTER_EXPERIE_PT_parent_transform_view3d(BETTER_EXPERIE_PT_parent_transform_base):
    bl_label = "父级变换"
    bl_idname = "BETTER_EXPERIE_PT_parent_transform_view3d"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Item"
    bl_options = {'DEFAULT_CLOSED'}


classes = (
    BetterExperie_OT_ClearDeltaTransform,
    BetterExperie_OT_ResetC4DTransform,
    BETTER_EXPERIE_PT_parent_transform_object,
    BETTER_EXPERIE_PT_parent_transform_view3d,
)


def register():
    bpy.types.Object.better_experie_c4d_loc = bpy.props.FloatVectorProperty(
        name="Location", subtype='TRANSLATION', unit='LENGTH',
        get=get_c4d_loc, set=set_c4d_loc, default=(0.0, 0.0, 0.0))
    bpy.types.Object.better_experie_c4d_rot = bpy.props.FloatVectorProperty(
        name="Rotation", subtype='EULER', unit='ROTATION',
        get=get_c4d_rot, set=set_c4d_rot, default=(0.0, 0.0, 0.0))
    bpy.types.Object.better_experie_c4d_scale = bpy.props.FloatVectorProperty(
        name="Scale", subtype='XYZ',
        get=get_c4d_scale, set=set_c4d_scale, default=(1.0, 1.0, 1.0))

    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

    del bpy.types.Object.better_experie_c4d_loc
    del bpy.types.Object.better_experie_c4d_rot
    del bpy.types.Object.better_experie_c4d_scale
