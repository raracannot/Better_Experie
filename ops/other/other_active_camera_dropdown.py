# 顶部栏活动相机下拉切换

import bpy

camera_items = []
none_camera = "__NO_CAMERA__"


def _get_object_path(obj):
    if obj.users_collection:
        col_name = f"[{obj.users_collection[0].name}]:"
    else:
        col_name = "[Scene Collection]:"
    parents = []
    current_parent = obj.parent
    while current_parent:
        parents.insert(0, current_parent.name)
        current_parent = current_parent.parent
    path_parts = [col_name] + parents + [obj.name]
    return " \\".join(path_parts)


def _collect_cameras(scene, view_layer):
    # 按筛查模式过滤相机
    filter_mode = scene.better_experie_camera_filter
    cameras = [obj for obj in scene.objects if obj.type == 'CAMERA']
    if filter_mode == 'VISIBLE':        # 视口未禁用且未隐藏
        cameras = [cam for cam in cameras
                   if not cam.hide_viewport and not cam.hide_get(view_layer=view_layer)]
    elif filter_mode == 'VIEWPORT_ON':  # 仅视口未禁用
        cameras = [cam for cam in cameras if not cam.hide_viewport]
    elif filter_mode == 'RENDER_ON':    # 仅渲染未禁用
        cameras = [cam for cam in cameras if not cam.hide_render]

    cameras.sort(key=lambda cam: cam.name) # 相机按名称排序，应当先排序再构建
    return cameras


def _get_camera_items(self, context):
    global camera_items
    camera_items = []
    for i, cam in enumerate(_collect_cameras(context.scene, context.view_layer)):
        camera_items.append((cam.name, cam.name + "\u200b", _get_object_path(cam), 'CAMERA_DATA', i))

    if not camera_items:
        camera_items.append((none_camera, "无相机", "场景无相机对象", 'ERROR', 0))
    return camera_items
    
    

def _get_active_camera(self):
    global camera_items
    if self.camera:
        cam_name = self.camera.name
        for item in camera_items:
            if item[0] == cam_name:
                return item[4]
    return 0


def _set_active_camera(self, value):
    global camera_items
    if 0 <= value < len(camera_items):
        cam_name = camera_items[value][0]
        if cam_name != none_camera and cam_name in self.objects:
            cam = self.objects[cam_name]
            self.camera = cam
            try:
                bpy.context.view_layer.objects.active = cam
            except Exception:
                pass


class BetterExperie_OT_CameraSwitch(bpy.types.Operator):
    bl_idname = "better_experie.camera_switch"
    bl_label = "切换相机"
    bl_description = "按顶部栏相机下拉栏的顺序，切换到上一个 / 下一个活动相机"
    bl_options = {'REGISTER'}  # 不写 UNDO：与原生切换相机一致，避免每次点击都压一条撤销记录

    direction: bpy.props.IntProperty(default=1, min=-1, max=1)

    @classmethod
    def poll(cls, context):
        scene = context.scene
        if scene is None:
            return False
        count = 0
        for obj in scene.objects:  # 提前退出：数到两个相机就够，不必扫完整个场景
            if obj.type == 'CAMERA':
                count += 1
                if count >= 2:
                    return True
        return False

    def execute(self, context):
        scene = context.scene
        cameras = _collect_cameras(scene, context.view_layer)

        if len(cameras) < 2:
            self.report({'WARNING'}, "可用相机不足两个")
            return {'CANCELLED'}

        try:
            index = cameras.index(scene.camera)
        except ValueError:
            # 当前没有活动相机，或活动相机被筛查模式排除在外
            index = -1 if self.direction > 0 else 0

        new_camera = cameras[(index + self.direction) % len(cameras)]
        scene.camera = new_camera

        # 与下拉栏的 set 回调保持一致：同步活动物体
        try:
            context.view_layer.objects.active = new_camera
        except Exception:
            pass

        self.report({'INFO'}, f"活动相机：{new_camera.name}")
        return {'FINISHED'}
        
        
def _draw_camera_dropdown(self, context):
    if context.region.alignment == 'RIGHT':
        row = self.layout.row(align=True)
        scene = context.scene

        row.prop(scene, "better_experie_camera_dropdown", text="", icon_only=True)
        if scene.camera:
            op = row.operator("better_experie.camera_switch", text="", icon='TRIA_LEFT')
            op.direction = -1
            
            sub = row.row(align=True)
            sub.ui_units_x = 4
            sub.prop(scene.camera, "name", text="")
            
            op = row.operator("better_experie.camera_switch", text="", icon='TRIA_RIGHT')
            op.direction = 1

        else:
            box = row.box()
            box.active = False
            box.label(text=" 未设置活动相机")
        row.prop(scene, "better_experie_camera_filter", text="", icon="FILTER", icon_only=True)
    
classes = (
    BetterExperie_OT_CameraSwitch,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
        
    bpy.types.Scene.better_experie_camera_filter = bpy.props.EnumProperty(
        name="相机筛查",
        items=[
            ('ALL', "所有相机", "列出场景全部相机对象",'OUTLINER_OB_CAMERA',0),
            ('VISIBLE', "仅可见相机", "只保留视口未禁用且未隐藏的相机",'HIDE_OFF',1),
            ('VIEWPORT_ON', "仅视口未禁用", "只保留视口未禁用的相机",'RESTRICT_VIEW_OFF',2),
            ('RENDER_ON', "仅渲染未禁用", "只保留渲染未禁用的相机",'RESTRICT_RENDER_OFF',3),
        ],default='ALL')
        
    bpy.types.Scene.better_experie_camera_dropdown = bpy.props.EnumProperty(
        name="选择相机", items=_get_camera_items, get=_get_active_camera, set=_set_active_camera,)

    if hasattr(bpy.types, "TOPBAR_HT_upper_bar"):
        bpy.types.TOPBAR_HT_upper_bar.prepend(_draw_camera_dropdown)


def unregister():
    if hasattr(bpy.types, "TOPBAR_HT_upper_bar"):
        bpy.types.TOPBAR_HT_upper_bar.remove(_draw_camera_dropdown)
    del bpy.types.Scene.better_experie_camera_dropdown
    del bpy.types.Scene.better_experie_camera_filter

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)