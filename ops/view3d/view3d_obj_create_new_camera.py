# 新建相机到当前

import bpy
import bmesh
    
# 检查当前视口是否处于摄像机透视模式
def is_camera_perspective(context):
    for area in context.screen.areas:
        if area.type == 'VIEW_3D':
            for space in area.spaces:
                if space.type == 'VIEW_3D' and space.region_3d.view_perspective == 'CAMERA':
                    return True
    return False

# 检查当前视口是否处于正交视图
def is_orthographic_view(context):
    for area in context.screen.areas:
        if area.type == 'VIEW_3D':
            for space in area.spaces:
                if space.type == 'VIEW_3D' and space.region_3d.is_orthographic_side_view:
                    return True
    return False
    

class BetterExperie_OT_CreateNewCameraAtView(bpy.types.Operator):
    bl_idname = "better_experie.create_new_camera_at_view"
    bl_label = "新建相机到当前"
    bl_description = "在当前视图创建新相机"

    def execute(self, context):
        # 保存当前活动对象
        original_active_obj = context.active_object

        # 计算相机位置
        if is_camera_perspective(context):
            location = context.scene.camera.location if context.scene.camera else context.region_data.view_location
        else:
            location = context.region_data.view_location

        try:
            # 添加相机（此时一定在对象模式）
            if context.mode != 'OBJECT':
                bpy.ops.object.mode_set(mode='OBJECT')
                
            bpy.ops.object.camera_add(location=location)
            new_camera = context.active_object
            context.scene.camera = new_camera
        except Exception as e:
            self.report({'ERROR'}, f"创建相机时发生错误: {e}")
            return {'CANCELLED'}

        # 检查是否为正交视图，设置相机类型
        if is_orthographic_view(context):
            new_camera.data.type = 'ORTHO'
        try:
            bpy.ops.view3d.camera_to_view()
        except Exception as e:
            self.report({'ERROR'}, f"移动相机到视图时发生错误: {e}")
        
        if original_active_obj is not None:
            original_active_obj.select_set(True)
            context.view_layer.objects.active = original_active_obj
        
        self.report({'INFO'}, f"新建相机到当前视口完成")
        return {'FINISHED'}
    

classes = (
    BetterExperie_OT_CreateNewCameraAtView,
)

    
def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)