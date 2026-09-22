# 自动渲染槽位轮换：渲染完成后自动切换到下一个 Render Slot，不足时自动创建

import bpy
from datetime import datetime
from bpy.app.handlers import persistent

_auto_slot_running = False
_scheduled_scenes = set()


def _get_render_result():
    image = bpy.data.images.get("Render Result")
    if image and image.type == 'RENDER_RESULT':
        return image
    return None


def _find_image_editor_context():
    for window in bpy.context.window_manager.windows:
        screen = window.screen
        if not screen:
            continue
        for area in screen.areas:
            if area.type != 'IMAGE_EDITOR':
                continue
            region = next((region for region in area.regions if region.type == 'WINDOW'), None)
            if region:
                return window, area, region, area.spaces.active
    return None


def _add_render_slot(image):
    old_count = len(image.render_slots)
    context_data = _find_image_editor_context()
    if context_data is None:
        print("[自动渲染槽位] 未找到图像编辑器，无法新增 Render Slot")
        return -1
    window, area, region, space = context_data
    original_image = space.image
    try:
        space.image = image
        with bpy.context.temp_override(window=window, area=area, region=region):
            bpy.ops.image.add_render_slot()
        area.tag_redraw()
    except Exception as exc:
        print(f"[自动渲染槽位] 新建 Render Slot 失败: {exc}")
        return -1
    finally:
        try:
            space.image = original_image
        except Exception:
            pass
    new_count = len(image.render_slots)
    if new_count <= old_count:
        return -1
    new_index = new_count - 1
    try:
        image.render_slots[new_index].name = f"Slot_{new_count}"
    except Exception:
        pass
    return new_index


def _rename_active_render_slot():
    image = _get_render_result()
    if image is None:
        return
    try:
        active_index = image.render_slots.active_index
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        image.render_slots[active_index].name = f"Slot_{active_index + 1}_{timestamp}"
    except Exception as exc:
        print(f"[自动渲染槽位] 重命名写入槽位失败: {exc}")


def _switch_to_next_render_slot():
    image = _get_render_result()
    if image is None:
        print("[自动渲染槽位] 未找到 Render Result")
        return False
    slot_count = len(image.render_slots)
    if slot_count == 0:
        new_index = _add_render_slot(image)
        if new_index < 0:
            return False
        image.render_slots.active_index = new_index
        print(f"[自动渲染槽位] 已新建并切换到槽位 {new_index + 1}")
        return True
    current_index = image.render_slots.active_index
    next_index = current_index + 1
    # 已有下一个槽位：直接切换，下一次渲染覆盖该槽位。
    if next_index < slot_count:
        image.render_slots.active_index = next_index
        print(f"[自动渲染槽位] 已切换：槽位 {current_index + 1} -> 槽位 {next_index + 1}")
        return True
    # 当前已是最后一个槽位：新增槽位。
    new_index = _add_render_slot(image)
    if new_index < 0:
        print("[自动渲染槽位] 当前已是最后一个槽位，且新建槽位失败")
        return False
    image.render_slots.active_index = new_index
    print(f"[自动渲染槽位] 已新建并切换到槽位 {new_index + 1}")
    return True


def _schedule_next_slot(scene, delay=0.35):
    if not _auto_slot_running:
        return
    scene_key = scene.as_pointer()
    if scene_key in _scheduled_scenes:
        return
    _scheduled_scenes.add(scene_key)

    def timer_callback():
        _scheduled_scenes.discard(scene_key)
        if not _auto_slot_running:
            return None
        try:
            props = scene.better_experie_auto_render_slot
            if props.enabled:
                _switch_to_next_render_slot()
        except ReferenceError:
            pass
        except Exception as exc:
            print(f"[自动渲染槽位] 自动切换失败: {exc}")
        return None

    bpy.app.timers.register(timer_callback, first_interval=max(0.0, delay))


@persistent
def _render_slot_render_complete(scene):
    try:
        props = scene.better_experie_auto_render_slot
        if not props.enabled:
            return
        _rename_active_render_slot()
        _schedule_next_slot(scene)
    except Exception as exc:
        print(f"[自动渲染槽位] 渲染完成回调失败: {exc}")


class BetterExperie_AutoRenderSlotSettings(bpy.types.PropertyGroup):
    enabled: bpy.props.BoolProperty(
        name="自动写入下一槽位",
        description="每次渲染完成后自动切换到下一个 Render Slot",
        default=False,
    )


class BetterExperie_OT_SwitchToNextRenderSlot(bpy.types.Operator):
    bl_idname = "better_experie.switch_to_next_render_slot"
    bl_label = "切换到下一槽位"
    bl_description = "立即切换到当前活动槽位的下一个槽位，不足时自动创建"

    @classmethod
    def poll(cls, context):
        image = context.space_data.image if context.space_data else None
        return bool(image and image.type == 'RENDER_RESULT')

    def execute(self, context):
        if _switch_to_next_render_slot():
            self.report({'INFO'}, "已切换到下一 Render Slot")
            return {'FINISHED'}

        self.report({'ERROR'}, "切换 Render Slot 失败，请确保存在图像编辑器区域")
        return {'CANCELLED'}


class BetterExperie_OT_ClearOtherRenderSlots(bpy.types.Operator):
    bl_idname = "better_experie.clear_other_render_slots"
    bl_label = "清空渲染槽"
    bl_description = "删除除当前活动槽位以外的所有渲染槽位"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        image = context.space_data.image if context.space_data else None
        return bool(image and image.type == 'RENDER_RESULT' and len(image.render_slots) > 1)

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        image = context.space_data.image
        if not image or image.type != 'RENDER_RESULT':
            self.report({'ERROR'}, "当前不是渲染结果")
            return {'CANCELLED'}

        slot_count = len(image.render_slots)
        active_index = image.render_slots.active_index
        if slot_count <= 1:
            self.report({'INFO'}, "当前只有一个渲染槽，无需清理")
            return {'CANCELLED'}
        try:
            # 先从后向前删除活动槽位右侧的槽位，逆序避免索引变化造成错误。
            for index in range(slot_count - 1, active_index, -1):
                image.render_slots.active_index = index
                bpy.ops.image.remove_render_slot()

            # 再从活动槽位左侧向前删除，每删一个左侧槽位原活动槽位自动左移。
            for index in range(active_index - 1, -1, -1):
                image.render_slots.active_index = index
                bpy.ops.image.remove_render_slot()

            # 删除完成后，唯一保留的槽位索引一定是 0。
            image.render_slots.active_index = 0
            context.area.tag_redraw()
            self.report({'INFO'}, "已清理其他渲染槽位，仅保留原活动槽位")
            return {'FINISHED'}

        except Exception as exc:
            self.report({'ERROR'}, f"清理渲染槽位失败: {exc}")
            return {'CANCELLED'}


class BetterExperie_OT_CycleRenderSlot(bpy.types.Operator):
    bl_idname = "better_experie.cycle_render_slot"
    bl_label = "循环切换渲染槽位"
    bl_description = "循环切换到上一个或下一个渲染槽位"
    bl_options = {'REGISTER'}

    direction: bpy.props.EnumProperty(
        name="切换方向",
        items=[
            ('PREVIOUS', "上一个", "循环切换到上一个槽位"),
            ('NEXT', "下一个", "循环切换到下一个槽位"),
        ], default='NEXT')

    @classmethod
    def poll(cls, context):
        image = context.space_data.image if context.space_data else None
        return bool(image and image.type == 'RENDER_RESULT' and len(image.render_slots) > 0)

    def execute(self, context):
        image = context.space_data.image
        slot_count = len(image.render_slots)
        current_index = image.render_slots.active_index
        if self.direction == 'NEXT':
            target_index = (current_index + 1) % slot_count
        else:
            target_index = (current_index - 1) % slot_count
        image.render_slots.active_index = target_index
        context.area.tag_redraw()
        self.report({'INFO'}, f"已切换到槽位 {target_index + 1}")
        return {'FINISHED'}


def _image_pt_render_slots_up_draw(self, context):
    layout = self.layout
    row = layout.row(align=True)
    op = row.operator("better_experie.cycle_render_slot", text="上一槽位", icon='TRIA_LEFT')
    op.direction = 'PREVIOUS'
    op = row.operator("better_experie.cycle_render_slot", text="下一槽位", icon='TRIA_RIGHT')
    op.direction = 'NEXT'


def _image_pt_render_slots_draw(self, context):
    layout = self.layout
    props = context.scene.better_experie_auto_render_slot
    row = layout.row()
    row.prop(props, "enabled", text="自动下一个", icon='RENDER_RESULT')
    enabled_row = row.row(align=True)
    enabled_row.operator("better_experie.switch_to_next_render_slot", text="", icon='SORT_ASC')
    enabled_row.operator("better_experie.clear_other_render_slots", text="", icon='TRASH')


classes = (
    BetterExperie_AutoRenderSlotSettings,
    BetterExperie_OT_SwitchToNextRenderSlot,
    BetterExperie_OT_CycleRenderSlot,
    BetterExperie_OT_ClearOtherRenderSlots,
)


def register():
    global _auto_slot_running
    _auto_slot_running = True

    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.better_experie_auto_render_slot = bpy.props.PointerProperty(type=BetterExperie_AutoRenderSlotSettings)
    try:
        bpy.types.IMAGE_PT_render_slots.prepend(_image_pt_render_slots_up_draw)
    except (ValueError, AttributeError):
        pass
    try:
        bpy.types.IMAGE_PT_render_slots.append(_image_pt_render_slots_draw)
    except (ValueError, AttributeError):
        pass

    if _render_slot_render_complete not in bpy.app.handlers.render_complete:
        bpy.app.handlers.render_complete.append(_render_slot_render_complete)


def unregister():
    global _auto_slot_running
    _auto_slot_running = False
    _scheduled_scenes.clear()

    if _render_slot_render_complete in bpy.app.handlers.render_complete:
        bpy.app.handlers.render_complete.remove(_render_slot_render_complete)
    try:
        bpy.types.IMAGE_PT_render_slots.remove(_image_pt_render_slots_up_draw)
    except (ValueError, AttributeError):
        pass
    try:
        bpy.types.IMAGE_PT_render_slots.remove(_image_pt_render_slots_draw)
    except (ValueError, AttributeError):
        pass
    if hasattr(bpy.types.Scene, "better_experie_auto_render_slot"):
        del bpy.types.Scene.better_experie_auto_render_slot

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
