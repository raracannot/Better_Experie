# 集合可见性覆盖工具

import bpy


def _refresh_all_drivers(scene):
    for obj in bpy.data.objects:
        if obj.animation_data and obj.animation_data.drivers:
            for prop in ["hide_viewport", "hide_render"]:
                for d in obj.animation_data.drivers:
                    if d.data_path == prop:
                        if len(d.driver.variables) > 0:
                            target = d.driver.variables[0].targets[0]
                            if target.id == scene and 'better_experie_collection_override_items' in target.data_path:
                                obj.driver_remove(prop)
                                break

    for i, item in enumerate(scene.better_experie_collection_override_items):
        if item.override_enable and item.collection_name:
            col = bpy.data.collections.get(item.collection_name)
            if col:
                for obj in col.objects:
                    for prop in ["hide_viewport", "hide_render"]:
                        d = obj.driver_add(prop)
                        d.driver.type = 'SUM'

                        var = d.driver.variables.get("var") or d.driver.variables.new()
                        var.name = "var"
                        var.type = 'SINGLE_PROP'

                        target = var.targets[0]
                        target.id_type = 'SCENE'
                        target.id = scene
                        target.data_path = f'better_experie_collection_override_items[{i}].{prop}'


def _on_property_update(self, context):
    _refresh_all_drivers(context.scene)


class BetterExperie_CollectionOverrideItem(bpy.types.PropertyGroup):
    collection_name: bpy.props.StringProperty(
        name="集合名", description="输入集合名称", update=_on_property_update)
    override_enable: bpy.props.BoolProperty(
        name="覆盖", description="是否覆盖该集合子项的可见性", default=False, update=_on_property_update)
    hide_viewport: bpy.props.BoolProperty(
        name="在视图禁用", description="在视图中隐藏集合的子集对象\n可设置关键帧", default=False)
    hide_render: bpy.props.BoolProperty(
        name="在渲染禁用", description="在渲染中隐藏集合的子集对象\n可设置关键帧", default=False)


class BetterExperie_OT_AddCollectionOverride(bpy.types.Operator):
    bl_idname = "better_experie.add_collection_override"
    bl_label = "添加集合"
    bl_description = "添加一个新的集合可见性覆盖条目"

    def execute(self, context):
        context.scene.better_experie_collection_override_items.add()
        return {'FINISHED'}


class BetterExperie_OT_RemoveCollectionOverride(bpy.types.Operator):
    bl_idname = "better_experie.remove_collection_override"
    bl_label = "删除"
    bl_description = "删除此集合可见性覆盖条目"

    index: bpy.props.IntProperty()

    def execute(self, context):
        context.scene.better_experie_collection_override_items.remove(self.index)
        _refresh_all_drivers(context.scene)
        return {'FINISHED'}


class BetterExperie_OT_RefreshCollectionOverride(bpy.types.Operator):
    bl_idname = "better_experie.refresh_collection_override"
    bl_label = "刷新绑定 (若集合内新增了对象请点击)"
    bl_description = "手动刷新所有驱动器绑定"

    def execute(self, context):
        _refresh_all_drivers(context.scene)
        self.report({'INFO'}, "集合可见性驱动器已刷新")
        return {'FINISHED'}


class BETTER_EXPERIE_PT_collection_visibility(bpy.types.Panel):
    bl_label = "集合可见性覆盖"
    bl_idname = "BETTER_EXPERIE_PT_collection_visibility"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = 'view_layer'
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        for i, item in enumerate(scene.better_experie_collection_override_items):
            row = layout.row(align=True)

            icon_override = 'PLAY' if item.override_enable else 'PAUSE'
            row.prop(item, "override_enable", text="", icon=icon_override, toggle=True)

            row.prop_search(item, "collection_name", bpy.data, "collections", text="")

            row.separator()
            icon_view = 'RESTRICT_VIEW_ON' if item.hide_viewport else 'RESTRICT_VIEW_OFF'
            row.prop(item, "hide_viewport", text="", icon=icon_view)

            icon_render = 'RESTRICT_RENDER_ON' if item.hide_render else 'RESTRICT_RENDER_OFF'
            row.prop(item, "hide_render", text="", icon=icon_render)

            row.separator()
            remove_op = row.operator("better_experie.remove_collection_override", text="", icon='X')
            remove_op.index = i

        layout.separator()
        row = layout.row()
        row.operator("better_experie.add_collection_override", text="添加集合", icon='ADD')
        row.operator("better_experie.refresh_collection_override", text="", icon='FILE_REFRESH')


classes = (
    BetterExperie_CollectionOverrideItem,
    BetterExperie_OT_AddCollectionOverride,
    BetterExperie_OT_RemoveCollectionOverride,
    BetterExperie_OT_RefreshCollectionOverride,
    BETTER_EXPERIE_PT_collection_visibility,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.better_experie_collection_override_items = bpy.props.CollectionProperty(
        type=BetterExperie_CollectionOverrideItem)


def unregister():
    if hasattr(bpy.context, "scene"):
        for obj in bpy.data.objects:
            if obj.animation_data and obj.animation_data.drivers:
                for prop in ["hide_viewport", "hide_render"]:
                    for d in obj.animation_data.drivers:
                        if d.data_path == prop and len(d.driver.variables) > 0:
                            target = d.driver.variables[0].targets[0]
                            if 'better_experie_collection_override_items' in target.data_path:
                                obj.driver_remove(prop)
                                break

    del bpy.types.Scene.better_experie_collection_override_items
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
