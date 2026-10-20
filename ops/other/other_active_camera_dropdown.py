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


def _get_camera_items(self, context):
    global camera_items
    camera_items = []
    scene = context.scene
    filter_mode = scene.better_experie_camera_filter

    cameras = [obj for obj in context.scene.objects if obj.type == 'CAMERA']

    # 按筛查模式过滤相机
    filtered_cams = []
    if filter_mode == 'ALL':
        for cam in cameras:
            filtered_cams.append(cam)
    elif filter_mode == 'VISIBLE':
        for cam in cameras: # 视口未禁用未隐藏
            if not cam.hide_viewport and not cam.hide_get(view_layer=context.view_layer):
                filtered_cams.append(cam)
    elif filter_mode == 'VIEWPORT_ON':
        for cam in cameras: # 仅视口未禁用
            if not cam.hide_viewport:
                filtered_cams.append(cam)
    elif filter_mode == 'RENDER_ON':
        for cam in cameras: # 仅渲染未禁用
            if not cam.hide_render:
                filtered_cams.append(cam)

    for i, cam in enumerate(filtered_cams):
        cam_path = _get_object_path(cam)
        camera_items.append((cam.name, cam.name + "\u200b", cam_path, 'CAMERA_DATA', i))
    camera_items.sort(key=lambda x: x[0]) #相机按名称排序

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


def _draw_camera_dropdown(self, context):
    if context.region.alignment == 'RIGHT':
        row = self.layout.row(align=True)
        scene = context.scene
        row.prop(scene, "better_experie_camera_dropdown", text="", icon_only=True)
        if scene.camera:
            row.prop(scene.camera, "name", text="")
        else:
            box = row.box()
            box.active = False
            box.label(text=" 未设置活动相机")
        row.prop(scene, "better_experie_camera_filter", text="",icon="FILTER", icon_only=True)


def register():
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
