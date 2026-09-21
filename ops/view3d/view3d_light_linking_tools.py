# 灯光链接 / 阴影链接工具：向原生灯光数据面板与右键菜单注入批量操作

import bpy
from bpy.props import EnumProperty

from ...utils.modal_border import add_modal_border, remove_modal_border

LINK_TYPES = [
    ("LIGHT", "Light Linking", "Operate on Light Linking"),
    ("SHADOW", "Shadow Linking", "Operate on Shadow Linking"),
]


def light_linking_label(link_type):
    return "灯光链接" if link_type == "LIGHT" else "阴影链接"


def light_linking_get_collection(light_obj, link_type):
    if link_type == "LIGHT":
        return light_obj.light_linking.receiver_collection
    return light_obj.light_linking.blocker_collection


def light_linking_set_collection(light_obj, link_type, collection):
    if link_type == "LIGHT":
        light_obj.light_linking.receiver_collection = collection
    else:
        light_obj.light_linking.blocker_collection = collection


def light_linking_ensure_collection(context, light_obj, link_type):
    collection = light_linking_get_collection(light_obj, link_type)
    if collection is not None:
        return collection
    try:
        with context.temp_override(
            active_object=light_obj,
            object=light_obj,
            selected_objects=[light_obj],
            selected_editable_objects=[light_obj],
        ):
            if link_type == "LIGHT":
                bpy.ops.object.light_linking_receiver_collection_new()
            else:
                bpy.ops.object.light_linking_blocker_collection_new()
    except Exception as error:
        print("[Light Linking] 创建链接集合失败：", error)
        return None
    return light_linking_get_collection(light_obj, link_type)


def light_linking_collection_objects(collection):
    return getattr(collection, "collection_objects", ())


def light_linking_collection_children(collection):
    return getattr(collection, "collection_children", ())


def light_linking_items(collection):
    return list(light_linking_collection_objects(collection)) + list(light_linking_collection_children(collection))


def light_linking_object_is_linked(collection, obj):
    return collection is not None and collection.objects.get(obj.name) is not None


def light_linking_mode(collection):
    items = light_linking_items(collection)
    if not items:
        # 默认 INCLUDE 包含
        return "INCLUDE"
    if any(item.light_linking.link_state == "INCLUDE" for item in items):
        # 任意 INCLUDE 包含，走 INCLUDE 包含判断
        return "INCLUDE"
    # 没有任何 INCLUDE 才走 EXCLUDE 排除判断
    return "EXCLUDE"


def light_linking_remove_exclude_items(collection):
    # 修复：按引用移除，避免 collection_objects 与 objects 的索引错位导致误删
    removed_count = 0

    exclude_objects = [
        item for item in light_linking_collection_objects(collection)
        if item.light_linking.link_state == "EXCLUDE"
    ]
    for obj in exclude_objects:
        try:
            collection.objects.unlink(obj)
            removed_count += 1
        except Exception as error:
            print("[Light Linking] 移除排除对象失败：", obj.name, error)

    exclude_children = [
        item for item in light_linking_collection_children(collection)
        if item.light_linking.link_state == "EXCLUDE"
    ]
    for child in exclude_children:
        try:
            collection.children.unlink(child)
            removed_count += 1
        except Exception as error:
            print("[Light Linking] 移除排除集合失败：", child.name, error)

    return removed_count


def light_linking_set_all_states(collection, state):
    changed_count = 0
    for item in light_linking_items(collection):
        if item.light_linking.link_state != state:
            item.light_linking.link_state = state
            changed_count += 1
    return changed_count


def light_linking_add_object(context, light_obj, obj, link_type):
    if obj is None or obj == light_obj:
        return False
    collection = light_linking_ensure_collection(context, light_obj, link_type)
    if collection is None or light_linking_object_is_linked(collection, obj):
        return False
    try:
        link_state = light_linking_mode(collection)
        collection.objects.link(obj)
        # 修复：按引用定位新条目，避免依赖 collection_objects[-1] 的顺序假设
        for item in light_linking_collection_objects(collection):
            if item == obj:
                item.light_linking.link_state = link_state
                break
        light_obj.update_tag()
        return True
    except Exception as error:
        print("[Light Linking] 添加对象失败：", error)
        return False


def light_linking_remove_object(light_obj, obj, link_type):
    if obj is None or obj == light_obj:
        return False
    collection = light_linking_get_collection(light_obj, link_type)
    if collection is None or collection.objects.get(obj.name) is None:
        return False
    try:
        collection.objects.unlink(obj)
        light_obj.update_tag()
        return True
    except Exception as error:
        print("[Light Linking] 移除对象失败：", error)
        return False


def light_linking_restore_selection(context, selected_names, active_name):
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


def light_linking_tag_redraw(context):
    screen = getattr(context, "screen", None)
    if screen is None:
        return
    for area in screen.areas:
        if area.type in {"VIEW_3D", "OUTLINER", "PROPERTIES"}:
            area.tag_redraw()


def light_linking_update_status(context, light_obj, link_type):
    if light_obj is None:
        return
    collection = light_linking_get_collection(light_obj, link_type)
    mode = light_linking_mode(collection) if collection is not None else "INCLUDE"
    mode_text = "包含模式" if mode == "INCLUDE" else "排除模式"
    try:
        context.workspace.status_text_set(
            f"{light_linking_label(link_type)}：{mode_text} | 点击添加 | Ctrl+点击移除 | Esc/右键：结束"
        )
    except Exception:
        pass


class BetterExperie_OT_LightLinkingClearLinks(bpy.types.Operator):
    bl_idname = "better_experie.light_linking_clear"
    bl_label = "清空链接"
    bl_description = "清空当前灯光的对象链接和集合链接"
    bl_options = {"REGISTER", "UNDO"}

    link_type: EnumProperty(items=LINK_TYPES, default="LIGHT")
    cleanup_mode: EnumProperty(
        name="清理模式",
        items=[
            ("CLEAR_ALL", "清理所有", "清理共享集合，所有引用此集合的灯光都会受影响"),
            ("MAKE_SINGLE_USER", "独立化后清理当前", "复制集合，仅清理当前灯光的副本"),
            ("CANCEL", "取消清理", "不执行清理"),
        ],
        default="CLEAR_ALL",
    )

    def invoke(self, context, event):
        light_obj = context.object
        if light_obj is None:
            return {"CANCELLED"}
        collection = light_linking_get_collection(light_obj, self.link_type)
        if collection is None:
            self.report({"WARNING"}, f"当前灯光没有{light_linking_label(self.link_type)}集合")
            return {"CANCELLED"}
        if collection.users > 1:
            return context.window_manager.invoke_props_dialog(self, width=420)
        return self.execute(context)

    def draw(self, context):
        layout = self.layout
        collection = light_linking_get_collection(context.object, self.link_type)
        if collection is None:
            return
        layout.label(text=f"当前集合被 {collection.users} 处引用,清理共享集合可能影响其他灯光", icon="ERROR")
        layout.prop(self, "cleanup_mode", text="清理模式", expand=True)

    def execute(self, context):
        light_obj = context.object
        if light_obj is None:
            return {"CANCELLED"}
        collection = light_linking_get_collection(light_obj, self.link_type)
        if collection is None:
            self.report({"WARNING"}, f"当前灯光没有{light_linking_label(self.link_type)}集合")
            return {"CANCELLED"}
        if self.cleanup_mode == "CANCEL":
            self.report({"INFO"}, "已取消清理")
            return {"CANCELLED"}
        if self.cleanup_mode == "MAKE_SINGLE_USER" and collection.users > 1:
            try:
                new_collection = collection.copy()
                new_collection.name = f"{collection.name} - {light_obj.name}"
                light_linking_set_collection(light_obj, self.link_type, new_collection)
                collection = new_collection
            except Exception as error:
                print("[Light Linking] 集合独立化失败：", error)
                self.report({"ERROR"}, "集合独立化失败，请查看控制台")
                return {"CANCELLED"}

        removed_objects = 0
        removed_collections = 0
        for obj in list(collection.objects):
            try:
                collection.objects.unlink(obj)
                removed_objects += 1
            except Exception as error:
                print("[Light Linking] 删除对象链接失败：", obj.name, error)
        for child_collection in list(collection.children):
            try:
                collection.children.unlink(child_collection)
                removed_collections += 1
            except Exception as error:
                print("[Light Linking] 删除集合链接失败：", child_collection.name, error)

        light_obj.update_tag()
        light_linking_tag_redraw(context)
        self.report({"INFO"}, f"已清空{light_linking_label(self.link_type)}：{removed_objects} 个对象，{removed_collections} 个集合")
        return {"FINISHED"}


class BetterExperie_OT_LightLinkingChangeAllState(bpy.types.Operator):
    bl_idname = "better_experie.light_linking_change_all_state"
    bl_label = "全部包含/排除"
    bl_description = "批量修改全部链接的包含或排除状态"
    bl_options = {"REGISTER", "UNDO"}

    link_type: EnumProperty(items=LINK_TYPES, default="LIGHT")
    action: EnumProperty(
        items=[
            ("INCLUDE", "全部包含", "将全部链接设为包含"),
            ("EXCLUDE", "全部排除", "将全部链接设为排除"),
            ("INVERT", "翻转链接", "翻转全部链接状态"),
        ],
        default="INCLUDE",
    )

    def execute(self, context):
        light_obj = context.object
        if light_obj is None:
            return {"CANCELLED"}
        collection = light_linking_get_collection(light_obj, self.link_type)
        if collection is None:
            self.report({"WARNING"}, f"当前灯光没有{light_linking_label(self.link_type)}集合")
            return {"CANCELLED"}

        items = light_linking_items(collection)
        if not items:
            self.report({"WARNING"}, f"当前{light_linking_label(self.link_type)}集合为空")
            return {"CANCELLED"}

        changed_count = 0
        for item in items:
            try:
                current_state = item.light_linking.link_state
                if self.action == "INCLUDE":
                    new_state = "INCLUDE"
                elif self.action == "EXCLUDE":
                    new_state = "EXCLUDE"
                else:
                    new_state = "EXCLUDE" if current_state == "INCLUDE" else "INCLUDE"

                if current_state != new_state:
                    item.light_linking.link_state = new_state
                    changed_count += 1
            except Exception as error:
                print("[Light Linking] 修改链接状态失败：", error)

        action_names = {"INCLUDE": "全部包含", "EXCLUDE": "全部排除", "INVERT": "翻转链接"}
        light_obj.update_tag()
        light_linking_tag_redraw(context)
        self.report({"INFO"}, f"{action_names[self.action]}完成：共 {len(items)} 个条目，修改 {changed_count} 个")
        return {"FINISHED"}


class BetterExperie_OT_LightLinkingSmartConvertMode(bpy.types.Operator):
    bl_idname = "better_experie.light_linking_smart_convert_mode"
    bl_label = "智能转换链接模式"
    bl_description = "智能转换当前链接集合的包含或排除模式"
    bl_options = {"REGISTER", "UNDO"}

    link_type: EnumProperty(items=LINK_TYPES, default="LIGHT")
    target_mode: EnumProperty(
        items=[
            ("INCLUDE", "智能转换为包含模式", "清理排除对象，或将全部对象转换为包含"),
            ("EXCLUDE", "智能转换为排除模式", "清理排除对象后，将全部对象转换为排除"),
        ],
        default="INCLUDE",
    )

    def execute(self, context):
        light_obj = context.object
        if light_obj is None:
            return {"CANCELLED"}
        collection = light_linking_get_collection(light_obj, self.link_type)

        if collection is None:
            self.report({"WARNING"}, f"当前灯光没有{light_linking_label(self.link_type)}集合")
            return {"CANCELLED"}

        if not light_linking_items(collection):
            self.report({"WARNING"}, f"当前{light_linking_label(self.link_type)}集合为空")
            return {"CANCELLED"}

        current_mode = light_linking_mode(collection)
        removed_count = 0
        changed_count = 0

        if self.target_mode == "INCLUDE":
            if current_mode == "INCLUDE":
                removed_count = light_linking_remove_exclude_items(collection)
            else:
                changed_count = light_linking_set_all_states(collection, "INCLUDE")

        elif self.target_mode == "EXCLUDE":
            if current_mode == "INCLUDE":
                removed_count = light_linking_remove_exclude_items(collection)
                changed_count = light_linking_set_all_states(collection, "EXCLUDE")

        light_obj.update_tag()
        light_linking_tag_redraw(context)

        mode_text = "包含模式" if self.target_mode == "INCLUDE" else "排除模式"
        self.report({"INFO"}, f"已转换为{mode_text}：移除 {removed_count} 个排除对象，修改 {changed_count} 个对象")
        return {"FINISHED"}


class BetterExperie_OT_LightLinkingContinuousPick(bpy.types.Operator):
    bl_idname = "better_experie.light_linking_continuous_pick"
    bl_label = "吸管拾取"
    bl_description = "在三维视图或大纲中点击对象以添加链接，Ctrl+点击移除，Esc、右键或回车结束"
    bl_options = {"REGISTER", "UNDO"}

    link_type: EnumProperty(items=LINK_TYPES, default="LIGHT")
    _active = None
    _modal_border_handle = None

    def invoke(self, context, event):
        if type(self)._active is not None:
            self.report({"WARNING"}, "已有吸管拾取操作正在运行")
            return {"CANCELLED"}
        if context.object is None:
            return {"CANCELLED"}

        self.light_name = context.object.name
        self.added_count = 0
        self.removed_count = 0
        self.previous_selected_names = [obj.name for obj in context.selected_objects]
        self.previous_active_name = context.view_layer.objects.active.name if context.view_layer.objects.active else ""

        try:
            context.window.cursor_modal_set("EYEDROPPER")
            light_linking_update_status(context, context.object, self.link_type)
            add_modal_border(self, context)
            context.window_manager.modal_handler_add(self)
            type(self)._active = self
            return {"RUNNING_MODAL"}
        except Exception:
            self.teardown(context)
            return {"CANCELLED"}

    def modal(self, context, event):
        try:
            try:
                context.window.cursor_modal_set("EYEDROPPER")
            except Exception:
                pass
            if event.type in {"ESC", "RIGHTMOUSE", "RET", "NUMPAD_ENTER"} and event.value == "PRESS":
                return self.finish(context)

            if event.type == "LEFTMOUSE" and event.value == "PRESS":
                area, region = self.area_region_under_mouse(context, event)
                if area is None or region is None:
                    return {"RUNNING_MODAL"}
                if area.type == "VIEW_3D":
                    self.pick_viewport(context, area, region, event, event.ctrl)
                elif area.type == "OUTLINER":
                    self.pick_outliner(context, area, region, event.ctrl)
                return {"RUNNING_MODAL"}

            return {"PASS_THROUGH"}
        except Exception as error:
            import traceback
            traceback.print_exc()
            self.report({"ERROR"}, str(error))
            self.teardown(context)
            return {"CANCELLED"}

    def area_region_under_mouse(self, context, event):
        mouse_x, mouse_y = event.mouse_x, event.mouse_y
        for area in context.screen.areas:
            if not (area.x <= mouse_x < area.x + area.width and area.y <= mouse_y < area.y + area.height):
                continue
            for region in area.regions:
                if region.type == "WINDOW" and region.x <= mouse_x < region.x + region.width and region.y <= mouse_y < region.y + region.height:
                    return area, region
        return None, None

    def pick_viewport(self, context, area, region, event, remove=False):
        light_obj = bpy.data.objects.get(self.light_name)
        old_selected = [obj.name for obj in context.selected_objects]
        old_active = context.view_layer.objects.active.name if context.view_layer.objects.active else ""
        before = {obj.name for obj in context.selected_objects}
        local_mouse = (event.mouse_x - region.x, event.mouse_y - region.y)

        try:
            with context.temp_override(window=context.window, area=area, region=region):
                bpy.ops.view3d.select(extend=True, deselect=False, toggle=False, location=local_mouse, object=True)

            after = {obj.name for obj in context.selected_objects}
            hit_names = after - before
            active_obj = context.view_layer.objects.active

            if active_obj is not None:
                hit_names.add(active_obj.name)

            for name in hit_names:
                target = bpy.data.objects.get(name)
                if remove:
                    if light_linking_remove_object(light_obj, target, self.link_type):
                        self.removed_count += 1
                else:
                    if light_linking_add_object(context, light_obj, target, self.link_type):
                        self.added_count += 1

        except Exception as error:
            print("[Light Linking] 视图拾取失败：", error)
        finally:
            light_linking_restore_selection(context, old_selected, old_active)
            light_linking_update_status(context, context.object, self.link_type)
            light_linking_tag_redraw(context)

    def pick_outliner(self, context, area, region, remove=False):
        light_obj = bpy.data.objects.get(self.light_name)
        old_selected = [obj.name for obj in context.selected_objects]
        old_active = context.view_layer.objects.active.name if context.view_layer.objects.active else ""
        before = {obj.name for obj in context.selected_objects}

        try:
            with context.temp_override(window=context.window, area=area, region=region):
                bpy.ops.outliner.item_activate("INVOKE_DEFAULT")

            after = {obj.name for obj in context.selected_objects}
            hit_names = after - before
            active_obj = context.view_layer.objects.active

            if active_obj is not None:
                hit_names.add(active_obj.name)

            for name in hit_names:
                target = bpy.data.objects.get(name)
                if remove:
                    if light_linking_remove_object(light_obj, target, self.link_type):
                        self.removed_count += 1
                else:
                    if light_linking_add_object(context, light_obj, target, self.link_type):
                        self.added_count += 1

        except Exception as error:
            print("[Light Linking] Outliner 拾取失败：", error)
        finally:
            light_linking_restore_selection(context, old_selected, old_active)
            light_linking_update_status(context, context.object, self.link_type)
            light_linking_tag_redraw(context)

    def finish(self, context):
        self.teardown(context)
        if self.added_count > 0 or self.removed_count > 0:
            self.report({"INFO"}, f"已添加 {self.added_count} 个，移除 {self.removed_count} 个{light_linking_label(self.link_type)}对象")
            return {"FINISHED"}
        return {"CANCELLED"}

    def teardown(self, context):
        if type(self)._active is self:
            type(self)._active = None
        remove_modal_border(self)
        try:
            context.window.cursor_modal_restore()
            context.workspace.status_text_set(None)
        except Exception:
            pass
        light_linking_restore_selection(context, getattr(self, "previous_selected_names", []), getattr(self, "previous_active_name", ""))
        light_linking_tag_redraw(context)

    def cancel(self, context):
        self.teardown(context)


def _draw_light_linking_panel(layout, context, link_type):
    box = layout.box()

    light_obj = context.object
    collection = light_linking_get_collection(light_obj, link_type) if light_obj is not None else None
    if collection is None:
        include_icon, exclude_icon = "BLANK1", "BLANK1"
    else:
        mode = light_linking_mode(collection)
        if mode == "INCLUDE":
            include_icon, exclude_icon = "KEY_RING_FILLED", "BLANK1"
        else:
            include_icon, exclude_icon = "BLANK1", "KEY_RING_FILLED"

    row = box.row(align=True)
    op = row.operator("better_experie.light_linking_smart_convert_mode", text="切换为包含模式", icon=include_icon)
    op.link_type = link_type
    op.target_mode = "INCLUDE"
    op = row.operator("better_experie.light_linking_smart_convert_mode", text="切换为排除模式", icon=exclude_icon)
    op.link_type = link_type
    op.target_mode = "EXCLUDE"

    row.separator()
    op = row.operator("better_experie.light_linking_continuous_pick", text="吸管拾取", icon="EYEDROPPER")
    op.link_type = link_type


def _draw_light_linking_context_menu(layout, link_type):
    layout.separator()
    op = layout.operator("better_experie.light_linking_change_all_state", text="全部包含", icon="CHECKMARK")
    op.link_type = link_type
    op.action = "INCLUDE"
    op = layout.operator("better_experie.light_linking_change_all_state", text="全部排除", icon="X")
    op.link_type = link_type
    op.action = "EXCLUDE"
    op = layout.operator("better_experie.light_linking_change_all_state", text="翻转链接", icon="FILE_REFRESH")
    op.link_type = link_type
    op.action = "INVERT"
    layout.separator()
    op = layout.operator("better_experie.light_linking_clear", text="清空链接", icon="TRASH")
    op.link_type = link_type


def draw_light_linking_tools(self, context):
    _draw_light_linking_panel(self.layout, context, "LIGHT")


def draw_shadow_linking_tools(self, context):
    _draw_light_linking_panel(self.layout, context, "SHADOW")


def draw_light_linking_context_menu(self, context):
    _draw_light_linking_context_menu(self.layout, "LIGHT")


def draw_shadow_linking_context_menu(self, context):
    _draw_light_linking_context_menu(self.layout, "SHADOW")


classes = (
    BetterExperie_OT_LightLinkingClearLinks,
    BetterExperie_OT_LightLinkingChangeAllState,
    BetterExperie_OT_LightLinkingContinuousPick,
    BetterExperie_OT_LightLinkingSmartConvertMode,
)

# 核心面板（4.5+ 恒存在），注入/注销均做防御处理
PANEL_TARGETS = [
    ("OBJECT_PT_light_linking", draw_light_linking_tools),
    ("OBJECT_PT_shadow_linking", draw_shadow_linking_tools),
    ("OBJECT_MT_light_linking_context_menu", draw_light_linking_context_menu),
    ("OBJECT_MT_shadow_linking_context_menu", draw_shadow_linking_context_menu),
]


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    for panel_name, draw_func in PANEL_TARGETS:
        panel_cls = getattr(bpy.types, panel_name, None)
        if panel_cls is None:
            continue
        try:
            panel_cls.append(draw_func)
        except Exception:
            pass


def unregister():
    for panel_name, draw_func in PANEL_TARGETS:
        panel_cls = getattr(bpy.types, panel_name, None)
        if panel_cls is None:
            continue
        try:
            panel_cls.remove(draw_func)
        except Exception:
            pass
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
