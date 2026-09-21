# 相机灯光追踪工具

import bpy
from mathutils import Matrix, Vector
from bpy_extras import view3d_utils

from ...utils.modal_border import add_modal_border, remove_modal_border

# 记录“新建空白追踪”模态操作中创建的临时约束。
PENDING_BLANK_TRACK = {"owner": None,"constraint": None,}


def is_camera_or_light(obj):
    return obj is not None and obj.type in {"CAMERA", "LIGHT"}

def clear_pending_blank_track():
    PENDING_BLANK_TRACK["owner"] = None
    PENDING_BLANK_TRACK["constraint"] = None

def get_pending_blank_track():
    owner = PENDING_BLANK_TRACK["owner"]
    constraint = PENDING_BLANK_TRACK["constraint"]
    if owner is None or constraint is None:
        return None, None

    try:
        for item in owner.constraints:
            if item == constraint:
                return owner, constraint
    except ReferenceError:
        pass

    clear_pending_blank_track()
    return None, None

def remove_pending_blank_track():
    owner, constraint = get_pending_blank_track()
    if owner is not None and constraint is not None:
        try:
            owner.constraints.remove(constraint)
        except ReferenceError:
            pass

    clear_pending_blank_track()


def restore_selection(context, selected_names, active_name):
    """恢复模态拾取前的对象选择状态。"""
    try:
        for obj in context.view_layer.objects:
            obj.select_set(False)
        for name in selected_names:
            obj = bpy.data.objects.get(name)
            if obj is not None:
                obj.select_set(True)
        context.view_layer.objects.active = bpy.data.objects.get(active_name) if active_name else None
    except Exception:
        pass


class BetterExperie_OT_AddBlankTrack(bpy.types.Operator):
    bl_idname = "better_experie.add_blank_track"
    bl_label = "新建空白追踪"
    bl_description = "直接进入视图/大纲吸取模式，左键指定追踪目标；Esc 退出并删除约束，右键退出并保留约束"
    bl_options = {"REGISTER", "UNDO"}

    _modal_border_handle = None

    @classmethod
    def poll(cls, context):
        return is_camera_or_light(context.object)

    def area_region_under_mouse(self, context, event):
        """根据鼠标位置查找所在的区域。"""
        screen = getattr(context, "screen", None)
        if screen is None:
            return None, None
        mouse_x, mouse_y = event.mouse_x, event.mouse_y
        for area in screen.areas:
            if not (area.x <= mouse_x < area.x + area.width and area.y <= mouse_y < area.y + area.height):
                continue
            for region in area.regions:
                if region.type == "WINDOW" and region.x <= mouse_x < region.x + region.width and region.y <= mouse_y < region.y + region.height:
                    return area, region
        return None, None

    def pick_object(self, context, area, region, event):
        """在 3D 视图中使用鼠标位置射线检测并吸取对象。"""
        region_3d = area.spaces.active.region_3d
        if region_3d is None:
            return None

        mouse_pos = Vector((event.mouse_x - region.x, event.mouse_y - region.y,))

        depsgraph = context.evaluated_depsgraph_get()
        ray_origin = view3d_utils.region_2d_to_origin_3d(region,region_3d,mouse_pos,)
        ray_direction = view3d_utils.region_2d_to_vector_3d(region,region_3d,mouse_pos,)
        hit, location, normal, face_index, hit_object, matrix = context.scene.ray_cast(depsgraph,ray_origin,ray_direction,)

        # 优先吸取射线命中的网格等可射线检测对象。
        if hit and hit_object is not None:
            return hit_object.original

        # 射线没有命中几何体时，检测空物体、相机、灯光等对象原点。
        closest_object = None
        closest_distance = 24.0

        for obj in context.view_layer.objects:
            if obj.hide_viewport:
                continue

            screen_pos = view3d_utils.location_3d_to_region_2d(region,region_3d,obj.matrix_world.translation,)
            if screen_pos is None:
                continue

            distance = (screen_pos - mouse_pos).length
            if distance < closest_distance:
                closest_distance = distance
                closest_object = obj

        return closest_object

    def pick_outliner(self, context, area, region):
        """在大纲中点击以吸取对象。"""
        old_selected = [obj.name for obj in context.selected_objects]
        old_active = context.view_layer.objects.active.name if context.view_layer.objects.active else ""
        before = {obj.name for obj in context.selected_objects}

        try:
            with context.temp_override(window=context.window, area=area, region=region):
                bpy.ops.outliner.item_activate("INVOKE_DEFAULT")
        except Exception as error:
            print("[Track Tools] Outliner 拾取失败：", error)
            restore_selection(context, old_selected, old_active)
            return None

        after = {obj.name for obj in context.selected_objects}
        hit_names = after - before
        active_obj = context.view_layer.objects.active
        if active_obj is not None:
            hit_names.add(active_obj.name)

        target = None
        for name in hit_names:
            candidate = bpy.data.objects.get(name)
            if candidate is not None and candidate != context.object:
                target = candidate
                break

        # 恢复原选择，成功吸取时由 modal 统一改选目标。
        restore_selection(context, old_selected, old_active)
        return target

    def finish_modal(self, context):
        """恢复鼠标状态及底部状态栏提示。"""
        remove_modal_border(self)
        try:
            context.window.cursor_modal_restore()
        except RuntimeError:
            pass
        try:
            context.workspace.status_text_set(None)
        except RuntimeError:
            pass

    def invoke(self, context, event):
        obj = context.object

        if not is_camera_or_light(obj):
            self.report({"WARNING"}, "仅相机或灯光可以使用追踪工具")
            return {"CANCELLED"}

        # 清理之前未完成的临时追踪。
        remove_pending_blank_track()

        try:
            # 新建标准 Track To 约束。
            constraint = obj.constraints.new(type="TRACK_TO")
            constraint.name = "Track To"
            constraint.track_axis = "TRACK_NEGATIVE_Z"
            constraint.up_axis = "UP_Y"

            PENDING_BLANK_TRACK["owner"] = obj
            PENDING_BLANK_TRACK["constraint"] = constraint

            # 进入模态吸取状态。
            context.window.cursor_modal_set("EYEDROPPER")
            context.workspace.status_text_set("吸取追踪目标：在 3D 视图或大纲中左键点击对象；Esc取消；右键退出")
            add_modal_border(self, context)
            context.window_manager.modal_handler_add(self)
        except Exception as error:
            import traceback
            traceback.print_exc()
            remove_pending_blank_track()
            self.finish_modal(context)
            self.report({"ERROR"}, f"启动追踪工具失败：{error}")
            return {"CANCELLED"}

        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        try:
            owner, constraint = get_pending_blank_track()

            # 临时约束被手动删除时，退出模态。
            if owner is None or constraint is None:
                clear_pending_blank_track()
                self.finish_modal(context)
                return {"CANCELLED"}

            # Esc：退出并删除本次新建的空白追踪约束。
            if event.type == "ESC":
                owner.constraints.remove(constraint)
                clear_pending_blank_track()
                self.finish_modal(context)

                self.report({"INFO"}, "已取消并清理空白追踪约束")
                return {"CANCELLED"}

            # 右键：退出吸取模式，但保留当前创建的约束。
            if event.type == "RIGHTMOUSE":
                clear_pending_blank_track()
                self.finish_modal(context)

                self.report({"INFO"}, "已退出吸取模式，保留当前追踪约束")
                return {"FINISHED"}

            # 左键点击时，尝试在 3D 视图或大纲中吸取对象。
            if event.type == "LEFTMOUSE" and event.value == "PRESS":
                area, region = self.area_region_under_mouse(context, event)
                target = None
                if area is not None and region is not None:
                    if area.type == "VIEW_3D":
                        target = self.pick_object(context, area, region, event)
                    elif area.type == "OUTLINER":
                        target = self.pick_outliner(context, area, region)

                # 鼠标不在 3D 视图/大纲，或者没有点击到对象时，继续等待。
                if target is None:
                    self.report({"INFO"}, "未吸取到对象，请在 3D 视图或大纲中点击目标")
                    return {"RUNNING_MODAL"}

                # 不允许追踪目标为自身。
                if target == owner:
                    self.report({"WARNING"}, "不能将对象自身设为追踪目标")
                    return {"RUNNING_MODAL"}

                constraint.target = target
                clear_pending_blank_track()
                self.finish_modal(context)

                bpy.ops.object.select_all(action="DESELECT")
                target.select_set(True)
                context.view_layer.objects.active = target
                self.report({"INFO"}, f"已创建追踪约束，目标：{target.name}")
                return {"FINISHED"}

            return {"RUNNING_MODAL"}

        except Exception as error:
            import traceback
            traceback.print_exc()
            remove_pending_blank_track()
            self.finish_modal(context)
            self.report({"ERROR"}, f"追踪工具异常：{error}")
            return {"CANCELLED"}

    def cancel(self, context):
        remove_pending_blank_track()
        self.finish_modal(context)


class BetterExperie_OT_AddEmptyTrack(bpy.types.Operator):
    bl_idname = "better_experie.add_empty_track"
    bl_label = "新建空物体追踪"
    bl_description = "创建沿局部 -Z 方向偏移 1 米的空物体，并将其作为追踪目标"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return is_camera_or_light(context.object)

    def execute(self, context):
        obj = context.object
        if not is_camera_or_light(obj):
            self.report({"WARNING"}, "仅相机或灯光可以使用追踪工具")
            return {"CANCELLED"}

        empty = bpy.data.objects.new(name=f"{obj.name}_TrackTarget", object_data=None)
        empty.empty_display_size = 0.25
        if obj.users_collection:
            obj.users_collection[0].objects.link(empty)
        else:
            context.collection.objects.link(empty)

        obj_location, obj_rotation, obj_scale = obj.matrix_world.decompose()
        empty.matrix_world = Matrix.LocRotScale(obj_location, obj_rotation, None)
        # 沿原物体自身的局部 -Z 方向，在世界空间移动 1 米。
        empty.location += obj_rotation @ Vector((0.0, 0.0, -1.0))

        constraint = obj.constraints.new(type="TRACK_TO")
        # constraint.name = "Track To"
        constraint.target = empty

        bpy.ops.object.select_all(action="DESELECT")
        empty.select_set(True)
        context.view_layer.objects.active = empty
        self.report({"INFO"}, f"已创建空物体追踪目标：{empty.name}")
        return {"FINISHED"}


class BetterExperie_OT_ApplyTrack(bpy.types.Operator):
    bl_idname = "better_experie.apply_track"
    bl_label = "应用追踪"
    bl_description = "保留当前追踪后的姿态，并移除全部 Track To 约束；Ctrl 点击时同时删除作为目标的空物体"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        obj = context.object
        if not is_camera_or_light(obj):
            return False
        return any(item.type == "TRACK_TO" for item in obj.constraints)

    def invoke(self, context, event):
        # Ctrl + 点击时，删除追踪目标空物体。
        return self.apply_track(context, delete_empty_targets=event.ctrl)

    def execute(self, context):
        # 通过搜索菜单、Python 或其他非鼠标方式执行时，仅应用追踪。
        return self.apply_track(context, delete_empty_targets=False)

    def apply_track(self, context, delete_empty_targets=False):
        obj = context.object
        if not is_camera_or_light(obj):
            self.report({"WARNING"}, "仅相机或灯光可以使用追踪工具")
            return {"CANCELLED"}

        track_constraints = [item for item in obj.constraints if item.type == "TRACK_TO"]
        if not track_constraints:
            self.report({"INFO"}, "当前对象没有 Track To 追踪约束")
            return {"CANCELLED"}

        # 记录所有作为 Track To 目标的空物体。
        empty_targets = []
        if delete_empty_targets:
            for constraint in track_constraints:
                target = constraint.target
                if target is not None and target.type == "EMPTY":
                    if target not in empty_targets:
                        empty_targets.append(target)

        # 取得约束生效后的最终世界矩阵。
        context.view_layer.update()
        depsgraph = context.evaluated_depsgraph_get()
        evaluated_obj = obj.evaluated_get(depsgraph)
        final_world_matrix = evaluated_obj.matrix_world.copy()

        # 移除全部 Track To 约束。
        for constraint in track_constraints:
            obj.constraints.remove(constraint)

        # 将最终视觉姿态写回原对象。
        context.view_layer.update()
        obj.matrix_world = final_world_matrix

        # Ctrl 点击时，删除 Track To 指向的空物体。
        deleted_count = 0
        if delete_empty_targets:
            for empty in empty_targets:
                try:
                    bpy.data.objects.remove(empty, do_unlink=True)
                    deleted_count += 1
                except ReferenceError:
                    pass

        if delete_empty_targets:
            self.report({"INFO"}, f"已应用并移除 {len(track_constraints)} 个 Track To 约束，同时删除 {deleted_count} 个空物体")
        else:
            self.report({"INFO"}, f"已应用并移除 {len(track_constraints)} 个 Track To 追踪约束")
        return {"FINISHED"}


def draw_track_tools(self, context):
    obj = context.object
    # 仅在相机或灯光对象上显示按钮。
    if not is_camera_or_light(obj):
        return
    layout = self.layout
    row = layout.row(align=True)
    row.operator("better_experie.add_blank_track", text="空白追踪", icon="CON_TRACKTO")
    row.operator("better_experie.add_empty_track", text="空物体追踪", icon="EMPTY_AXIS")
    row.separator()
    row.operator("better_experie.apply_track", text="应用追踪", icon="CHECKMARK")


classes = (
    BetterExperie_OT_AddBlankTrack,
    BetterExperie_OT_AddEmptyTrack,
    BetterExperie_OT_ApplyTrack,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    try:
        bpy.types.OBJECT_PT_constraints.append(draw_track_tools)
    except (ValueError, AttributeError):
        pass


def unregister():
    remove_pending_blank_track()

    try:
        bpy.types.OBJECT_PT_constraints.remove(draw_track_tools)
    except (ValueError, AttributeError):
        pass

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
