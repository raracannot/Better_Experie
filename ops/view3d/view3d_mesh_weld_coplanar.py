# 焊接共面：借助原生布尔并集（intersect_boolean）把选中且可见的共面/重叠面焊接为一个面
# 用临时面域属性层标记隐藏面，布尔后读取属性层恢复可见性

import bpy


_LAYER_NAME = "temp_weld_coplanar"


class BetterExperie_OT_WeldCoplanar(bpy.types.Operator):
    bl_idname = "better_experie.weld_coplanar"
    bl_label = "焊接共面"
    bl_description = "借助布尔并集将选中的共面/重叠面焊接为一个面。自动隐藏未选中面来限定范围，完成后恢复可见性"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return (
            context.active_object is not None
            and context.active_object.type == 'MESH'
            and context.mode == 'EDIT_MESH'
            and context.tool_settings.mesh_select_mode[2]
        )

    def execute(self, context):
        obj = context.edit_object
        if not obj or obj.type != 'MESH':
            self.report({'WARNING'}, "请选择网格对象")
            return {'CANCELLED'}

        import bmesh
        bm = bmesh.from_edit_mesh(obj.data)
        bm.faces.ensure_lookup_table()

        selected_faces = [f for f in bm.faces if f.select]
        if not selected_faces:
            self.report({'WARNING'}, "请先选中要焊接的面")
            return {'CANCELLED'}

        # 清理可能残留的临时层
        old = bm.faces.layers.int.get(_LAYER_NAME)
        if old is not None:
            bm.faces.layers.int.remove(old)

        # 创建临时面域属性层：记录当前可见性（1=原本隐藏，0=原本可见），与选择状态无关
        layer = bm.faces.layers.int.new(_LAYER_NAME)
        for f in bm.faces:
            f[layer] = 1 if f.hide else 0

        # 隐藏所有未选中的面，仅保留选中面可见 → 布尔只处理可见网格
        for f in bm.faces:
            if not f.select:
                f.hide = True

        bmesh.update_edit_mesh(obj.data, loop_triangles=True)

        saved_mode = context.tool_settings.mesh_select_mode[:]
        context.tool_settings.mesh_select_mode = (False, False, True)
        try:
            bpy.ops.mesh.intersect_boolean(
                operation='UNION',
                solver='EXACT',
                use_self=True,
            )
        except RuntimeError as e:
            self.report({'ERROR'}, f"布尔运算失败: {e}")
            bm = bmesh.from_edit_mesh(obj.data)
            for f in bm.faces:
                f.hide = False
            bmesh.update_edit_mesh(obj.data, loop_triangles=True)
            context.tool_settings.mesh_select_mode = saved_mode
            return {'CANCELLED'}

        context.tool_settings.mesh_select_mode = saved_mode

        # 布尔后读取临时层恢复可见性
        bm = bmesh.from_edit_mesh(obj.data)
        bm.faces.ensure_lookup_table()

        layer = bm.faces.layers.int.get(_LAYER_NAME)
        if layer is None:
            # 属性层在布尔后丢失（求解器重建 customdata），降级为全部可见
            for f in bm.faces:
                f.hide = False
            bmesh.update_edit_mesh(obj.data, loop_triangles=True)
            self.report({'INFO'}, "焊接共面完成（属性层丢失，已恢复全部可见）")
            return {'FINISHED'}

        # 布尔后按属性层精确还原可见性（1=原本隐藏，0=原本可见）
        restored = 0
        for f in bm.faces:
            f.hide = (f[layer] == 1)
            if f[layer] == 1:
                restored += 1

        # 清理临时属性层
        try:
            bm.faces.layers.int.remove(layer)
        except Exception:
            pass

        bmesh.update_edit_mesh(obj.data, loop_triangles=True)
        self.report({'INFO'}, f"焊接共面完成，已按可见性还原 {restored} 个隐藏面")
        return {'FINISHED'}


classes = (
    BetterExperie_OT_WeldCoplanar,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
