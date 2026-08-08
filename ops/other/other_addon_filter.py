# 工作区插件过滤与预设管理

import bpy
import addon_utils

_ADDON_MODULE = __name__.split('.')[0]


class BetterExperie_PropertyGroup_AddonFilterPreset(bpy.types.PropertyGroup):
    name: bpy.props.StringProperty(name="预设名称", default="新预设")
    addons_list: bpy.props.StringProperty(name="插件列表")


class BetterExperie_OT_ToggleAddonFilter(bpy.types.Operator):
    bl_idname = "better_experie.toggle_addon_filter"
    bl_label = "切换过滤"
    bl_description = "切换工作区插件过滤的开关状态，开启时自动保留自身"
    bl_options = {'REGISTER'}

    def execute(self, context):
        workspace = context.workspace
        workspace.use_filter_by_owner = not workspace.use_filter_by_owner

        if workspace.use_filter_by_owner:
            current_owners = {owner.name for owner in workspace.owner_ids}
            if _ADDON_MODULE not in current_owners:
                try:
                    workspace.owner_ids.new(_ADDON_MODULE)
                except Exception as e:
                    print(f"无法保留自身插件: {e}")

        return {'FINISHED'}


class BetterExperie_OT_FlipAddonFilter(bpy.types.Operator):
    bl_idname = "better_experie.flip_addon_filter"
    bl_label = "反转过滤"
    bl_description = "翻转工作区插件过滤的勾选状态"
    bl_options = {'REGISTER'}

    def execute(self, context):
        workspace = context.workspace
        workspace.use_filter_by_owner = True
        enabled_addons = [mod.__name__ for mod in addon_utils.modules() if addon_utils.check(mod.__name__)[1]]
        current_owners = {owner.name for owner in workspace.owner_ids}
        while workspace.owner_ids:
            workspace.owner_ids.remove(workspace.owner_ids[0])

        for addon in enabled_addons:
            if addon not in current_owners:
                try:
                    workspace.owner_ids.new(addon)
                except Exception as e:
                    print(f"无法添加插件 {addon}: {e}")

        current_active_owners = {owner.name for owner in workspace.owner_ids}
        if _ADDON_MODULE not in current_active_owners:
            try:
                workspace.owner_ids.new(_ADDON_MODULE)
            except Exception as e:
                print(f"无法保留自身插件: {e}")

        return {'FINISHED'}


class BetterExperie_OT_SaveAddonFilterPreset(bpy.types.Operator):
    bl_idname = "better_experie.save_addon_filter_preset"
    bl_label = "保存预设"
    bl_description = "保留一份当前开关状态，作为预设到场景属性"
    bl_options = {'REGISTER'}

    def execute(self, context):
        workspace = context.workspace
        scene = context.scene
        current_owners = [owner.name for owner in workspace.owner_ids]

        new_preset = scene.better_experie_addon_filter_presets.add()
        new_preset.name = f"预设 {len(scene.better_experie_addon_filter_presets)}"
        new_preset.addons_list = ",".join(current_owners)

        return {'FINISHED'}


class BetterExperie_OT_ApplyAddonFilterPreset(bpy.types.Operator):
    bl_idname = "better_experie.apply_addon_filter_preset"
    bl_label = "应用"
    bl_description = "应用此预设的插件状态"
    bl_options = {'REGISTER'}

    preset_index: bpy.props.IntProperty()

    def execute(self, context):
        workspace = context.workspace
        scene = context.scene
        if self.preset_index < 0 or self.preset_index >= len(scene.better_experie_addon_filter_presets):
            return {'CANCELLED'}

        preset = scene.better_experie_addon_filter_presets[self.preset_index]
        addons_to_enable = preset.addons_list.split(",") if preset.addons_list else []
        workspace.use_filter_by_owner = True

        while workspace.owner_ids:
            workspace.owner_ids.remove(workspace.owner_ids[0])

        for addon in addons_to_enable:
            if addon:
                try:
                    workspace.owner_ids.new(addon)
                except Exception:
                    pass

        current_active_owners = {owner.name for owner in workspace.owner_ids}
        if _ADDON_MODULE not in current_active_owners:
            try:
                workspace.owner_ids.new(_ADDON_MODULE)
            except Exception:
                pass

        return {'FINISHED'}


class BetterExperie_OT_DeleteAddonFilterPreset(bpy.types.Operator):
    bl_idname = "better_experie.delete_addon_filter_preset"
    bl_label = "删除"
    bl_description = "删除对应的预设"
    bl_options = {'REGISTER'}

    preset_index: bpy.props.IntProperty()

    def execute(self, context):
        scene = context.scene
        if 0 <= self.preset_index < len(scene.better_experie_addon_filter_presets):
            scene.better_experie_addon_filter_presets.remove(self.preset_index)
        return {'FINISHED'}


def _draw_addon_filter_panel(self, context):
    layout = self.layout
    scene = context.scene
    filter_enabled = context.workspace.use_filter_by_owner

    row = layout.row(align=True)
    row.operator("better_experie.toggle_addon_filter",
                 text="关闭过滤" if filter_enabled else "启用过滤",
                 icon='FILTER')
    row.operator("better_experie.flip_addon_filter", text="", icon='UV_SYNC_SELECT')
    row.operator("better_experie.save_addon_filter_preset", text="", icon='FILE_TICK')

    if len(scene.better_experie_addon_filter_presets) > 0:
        box = layout.box()
        for i, preset in enumerate(scene.better_experie_addon_filter_presets):
            row = box.row(align=True)
            row.prop(preset, "name", text="")
            op_apply = row.operator("better_experie.apply_addon_filter_preset", text="应用")
            op_apply.preset_index = i
            op_del = row.operator("better_experie.delete_addon_filter_preset", text="", icon='X')
            op_del.preset_index = i


classes = (
    BetterExperie_PropertyGroup_AddonFilterPreset,
    BetterExperie_OT_ToggleAddonFilter,
    BetterExperie_OT_FlipAddonFilter,
    BetterExperie_OT_SaveAddonFilterPreset,
    BetterExperie_OT_ApplyAddonFilterPreset,
    BetterExperie_OT_DeleteAddonFilterPreset,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    bpy.types.Scene.better_experie_addon_filter_presets = bpy.props.CollectionProperty(
        type=BetterExperie_PropertyGroup_AddonFilterPreset)
    
    #某些第三方N面板优化插件会把 WORKSPACE_PT_addons 这个面板移除掉然后自己实现，我们需要做防御性兼容
    if hasattr(bpy.types, "WORKSPACE_PT_addons"):
        bpy.types.WORKSPACE_PT_addons.append(_draw_addon_filter_panel)


def unregister():
    if hasattr(bpy.types, "WORKSPACE_PT_addons"):
        bpy.types.WORKSPACE_PT_addons.remove(_draw_addon_filter_panel)
    del bpy.types.Scene.better_experie_addon_filter_presets

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
