# 灯光链接 / 阴影链接工具：向原生灯光数据面板与右键菜单注入批量操作

import bpy
from bpy.props import BoolProperty, EnumProperty

from ...utils.modal_border import add_modal_border, remove_modal_border

LINK_TYPES = [
    ("LIGHT", "Light Linking", "Operate on Light Linking"),
    ("SHADOW", "Shadow Linking", "Operate on Shadow Linking"),
]

# 吸管拾取“自动子级”开关（Scene 属性，随 .blend 保存）
AUTO_CHILDREN_PROP = "better_experie_light_linking_auto_children"


def light_linking_label(link_type):
    return "灯光链接" if link_type == "LIGHT" else "阴影链接"


def light_linking_auto_children_enabled(context):
    scene = getattr(context, "scene", None)
    if scene is None:
        return False
    return bool(getattr(scene, AUTO_CHILDREN_PROP, False))


def light_linking_expand_targets(obj, include_children):
    """把拾取到的对象展开为“自身 + 递归子级”；关闭自动子级时只返回自身"""
    if obj is None:
        return []
    targets = [obj]
    if not include_children:
        return targets
    seen = {obj.name}
    try:
        for child in obj.children_recursive:
            if child.name in seen:
                continue
            seen.add(child.name)
            targets.append(child)
    except Exception as error:
        print("[Light Linking] 展开子级失败：", error)
    return targets


def light_linking_collect_targets(picked_objects, include_children):
    """多个拾取对象合并展开，共用子级只出现一次（父级保持在前）"""
    targets = []
    seen = set()
    for obj in picked_objects:
        for target in light_linking_expand_targets(obj, include_children):
            if target.name in seen:
                continue
            seen.add(target.name)
            targets.append(target)
    return targets


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
    removed_count = 0
    # 收集需要删除的索引（按 collection_objects 的顺序）
    exclude_indices = [
        i for i, item in enumerate(light_linking_collection_objects(collection))
        if item.light_linking.link_state == "EXCLUDE"
    ]
    # 从后往前删，避免删除后索引错位
    real_objects = list(collection.objects)
    for i in sorted(exclude_indices, reverse=True):
        if i < len(real_objects):
            obj = real_objects[i]
            try:
                collection.objects.unlink(obj)
                removed_count += 1
            except Exception as error:
                print("[Light Linking] 移除排除对象失败：", obj.name, error)

    # 子集合同理
    exclude_child_indices = [
        i for i, item in enumerate(light_linking_collection_children(collection))
        if item.light_linking.link_state == "EXCLUDE"
    ]

    real_children = list(collection.children)
    for i in sorted(exclude_child_indices, reverse=True):
        if i < len(real_children):
            child = real_children[i]
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
        # CollectionObject 没有 object/name 引用，只能按 collection.objects 的索引对应定位新条目
        object_names = [item.name for item in collection.objects]
        try:
            index = object_names.index(obj.name)
        except ValueError:
            index = -1
        items = list(light_linking_collection_objects(collection))
        if 0 <= index < len(items):
            items[index].light_linking.link_state = link_state
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
    auto_text = " | 自动子级：开" if light_linking_auto_children_enabled(context) else ""
    try:
        context.workspace.status_text_set(
            f"{light_linking_label(link_type)}：{mode_text}{auto_text} | 点击添加 | Ctrl+点击移除 | Esc/右键：结束"
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
        self.added_child_count = 0
        self.removed_child_count = 0
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
                if bpy.data.objects.get(self.light_name) is None:
                    self.report({"WARNING"}, "灯光对象已不存在，吸管拾取结束")
                    return self.finish(context)
                if area.type == "VIEW_3D":
                    self.pick_viewport(context, area, region, event)
                elif area.type == "OUTLINER":
                    self.pick_outliner(context, area, region, event)
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

    def pick_viewport(self, context, area, region, event):
        local_mouse = (event.mouse_x - region.x, event.mouse_y - region.y)

        def select_operator():
            bpy.ops.view3d.select(extend=False, deselect=False, toggle=False, location=local_mouse, object=True)

        self.pick_objects(context, area, region, event, select_operator)

    def pick_outliner(self, context, area, region, event):
        def select_operator():
            bpy.ops.outliner.item_activate("INVOKE_DEFAULT")

        self.pick_objects(context, area, region, event, select_operator)

    def pick_objects(self, context, area, region, event, select_operator):
        light_obj = bpy.data.objects.get(self.light_name)
        if light_obj is None:
            return
        # 编辑模式等非物体模式下无法可靠改写对象选择，直接忽略本次点击
        if context.mode != "OBJECT":
            return
        old_selected = [obj.name for obj in context.selected_objects]
        old_active = context.view_layer.objects.active.name if context.view_layer.objects.active else ""
        picked = []
        try:
            # 先清空选择：点空白处时结果为空，不会把上一次的激活对象误当成命中目标
            light_linking_restore_selection(context, [], "")
            with context.temp_override(window=context.window, area=area, region=region):
                select_operator()
            picked = list(context.selected_objects)
        except Exception as error:
            print("[Light Linking] 拾取失败：", error)
        finally:
            light_linking_restore_selection(context, old_selected, old_active)

        self.apply_picked(context, light_obj, picked, event.ctrl)
        light_linking_update_status(context, light_obj, self.link_type)
        light_linking_tag_redraw(context)

    def apply_picked(self, context, light_obj, picked, remove):
        if not picked:
            return
        include_children = light_linking_auto_children_enabled(context)
        picked_names = {obj.name for obj in picked}

        for target in light_linking_collect_targets(picked, include_children):
            is_child = target.name not in picked_names
            if remove:
                if light_linking_remove_object(light_obj, target, self.link_type):
                    self.removed_count += 1
                    if is_child:
                        self.removed_child_count += 1
            elif light_linking_add_object(context, light_obj, target, self.link_type):
                self.added_count += 1
                if is_child:
                    self.added_child_count += 1

    def finish(self, context):
        auto_children = light_linking_auto_children_enabled(context)
        self.teardown(context)
        if self.added_count > 0 or self.removed_count > 0:
            text = f"已添加 {self.added_count} 个，移除 {self.removed_count} 个{light_linking_label(self.link_type)}对象"
            if auto_children and (self.added_child_count or self.removed_child_count):
                text += f"（其中子级：添加 {self.added_child_count} 个，移除 {self.removed_child_count} 个）"
            self.report({"INFO"}, text)
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




class BetterExperie_OT_LightLinkingCopyToOther(bpy.types.Operator):
    bl_idname = "better_experie.light_linking_copy_to_other"
    bl_label = "复制链接到另一边"
    bl_description = ("把所选物体的灯光链接复制到阴影链接（或反向）\n"
                      "默认两边共用同一个集合；按住 Alt 点击则复制一份独立集合")
    bl_options = {"REGISTER", "UNDO"}

    direction: EnumProperty(
        items=[
            ("LIGHT_TO_SHADOW", "灯光 → 阴影", "把灯光链接复制给阴影链接"),
            ("SHADOW_TO_LIGHT", "阴影 → 灯光", "把阴影链接复制给灯光链接"),
        ],
        default="LIGHT_TO_SHADOW",
    )
    make_copy: BoolProperty(
        name="独立副本",
        description="复制一份独立集合，而不是与源共用同一个集合",
        default=False,
    )

    def invoke(self, context, event):
        # 面板按钮走 INVOKE_DEFAULT，这里能拿到真实点击事件
        # 默认（不按 Alt）= 共享；按住 Alt = 独立副本
        if not self.properties.is_property_set("make_copy"):
            self.make_copy = bool(getattr(event, "alt", False))
        return self.execute(context)

    def execute(self, context):
        src_type = "LIGHT" if self.direction == "LIGHT_TO_SHADOW" else "SHADOW"
        dst_type = "SHADOW" if self.direction == "LIGHT_TO_SHADOW" else "LIGHT"

        targets = list(context.selected_objects) or ([context.object] if context.object else [])
        if not targets:
            self.report({"WARNING"}, "没有选中物体")
            return {"CANCELLED"}

        done = synced = empty = failed = 0
        for obj in targets:
            src = light_linking_get_collection(obj, src_type)
            if src is None:
                empty += 1
                continue
            dst = light_linking_get_collection(obj, dst_type)
            if dst is src:
                synced += 1
                continue
            try:
                light_linking_set_collection(obj, dst_type, src.copy() if self.make_copy else src)
                obj.update_tag()
                done += 1
            except Exception as error:
                failed += 1
                print("[Light Linking] 复制失败：", obj.name, error)

        light_linking_tag_redraw(context)
        mode_text = "独立副本" if self.make_copy else "共用同一集合"
        msg = f"{light_linking_label(src_type)} → {light_linking_label(dst_type)}（{mode_text}）：{done} 个物体"
        if synced:
            msg += f"，{synced} 个已同步"
        if empty:
            msg += f"，{empty} 个无源集合已跳过"
        if failed:
            msg += f"，{failed} 个失败"
        self.report({"WARNING"} if failed else {"INFO"}, msg)
        return {"FINISHED"}
        
        
        
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
    row.use_property_decorate = False
    
    op = row.operator(
        "better_experie.light_linking_copy_to_other",
        text="" if link_type == "LIGHT" else "",
        icon="SORT_ASC" if link_type == "LIGHT" else "SORT_DESC",
    )
    
    op = row.operator("better_experie.light_linking_smart_convert_mode", text="切换为包含模式", icon=include_icon)
    op.link_type = link_type
    op.target_mode = "INCLUDE"
    op = row.operator("better_experie.light_linking_smart_convert_mode", text="切换为排除模式", icon=exclude_icon)
    op.link_type = link_type
    op.target_mode = "EXCLUDE"

    row.separator()
    op = row.operator("better_experie.light_linking_continuous_pick", text="吸管拾取", icon="EYEDROPPER")
    op.link_type = link_type
    scene = getattr(context, "scene", None)
    if scene is not None and hasattr(scene, AUTO_CHILDREN_PROP):
        row.prop(scene, AUTO_CHILDREN_PROP, text="", icon="PARTICLES", toggle=True)


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
    BetterExperie_OT_LightLinkingCopyToOther, 
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
    # Scene 属性：随 .blend 保存，热重载时先清掉旧属性避免残留
    try:
        del bpy.types.Scene.better_experie_light_linking_auto_children
    except (AttributeError, TypeError):
        pass
    bpy.types.Scene.better_experie_light_linking_auto_children = BoolProperty(
        name="自动子级",
        description="开启后，使用吸管拾取会连同对象的所有子级一起添加或移除",
        default=False,
    )
    for panel_name, draw_func in PANEL_TARGETS:
        panel_cls = getattr(bpy.types, panel_name, None)
        if panel_cls is None:
            continue
        # 先摘再挂：热重载/重复 register 不会把同一个 draw 挂两遍
        try:
            panel_cls.remove(draw_func)
        except Exception:
            pass
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
    try:
        del bpy.types.Scene.better_experie_light_linking_auto_children
    except (AttributeError, TypeError):
        pass
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
