# 对调隐藏

import bpy
import bmesh
    
class BetterExperie_OT_ToggleHidden(bpy.types.Operator):
    bl_idname = "better_experie.toggle_hidden"
    bl_label = "对调隐藏"
    bl_description = "对调隐藏和未隐藏的元素\n将隐藏项可见、将可见项隐藏"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        mode = context.mode
        if mode == 'EDIT_MESH':
            obj = context.active_object
            bm = bmesh.from_edit_mesh(obj.data)
            for v in bm.verts:
                v.hide = not v.hide
            for e in bm.edges:
                e.hide = not e.hide
            for f in bm.faces:
                f.hide = not f.hide
            bmesh.update_edit_mesh(obj.data)
        elif mode in ['EDIT_CURVE', 'EDIT_SURFACE']:
            obj = context.active_object
            curve = obj.data
            visible_points = set()
            for s in curve.splines:
                for i, p in enumerate(s.bezier_points):
                    if not p.hide:
                        visible_points.add((s, i))
            bpy.ops.curve.reveal(select=False)
            for s in curve.splines:
                for i, p in enumerate(s.bezier_points):
                    if (s, i) in visible_points:
                        p.hide = True
        elif mode == 'EDIT_METABALL':
            obj = context.active_object
            metaball = obj.data
            visible_elements = set()
            for i, element in enumerate(metaball.elements):
                if not element.hide:
                    visible_elements.add(i)
            bpy.ops.mball.reveal_metaelems(select=False)
            for i, element in enumerate(metaball.elements):
                if i in visible_elements:
                    element.hide = True
        else:
            # 仅遍历当前视图层对象，避免对非当前视图层对象调用 hide_set 报错
            for obj in context.view_layer.objects:
                obj.hide_set(not obj.hide_get())
        return {'FINISHED'}
        
classes = (
    BetterExperie_OT_ToggleHidden,
)

    
def register():
    for cls in classes:
        bpy.utils.register_class(cls)
        
def unregister():
    
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
