# 创建空物体组

import bpy


class BetterExperie_OT_CreateEmptyGroup(bpy.types.Operator):
    bl_idname = "better_experie.create_empty_group"
    bl_label = "创建空物体组"
    bl_description = "在活动物体的层级处新建一个空物体，并把所选对象设为其子集"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return len(context.selected_objects) > 0

    def execute(self, context):
        selected_objs = context.selected_objects
        active_obj = context.active_object

        target_collection = None

        if active_obj and active_obj.users_collection:
            target_collection = active_obj.users_collection[0]
        else:
            collection_counts = {}
            for obj in selected_objs:
                for coll in obj.users_collection:
                    collection_counts[coll] = collection_counts.get(coll, 0) + 1
            if collection_counts:
                target_collection = max(collection_counts, key=collection_counts.get)

        if not target_collection:
            target_collection = context.collection

        empty = bpy.data.objects.new("Empty_Group", None)
        empty.empty_display_size = 0.001
        context.collection.objects.link(empty)

        if active_obj:
            empty.parent = active_obj.parent
            empty.matrix_world = active_obj.matrix_world.copy()

        for obj in selected_objs:
            world_mat = obj.matrix_world.copy()
            obj.parent = empty
            obj.matrix_world = world_mat

        bpy.ops.object.select_all(action='DESELECT')
        empty.select_set(True)
        context.view_layer.objects.active = empty

        return {'FINISHED'}


class BetterExperie_OT_DissolveEmptyGroup(bpy.types.Operator):
    bl_idname = "better_experie.dissolve_empty_group"
    bl_label = "解散空物体组"
    bl_description = "将所选空物体的子集移出并保持世界变换，然后删除空物体"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        if not obj or obj.type != 'EMPTY':
            return False
        for child in bpy.data.objects:
            if child.parent == obj:
                return True
        return False

    def execute(self, context):
        empty = context.active_object
        new_parent = empty.parent

        children = [c for c in bpy.data.objects if c.parent == empty]
        for child in children:
            world_mat = child.matrix_world.copy()
            child.parent = new_parent
            child.matrix_world = world_mat

        bpy.data.objects.remove(empty)
        self.report({'INFO'}, f"已解散空物体组，释放了 {len(children)} 个子对象")
        return {'FINISHED'}


classes = (
    BetterExperie_OT_CreateEmptyGroup,
    BetterExperie_OT_DissolveEmptyGroup,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
