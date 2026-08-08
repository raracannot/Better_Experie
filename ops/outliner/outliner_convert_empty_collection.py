# 空物体/集合 层级转换

import bpy

def getChildren(obj_parent):
    children_list = []
    for obj in bpy.data.objects:
        if obj.parent == obj_parent:
            children_list.append(obj)
    return children_list

def is_referenced_by_modifier(empty_obj):
    for obj in bpy.data.objects:
        for mod in obj.modifiers:
            for attr in dir(mod):
                if getattr(mod, attr) == empty_obj:
                    return True
    return False


class BetterExperie_OT_EmptiesToCollections(bpy.types.Operator):
    bl_idname = 'better_experie.empties_to_collections'
    bl_label = "空对象转集合"
    bl_description = "将空对象层级结构转换为集合层级结构\n\n常用于将外部导入的模型层集转换为blender层级"
    bl_options = {"REGISTER", "UNDO"}

    apply_scale: bpy.props.BoolProperty(
        name="是否应用缩放",
        description="是否对选中对象应用缩放，建议默认勾选",
        default=True)
    auto_independent: bpy.props.BoolProperty(
        name="是否自动独立化",
        description="是否对多用户对象进行独立化处理，建议默认勾选",
        default=True)

    def invoke(self, context, event):
        wm = context.window_manager
        return wm.invoke_props_dialog(self)

    def execute(self, context):
        selected_obj = []
        if len(bpy.context.selected_objects) == 1:
            root_parent = bpy.context.selected_objects[0]

            def collect_objects(obj):
                selected_obj.append(obj)
                for child in getChildren(obj):
                    collect_objects(child)
            collect_objects(root_parent)
        elif len(bpy.context.selected_objects) == 0:
            for obj in bpy.context.scene.objects:
                selected_obj.append(obj)
        elif len(bpy.context.selected_objects) > 1:
            for root_obj in bpy.context.selected_objects:
                if root_obj.type == 'EMPTY':
                    def collect_objects(obj):
                        if obj in selected_obj:
                            return
                        selected_obj.append(obj)
                        for child in getChildren(obj):
                            collect_objects(child)
                    collect_objects(root_obj)
                else:
                    selected_obj.append(root_obj)
        # 处理多用户数据块（如果需要自动独立化）
        if self.auto_independent:
            for obj in selected_obj:
                if obj.data and obj.data.users > 1:
                    new_data = obj.data.copy()
                    obj.data = new_data
        # 应用缩放（如果需要）
        if self.apply_scale:
            scaled_objects_count = 0
            for obj in selected_obj:
                if obj.type == 'MESH':
                    if self.auto_independent and obj.data.users > 1:
                        obj.data = obj.data.copy()
                    scaled_objects_count += 1
            # 切换到物体模式，确保操作可以正常进行
            if bpy.context.active_object and bpy.context.active_object.mode != 'OBJECT':
                bpy.ops.object.mode_set(mode='OBJECT')
            # 应用缩放
            try:
                bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
                self.report({'INFO'}, f"成功应用了 {scaled_objects_count} 个对象的缩放")
            except RuntimeError as e:
                self.report({'ERROR'}, f"应用缩放时出错: {str(e)}")

        bpy.ops.object.select_all(action='DESELECT')
        # 创建选择集
        obj_to_clean = []
        for obj in selected_obj:
            if obj.type == "EMPTY":
                obj_to_clean.append(obj)
                obj.select_set(True)

        # 创建关于整个场景中集合层级结构的字典：
        coll_from_empty = {}
        for obj in selected_obj:
            if obj.type == "EMPTY":
                if obj.name in bpy.data.collections.keys():
                    bpy.data.collections.remove(bpy.data.collections[obj.name])
                if obj.name not in bpy.data.collections.keys():
                    bpy.data.collections.new(obj.name)
                coll = bpy.data.collections[obj.name]
                coll_from_empty[obj] = coll

        # 构建集合层级结构
        for obj, coll in coll_from_empty.items():
            parent = coll_from_empty.get(obj.parent)
            if parent:
                parent.children.link(coll)
            else:
                bpy.context.scene.collection.children.link(coll)

        # 取消链接场景中所有选定的对象
        for obj in selected_obj:
            for col in obj.users_collection[:]:
                col.objects.unlink(obj)

        # 将对象放入正确的集合中
        for obj in selected_obj:
            if obj.type != 'EMPTY':
                if obj.parent in coll_from_empty:
                    coll = coll_from_empty[obj.parent]
                    coll.objects.link(obj)
                else:
                    bpy.context.scene.collection.objects.link(obj)

        # 移除所有原先的带层级的空物体
        for obj in selected_obj:
            if obj.type == "EMPTY" and getChildren(obj):
                bpy.data.objects.remove(obj)
        self.report({'INFO'}, f"已完成{len(selected_obj)}个对象的空对象转集合操作")
        return {"FINISHED"}


class BetterExperie_OT_CollectionsToEmpties(bpy.types.Operator):
    bl_idname = 'better_experie.collections_to_empties'
    bl_label = "集合转空对象"
    bl_description = "将集合层级结构转换为空对象层级结构\n\n可用于将blender层级导出外部模型前的准备"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        bpy.ops.object.select_all(action='DESELECT')
        master_collection = bpy.context.scene.collection

        def check_and_unexclude(layer_collection):
            if layer_collection.exclude:
                layer_collection.exclude = False
            for child in layer_collection.children:
                check_and_unexclude(child)

        view_layer = bpy.context.view_layer
        check_and_unexclude(view_layer.layer_collection)

        while True:
            instance_objects = [obj for obj in bpy.data.objects if obj.instance_type == 'COLLECTION']
            if not instance_objects:
                break
            for obj in instance_objects:
                if obj.name not in context.view_layer.objects:
                    context.collection.objects.link(obj)
                obj.select_set(True)
            bpy.ops.object.duplicates_make_real()
            bpy.ops.object.select_all(action='DESELECT')

        selected_collections = [
            id for id in context.selected_ids
            if isinstance(id, bpy.types.Collection) and id != master_collection
        ]
        if not selected_collections:
            selected_collections = list(master_collection.children)

        collection_hierarchy = {}
        def collect_collections(collection, parent=None):
            collection_hierarchy[collection] = []
            for sub_collection in collection.children:
                collection_hierarchy[collection].append(sub_collection)
                collect_collections(sub_collection, collection)
        for col in selected_collections:
            collect_collections(col)

        # 创建空对象字典，用于存储集合对应的空对象
        empty_objects = {}
        for collection in collection_hierarchy.keys():
            empty_obj = bpy.data.objects.new(collection.name, None)
            master_collection.objects.link(empty_obj)
            empty_objects[collection] = empty_obj

        # 构建空对象的父子层级关系
        for collection, children in collection_hierarchy.items():
            parent_empty = empty_objects.get(collection)
            for child_collection in children:
                child_empty = empty_objects.get(child_collection)
                if parent_empty and child_empty:
                    child_empty.parent = parent_empty

        # 将集合内的对象移动和绑定到对应的空对象下
        for collection, empty_obj in empty_objects.items():
            for obj in collection.objects:
                if obj not in empty_objects.values():
                    for col in obj.users_collection:
                        col.objects.unlink(obj)
                    empty_obj.users_collection[0].objects.link(obj)
                    obj.parent = empty_obj

        # 移除所有原先的集合
        collections_to_remove = list(collection_hierarchy.keys())
        for collection in collections_to_remove:
            bpy.data.collections.remove(collection)
        self.report({'INFO'}, f"已完成集合转空对象操作")
        return {"FINISHED"}


# 清除为空集合
class BetterExperie_OT_ClearEmptyCollections(bpy.types.Operator):
    bl_idname = 'better_experie.clear_empty_collections'
    bl_label = "清除为空集合"
    bl_description = "遍历场景，当集合为空时，将其移除"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        count = 0
        collections_to_remove = []
        for collection in bpy.data.collections:
            if not collection.objects and not collection.children:
                collections_to_remove.append(collection)
                count += 1
        for collection in collections_to_remove:
            bpy.data.collections.remove(collection)
        self.report({'INFO'}, f"清理完成,清理了{count}个集合")
        return {"FINISHED"}


# 清除无用空物体
class BetterExperie_OT_ClearUselessEmpties(bpy.types.Operator):
    bl_idname = 'better_experie.clear_useless_empties'
    bl_label = "清除无用空物体"
    bl_description = "遍历场景，当空物体不包含子集且未被其他对象的修改器引用时，将其移除"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        count = 0
        objects_to_remove = []
        for obj in bpy.data.objects:
            if (
                obj.type == 'EMPTY'
                and obj.empty_display_type != 'IMAGE'
                and not getChildren(obj)
                and not is_referenced_by_modifier(obj)
                and obj.instance_type == 'NONE'
            ):
                objects_to_remove.append(obj)
                count += 1
        for obj in objects_to_remove:
            bpy.data.objects.remove(obj)
        self.report({'INFO'}, f"清理完成，清理了{count}个空物体")
        return {"FINISHED"}


classes = (
    BetterExperie_OT_EmptiesToCollections,
    BetterExperie_OT_CollectionsToEmpties,
    BetterExperie_OT_ClearEmptyCollections,
    BetterExperie_OT_ClearUselessEmpties,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

