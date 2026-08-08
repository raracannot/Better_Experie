# 无损复制/粘贴选中元素（极速选中 + 精准垃圾回收）

import json
import bpy

SUPPORTED_TYPES = {'MESH', 'CURVE', 'SURFACE', 'ARMATURE', 'GPENCIL'}


def _has_selection(obj):
    if obj.type == 'MESH':
        import bmesh
        bm = bmesh.from_edit_mesh(obj.data)
        return any(v.select for v in bm.verts)
    elif obj.type in {'CURVE', 'SURFACE'}:
        for spl in obj.data.splines:
            if spl.type == 'BEZIER':
                if any(p.select_control_point for p in spl.bezier_points):
                    return True
            else:
                if any(p.select for p in spl.points):
                    return True
        return False
    elif obj.type == 'ARMATURE':
        return len(bpy.context.selected_bones) > 0
    elif obj.type == 'GPENCIL':
        for layer in obj.data.layers:
            if not layer.hide and not layer.lock:
                for frame in layer.frames:
                    for stroke in frame.strokes:
                        if any(pt.select for pt in stroke.points):
                            return True
        return False
    return False


def _cleanup_specific_data(data_blocks):
    for data in data_blocks:
        if data and getattr(data, "users", 1) == 0:
            try:
                if isinstance(data, bpy.types.Mesh):
                    bpy.data.meshes.remove(data)
                elif isinstance(data, bpy.types.Curve):
                    bpy.data.curves.remove(data)
                elif isinstance(data, bpy.types.Armature):
                    bpy.data.armatures.remove(data)
                elif isinstance(data, bpy.types.GreasePencil):
                    bpy.data.grease_pencils.remove(data)
            except Exception as e:
                print(f"清理临时数据失败: {e}")


class BetterExperie_OT_CopyElements(bpy.types.Operator):
    bl_idname = "better_experie.copy_elements"
    bl_label = "复制选中元素"
    bl_description = "复制编辑状态下，选中的【网格/骨骼/曲线】元素到剪贴板"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj and obj.type in SUPPORTED_TYPES and obj.mode in {'EDIT', 'EDIT_GPENCIL'}

    def execute(self, context):
        original_obj = context.active_object
        obj_type = original_obj.type

        if not _has_selection(original_obj):
            self.report({'WARNING'}, "请先选中要复制的元素")
            return {'CANCELLED'}

        bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.object.select_all(action='DESELECT')
        original_obj.select_set(True)
        context.view_layer.objects.active = original_obj

        bpy.ops.object.duplicate()
        dup_obj = context.active_object

        if obj_type == 'GPENCIL':
            bpy.ops.object.mode_set(mode='EDIT_GPENCIL')
        else:
            bpy.ops.object.mode_set(mode='EDIT')

        separated = False
        try:
            if obj_type == 'MESH':
                bpy.ops.mesh.separate(type='SELECTED')
            elif obj_type in {'CURVE', 'SURFACE'}:
                bpy.ops.curve.separate()
            elif obj_type == 'ARMATURE':
                bpy.ops.armature.separate()
            elif obj_type == 'GPENCIL':
                bpy.ops.gpencil.stroke_separate(mode='SELECTED')
            separated = True
        except RuntimeError:
            pass

        bpy.ops.object.mode_set(mode='OBJECT')

        if separated:
            new_objs = [obj for obj in context.selected_objects if obj != dup_obj]
            if new_objs:
                copy_target = new_objs[0]
                objs_to_delete = [dup_obj, copy_target]
            else:
                copy_target = dup_obj
                objs_to_delete = [dup_obj]
        else:
            copy_target = dup_obj
            objs_to_delete = [dup_obj]

        plugin_generated_data = [obj.data for obj in objs_to_delete if obj.data]

        bpy.ops.object.select_all(action='DESELECT')
        copy_target.select_set(True)
        context.view_layer.objects.active = copy_target

        mw = copy_target.matrix_world.copy()
        copy_target.parent = None
        copy_target.matrix_world = mw

        bpy.ops.view3d.copybuffer()

        bpy.ops.object.select_all(action='DESELECT')
        for obj in objs_to_delete:
            obj.select_set(True)
        bpy.ops.object.delete()

        _cleanup_specific_data(plugin_generated_data)

        original_obj.select_set(True)
        context.view_layer.objects.active = original_obj
        if obj_type == 'GPENCIL':
            bpy.ops.object.mode_set(mode='EDIT_GPENCIL')
        else:
            bpy.ops.object.mode_set(mode='EDIT')

        self.report({'INFO'}, f"成功将 {obj_type} 元素复制到剪贴板")
        return {'FINISHED'}


class BetterExperie_OT_PasteElements(bpy.types.Operator):
    bl_idname = "better_experie.paste_elements"
    bl_label = "粘贴元素并选中"
    bl_description = "编辑模式下，将剪贴板的【网格/骨骼/曲线】元素粘贴入内"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj and obj.type in SUPPORTED_TYPES and obj.mode in {'EDIT', 'EDIT_GPENCIL'}

    def execute(self, context):
        target_obj = context.active_object
        target_type = target_obj.type

        bpy.ops.object.mode_set(mode='OBJECT')

        old_counts = {}
        if target_type == 'MESH':
            old_counts['verts'] = len(target_obj.data.vertices)
            old_counts['edges'] = len(target_obj.data.edges)
            old_counts['faces'] = len(target_obj.data.polygons)
        elif target_type in {'CURVE', 'SURFACE'}:
            old_counts['splines'] = len(target_obj.data.splines)
        elif target_type == 'ARMATURE':
            old_counts['bones'] = set(b.name for b in target_obj.data.bones)

        bpy.ops.object.select_all(action='DESELECT')
        try:
            bpy.ops.view3d.pastebuffer()
        except RuntimeError:
            self.report({'WARNING'}, "剪贴板中没有有效的数据")
            context.view_layer.objects.active = target_obj
            target_obj.select_set(True)
            self._restore_edit_mode(target_type)
            return {'CANCELLED'}

        pasted_objs = context.selected_objects
        if not pasted_objs:
            self.report({'WARNING'}, "未粘贴任何物体")
            context.view_layer.objects.active = target_obj
            target_obj.select_set(True)
            self._restore_edit_mode(target_type)
            return {'CANCELLED'}

        plugin_generated_data = []

        for obj in pasted_objs:
            if obj.type != target_type:
                self.report({'WARNING'}, "类型不匹配！无法合并")
                bpy.ops.object.delete()
                context.view_layer.objects.active = target_obj
                target_obj.select_set(True)
                self._restore_edit_mode(target_type)
                return {'CANCELLED'}
            obj.select_set(True)
            if obj.data:
                plugin_generated_data.append(obj.data)

        target_obj.select_set(True)
        context.view_layer.objects.active = target_obj

        # 验证目标对象可见且可选，避免 object.join poll 失败（RuntimeError）
        if not target_obj.visible_get() or target_obj.hide_select:
            self.report({'WARNING'}, f"目标对象 '{target_obj.name}' 不可见或不可选，无法合并粘贴")
            try:
                bpy.ops.object.delete()
            except Exception:
                pass
            context.view_layer.objects.active = target_obj
            target_obj.select_set(True)
            self._restore_edit_mode(target_type)
            return {'CANCELLED'}

        bpy.ops.object.join()

        _cleanup_specific_data(plugin_generated_data)

        if target_type == 'MESH':
            mesh = target_obj.data
            v_sel = [False] * old_counts['verts'] + [True] * (len(mesh.vertices) - old_counts['verts'])
            e_sel = [False] * old_counts['edges'] + [True] * (len(mesh.edges) - old_counts['edges'])
            p_sel = [False] * old_counts['faces'] + [True] * (len(mesh.polygons) - old_counts['faces'])

            mesh.vertices.foreach_set('select', v_sel)
            mesh.edges.foreach_set('select', e_sel)
            mesh.polygons.foreach_set('select', p_sel)
            bpy.ops.object.mode_set(mode='EDIT')

        elif target_type in {'CURVE', 'SURFACE'}:
            curve = target_obj.data
            for i, spline in enumerate(curve.splines):
                is_new = (i >= old_counts['splines'])
                if spline.type == 'BEZIER':
                    pts_count = len(spline.bezier_points)
                    sel_arr = [is_new] * pts_count
                    spline.bezier_points.foreach_set('select_control_point', sel_arr)
                    spline.bezier_points.foreach_set('select_left_handle', sel_arr)
                    spline.bezier_points.foreach_set('select_right_handle', sel_arr)
                else:
                    pts_count = len(spline.points)
                    sel_arr = [is_new] * pts_count
                    spline.points.foreach_set('select', sel_arr)
            bpy.ops.object.mode_set(mode='EDIT')

        elif target_type == 'ARMATURE':
            bpy.ops.object.mode_set(mode='EDIT')
            bpy.ops.armature.select_all(action='DESELECT')
            for bone in target_obj.data.edit_bones:
                if bone.name not in old_counts['bones']:
                    bone.select = True
                    bone.select_head = True
                    bone.select_tail = True

        elif target_type == 'GPENCIL':
            bpy.ops.object.mode_set(mode='EDIT_GPENCIL')

        self.report({'INFO'}, "成功极速粘贴并选中新元素")
        return {'FINISHED'}

    def _restore_edit_mode(self, obj_type):
        if obj_type == 'GPENCIL':
            bpy.ops.object.mode_set(mode='EDIT_GPENCIL')
        else:
            bpy.ops.object.mode_set(mode='EDIT')



classes = (
    BetterExperie_OT_CopyElements,
    BetterExperie_OT_PasteElements,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
