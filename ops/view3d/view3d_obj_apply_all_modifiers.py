# 应用所有修改器

import bpy

class BetterExperie_OT_ApplyAllModifiers(bpy.types.Operator):
    #遍历所有选中的物体，尝试应用每个修改器
    bl_idname = "better_experie.apply_all_modifiers"
    bl_label = "应用所有修改器"
    bl_options = {'REGISTER', 'UNDO'}
    bl_description = "遍历所有选中的物体，尝试应用每个修改器"
    
    @classmethod
    def poll(cls, context):
        return any(obj.type == 'MESH' for obj in context.selected_objects)
        #如果所选项目没有mesh也跳过

    def execute(self, context):
        applied_count = 0
        skipped_objects = []
        failed_modifiers = []
        
        if context.mode != 'OBJECT':
            self.report({'INFO'}, "请在物体模式下执行")
            return {'CANCELLED'}
        
        # 遍历所有选中的物体（复制列表以避免迭代中修改）
        for obj in context.selected_objects[:]:
            if obj.type != 'MESH':
                continue  # 只处理网格物体

            if not obj.modifiers:
                continue  # 无修改器，直接跳过
            
            # 确保物体是当前激活的，以便操作符工作
            context.view_layer.objects.active = obj

            # 复制修改器列表，因为应用后会改变原列表
            modifiers = obj.modifiers[:]

            for mod in modifiers:
                try:
                    # 应用修改器（需要确保在对象模式下）
                    bpy.ops.object.modifier_apply(modifier=mod.name)
                    applied_count += 1
                except Exception as e:
                    # 记录失败的修改器，但继续处理其他修改器
                    failed_modifiers.append((obj.name, mod.name, str(e)))
                    continue

            # 如果物体仍有修改器但未能全部应用（理论上循环已处理完），记录
            if obj.modifiers:
                skipped_objects.append(obj.name)

        # 报告结果
        msg = f"已应用 {applied_count} 个修改器"
        if failed_modifiers:
            msg += f"\n失败 {len(failed_modifiers)} 个："
            for obj_name, mod_name, err in failed_modifiers[:5]:  # 最多显示5个
                msg += f"\n  {obj_name}.{mod_name} ({err})"
            if len(failed_modifiers) > 5:
                msg += f"\n  以及 {len(failed_modifiers)-5} 个更多"
        if skipped_objects:
            msg += f"\n以下物体仍有修改器（可能因顺序问题未完全应用）: {', '.join(skipped_objects[:5])}"
        self.report({'INFO'}, msg)
        return {'FINISHED'}



def register():
    bpy.utils.register_class(BetterExperie_OT_ApplyAllModifiers)


def unregister():
    bpy.utils.unregister_class(BetterExperie_OT_ApplyAllModifiers)


if __name__ == "__main__":
    register()