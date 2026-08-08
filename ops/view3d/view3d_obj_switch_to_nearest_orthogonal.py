# 就近正交

import bpy
import math
import mathutils

def get_nearest_axis(rv3d):
    view_quat = rv3d.view_rotation
    forward = view_quat @ mathutils.Vector((0.0, 0.0, 1.0))

    axes = [
        (mathutils.Vector((0, 0, 1)), 'TOP'),
        (mathutils.Vector((0, 0, -1)), 'BOTTOM'),
        (mathutils.Vector((0, 1, 0)), 'BACK'),
        (mathutils.Vector((0, -1, 0)), 'FRONT'),
        (mathutils.Vector((1, 0, 0)), 'RIGHT'),
        (mathutils.Vector((-1, 0, 0)), 'LEFT'),
    ]
    # 计算每个轴的 dot
    axis_list = []
    for axis_vec, axis_name in axes:
        dot = forward.dot(axis_vec)
        axis_list.append((axis_name, dot))
    # 按 dot 值降序排序
    axis_list.sort(key=lambda x: x[1], reverse=True)
    return axis_list

class BetterExperie_OT_SwitchToNearestOrthogonal(bpy.types.Operator):
    bl_idname = "better_experie.switch_to_nearest_orthogonal"
    bl_label = "就近正交"
    bl_description = "切换到最近正交轴或还原为透视模式"
    self_angle_time:bpy.props.IntProperty()

    def execute(self, context):
        axis_to_time = {'FRONT': 0,'LEFT': 1,'BACK': 2,'RIGHT': 3}
        rv3d = context.region_data
        if rv3d.view_perspective != 'ORTHO':
            axis_list = get_nearest_axis(rv3d)
            #print(f"【就近轴排序列表】: {axis_list}")#debug
            axis = axis_list[0][0]
            bpy.ops.view3d.view_axis(type=axis)

            if axis in ('TOP', 'BOTTOM'):
                axis = axis_list[1][0]
                dot = axis_list[1][1]

                if dot>=0.001:
                    angle_time = axis_to_time.get(axis, 0)
                    self.self_angle_time = angle_time
                else:
                    angle_time = self.self_angle_time
                for _ in range(angle_time):
                    bpy.ops.view3d.view_orbit(angle=math.radians(90), type='ORBITLEFT')
        else:
            bpy.ops.view3d.view_persportho()
        return {'FINISHED'}

        
classes = (
    BetterExperie_OT_SwitchToNearestOrthogonal,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)