# 修改器批量处理工具

import bpy


def _filter_modifier(modifier_filter, modifier):
    if modifier_filter == 'ALL':
        return True
    return modifier_filter and modifier.type == modifier_filter


def _get_modifier_enum_items(self, context):
    items = [("ALL", "【所有】全部修改器", "处理所有修改器")]
    items.extend([
        (item.identifier, item.name, item.description)
        for item in bpy.types.Modifier.bl_rna.properties['type'].enum_items
        if item.identifier != 'DUMMY'
    ])
    return items


class BetterExperie_OT_BatchProcessModifiers(bpy.types.Operator):
    bl_idname = "better_experie.batch_process_modifiers"
    bl_label = "批量处理修改器"
    bl_description = "点击弹出处理选项（支持Shift/Ctrl快捷键预设）"
    bl_options = {'REGISTER', 'UNDO'}

    modifier_filter: bpy.props.EnumProperty(
        items=_get_modifier_enum_items,
        name="修改器过滤",
        description="设置批量处理所适用的修改器范围"
    )

    action_type: bpy.props.EnumProperty(
        items=[
            ('APPLY', "应用 (Apply)", "批量应用修改器"),
            ('REMOVE', "移除 (Remove)", "批量移除修改器"),
            ('DISABLE', "屏蔽 (Disable)", "批量禁用修改器在视图和渲染中的显示"),
            ('ENABLE', "启用 (Enable)", "批量启用修改器在视图和渲染中的显示"),
        ],
        name="处理方式",
        default='APPLY'
    )

    target_scope: bpy.props.EnumProperty(
        items=[
            ('SELECTED', "选中对象", "仅处理当前选中的对象"),
            ('ALL', "场景所有对象", "处理当前场景中的所有对象"),
        ],
        name="作用范围",
        default='SELECTED'
    )

    remove_invisible_only: bpy.props.BoolProperty(
        name="仅移除不可见修改器",
        description="勾选后，仅移除在视图中被隐藏的修改器",
        default=False
    )

    def invoke(self, context, event):
        self.target_scope = 'ALL' if event.shift else 'SELECTED'
        self.remove_invisible_only = event.ctrl
        if event.ctrl:
            self.action_type = 'REMOVE'

        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        layout = self.layout

        layout.prop(self, "modifier_filter")
        layout.separator()

        layout.prop(self, "action_type")
        layout.prop(self, "target_scope")

        if self.action_type == 'REMOVE':
            layout.prop(self, "remove_invisible_only")

    def execute(self, context):
        modifier_filter = self.modifier_filter
        objects = context.view_layer.objects if self.target_scope == 'ALL' else context.selected_objects

        original_mode = context.active_object.mode if context.active_object else 'OBJECT'
        original_active_obj = context.active_object

        if self.action_type == 'APPLY' and original_mode == 'EDIT':
            bpy.ops.object.mode_set(mode='OBJECT')

        count = 0
        failed_objects = []

        for obj in objects:
            if not obj.modifiers:
                continue

            if self.action_type == 'APPLY':
                try:
                    bpy.context.view_layer.objects.active = obj
                    for modifier in obj.modifiers:
                        if _filter_modifier(modifier_filter, modifier):
                            if modifier.show_viewport:
                                bpy.ops.object.modifier_apply(modifier=modifier.name)
                            else:
                                bpy.ops.object.modifier_remove(modifier=modifier.name)
                    count += 1
                except Exception as e:
                    failed_objects.append(obj.name)
                    self.report({'WARNING'}, f"对象 {obj.name} 应用修改器失败: {str(e)}")

            elif self.action_type == 'REMOVE':
                for modifier in obj.modifiers[:]:
                    if _filter_modifier(modifier_filter, modifier):
                        if self.remove_invisible_only and modifier.show_viewport:
                            continue
                        obj.modifiers.remove(modifier)
                        count += 1

            elif self.action_type == 'DISABLE':
                for mod in obj.modifiers:
                    if _filter_modifier(modifier_filter, mod):
                        mod.show_viewport = False
                        mod.show_render = False
                        count += 1

            elif self.action_type == 'ENABLE':
                for mod in obj.modifiers:
                    if _filter_modifier(modifier_filter, mod):
                        mod.show_viewport = True
                        mod.show_render = True
                        count += 1

        if self.action_type == 'APPLY':
            if original_active_obj:
                bpy.context.view_layer.objects.active = original_active_obj
            if original_mode == 'EDIT':
                bpy.ops.object.mode_set(mode='EDIT')

            self.report({'INFO'}, f"成功应用 {count} 个对象，失败 {len(failed_objects)} 个")
            if failed_objects:
                for obj in context.scene.objects:
                    obj.select_set(obj.name in failed_objects)
        else:
            action_names = {'REMOVE': '移除', 'DISABLE': '屏蔽', 'ENABLE': '启用'}
            self.report({'INFO'}, f"成功{action_names[self.action_type]} {count} 个修改器")

        return {'FINISHED'}



classes = (
    BetterExperie_OT_BatchProcessModifiers,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
