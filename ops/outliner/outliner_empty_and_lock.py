# 创建空物体（支持修饰键选择层级）与变换锁定

import bpy


class BetterExperie_OT_ToggleTransformLocks(bpy.types.Operator):
    bl_idname = "better_experie.toggle_transform_locks"
    bl_label = "添加保护 (Alt解锁)"
    bl_description = "默认: 锁定所选对象的位移、旋转、缩放 | Alt: 解锁"
    bl_options = {'REGISTER', 'UNDO'}

    alt: bpy.props.BoolProperty(default=False)

    @classmethod
    def poll(cls, context):
        return len(context.selected_objects) > 0

    def invoke(self, context, event):
        self.alt = event.alt
        return self.execute(context)

    def execute(self, context):
        selected_objs = context.selected_objects
        lock_state = not self.alt

        for obj in selected_objs:
            for i in range(3):
                obj.lock_location[i] = lock_state
                obj.lock_rotation[i] = lock_state
                obj.lock_scale[i] = lock_state

        action_str = "解锁" if self.alt else "锁定"
        self.report({'INFO'}, f"已{action_str} {len(selected_objs)} 个对象的变换")
        return {'FINISHED'}


class BetterExperie_OT_AddEmptySibling(bpy.types.Operator):
    bl_idname = "better_experie.add_empty_sibling"
    bl_label = "创建空物体 (支持修饰键)"
    bl_description = "默认/Ctrl: 同级 | Shift: 作为子集 | Alt: 作为父集"
    bl_options = {'REGISTER', 'UNDO'}

    shift: bpy.props.BoolProperty(default=False)
    ctrl: bpy.props.BoolProperty(default=False)
    alt: bpy.props.BoolProperty(default=False)

    @classmethod
    def poll(cls, context):
        return True

    def invoke(self, context, event):
        self.shift = event.shift
        self.ctrl = event.ctrl
        self.alt = event.alt
        return self.execute(context)

    def _create_empty(self, obj, collection):
        empty = bpy.data.objects.new(name=f"{obj.name}_Empty", object_data=None)
        empty.empty_display_type = 'PLAIN_AXES'
        if collection:
            collection.objects.link(empty)
        else:
            bpy.context.scene.collection.objects.link(empty)
        return empty

    def execute(self, context):
        active_obj = context.active_object
        selected_objs = context.selected_objects

        new_empties = []
        objects_to_activate = []

        if self.shift and selected_objs:
            for obj in selected_objs:
                col = context.collection
                empty = self._create_empty(obj, col)

                empty.parent = obj
                empty.matrix_world = obj.matrix_world.copy()

                new_empties.append(empty)
                objects_to_activate.append(empty)
            msg = f"已为 {len(selected_objs)} 个物体创建子集空物体"

        elif self.alt and selected_objs:
            for obj in selected_objs:
                col = context.collection
                empty = self._create_empty(obj, col)

                empty.parent = obj.parent
                empty.matrix_world = obj.matrix_world.copy()

                old_matrix = obj.matrix_world.copy()
                obj.parent = empty
                obj.matrix_parent_inverse = empty.matrix_world.inverted()
                obj.matrix_world = old_matrix

                new_empties.append(empty)
                objects_to_activate.append(obj)
            msg = f"已为 {len(selected_objs)} 个物体创建父集空物体"

        else:
            if active_obj:
                col = context.collection
                empty = self._create_empty(active_obj, col)

                empty.parent = active_obj.parent
                empty.matrix_world = active_obj.matrix_world.copy()
                msg = f"已在 {active_obj.name} 同层级创建空物体"
            else:
                col = context.collection if context.collection else context.scene.collection
                empty = bpy.data.objects.new(name="Empty", object_data=None)
                empty.empty_display_type = 'PLAIN_AXES'
                col.objects.link(empty)
                msg = "已在当前集合创建空物体"

            new_empties.append(empty)

        bpy.ops.object.select_all(action='DESELECT')
        for empty in new_empties:
            empty.select_set(True)

        if new_empties:
            context.view_layer.objects.active = new_empties[-1]

        self.report({'INFO'}, msg)
        return {'FINISHED'}

def draw_outliner_header_button(self, context):
    if getattr(context.space_data, "display_mode", "") == 'VIEW_LAYER':
        row = self.layout.row(align=True)
        row.operator("better_experie.toggle_transform_locks", text="", icon='LOCKED')
        row.operator("better_experie.add_empty_sibling", text="", icon='EMPTY_AXIS')


classes = (
    BetterExperie_OT_ToggleTransformLocks,
    BetterExperie_OT_AddEmptySibling,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.OUTLINER_HT_header.prepend(draw_outliner_header_button)


def unregister():
    bpy.types.OUTLINER_HT_header.remove(draw_outliner_header_button)
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
