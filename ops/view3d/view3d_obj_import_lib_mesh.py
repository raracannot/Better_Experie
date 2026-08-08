# 从预设库导入网格，对齐游标并复用已有数据

import bpy
import os


class BetterExperie_OT_ImportLibMesh(bpy.types.Operator):
    bl_idname = "better_experie.import_lib_mesh"
    bl_label = "导入网格"
    bl_description = "默认点击导入并复用数据；按住Shift点击则强制作为独立副本导入"
    bl_options = {'REGISTER', 'UNDO'}

    object_name: bpy.props.StringProperty(
        name="Object Name",
        description="Name of the object to import from lib.blend"
    )

    reuse_data: bpy.props.BoolProperty(
        name="复用材质和节点",
        description="自动复用场景中已存在的同名材质和节点树",
        default=True
    )

    def invoke(self, context, event):
        self.reuse_data = not event.shift
        return self.execute(context)

    def execute(self, context):
        addon_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        lib_path = os.path.join(addon_dir, "data", "obj_lib.blend")

        if not os.path.exists(lib_path):
            self.report({'ERROR'}, f"找不到模型库文件: {lib_path}")
            return {'CANCELLED'}

        directory = os.path.join(lib_path, "Object")

        def deduplicate_datablock(data_collection, datablock):
            if datablock and "." in datablock.name:
                base_name, ext = datablock.name.rsplit(".", 1)
                if ext.isdigit() and base_name in data_collection:
                    return data_collection[base_name]
            return datablock

        try:
            selected_before = set(context.selected_objects)

            bpy.ops.wm.append(
                filepath=os.path.join(lib_path, "Object", self.object_name),
                filename=self.object_name,
                directory=directory,
                active_collection=True
            )

            selected_after = set(context.selected_objects)
            new_objects = selected_after - selected_before

            for obj in new_objects:
                obj.matrix_world = context.scene.cursor.matrix.copy()

                if obj.asset_data:
                    obj.asset_clear()

                if self.reuse_data:
                    for slot in obj.material_slots:
                        if slot.material:
                            orig_mat = slot.material
                            reused_mat = deduplicate_datablock(bpy.data.materials, orig_mat)
                            if reused_mat != orig_mat:
                                slot.material = reused_mat
                                if orig_mat.users == 0:
                                    bpy.data.materials.remove(orig_mat)

                    for mod in obj.modifiers:
                        if mod.type == 'NODES' and mod.node_group:
                            orig_ng = mod.node_group
                            reused_ng = deduplicate_datablock(bpy.data.node_groups, orig_ng)
                            if reused_ng != orig_ng:
                                mod.node_group = reused_ng
                                if orig_ng.users == 0:
                                    bpy.data.node_groups.remove(orig_ng)

                obj.select_set(True)
                context.view_layer.objects.active = obj

            if self.reuse_data:
                self.report({'INFO'}, f"成功导入: {self.object_name}")
            else:
                self.report({'INFO'}, f"成功导入: {self.object_name}(独立副本)")

        except Exception as e:
            self.report({'ERROR'}, f"导入失败: {str(e)}")
            return {'CANCELLED'}

        return {'FINISHED'}


class VIEW3D_MT_better_experie_more_meshes(bpy.types.Menu):
    bl_idname = "VIEW3D_MT_better_experie_more_meshes"
    bl_label = "更多网格"
    bl_description = "从预设库导入常用网格体"

    def draw(self, context):
        layout = self.layout

        mesh_items = [
            ("立方体", 'MESH_CUBE'),
            ("圆柱", 'MESH_CYLINDER'),
            ("平面", 'MESH_PLANE'),
            ("圆盘", 'MESH_CIRCLE'),
            ("球体", 'MESH_UVSPHERE'),
            ("胶囊", 'MESH_CAPSULE'),
            ("圆管", 'MESH_CYLINDER'),
            ("圆环", 'MESH_TORUS'),
            ("背景", 'OUTLINER_OB_MESH')
        ]

        for name, icon in mesh_items:
            op = layout.operator(BetterExperie_OT_ImportLibMesh.bl_idname, text=name, icon=icon)
            op.object_name = name



classes = (
    BetterExperie_OT_ImportLibMesh,
    VIEW3D_MT_better_experie_more_meshes,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
