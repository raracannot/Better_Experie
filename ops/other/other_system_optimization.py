# 系统缓存清理
import bpy
import time
import gc

def count_orphan_data_blocks():
    #统计未使用的数据块数量（没有用户且未标记假用户）
    count = 0
    for attr in dir(bpy.data):
        if attr.startswith('_'):
            continue
        collection = getattr(bpy.data, attr)
        if not hasattr(collection, '__iter__') or isinstance(collection, str):
            continue
        try:
            for item in collection:
                if hasattr(item, 'users') and hasattr(item, 'use_fake_user'):
                    if item.users == 0 and not item.use_fake_user:
                        count += 1
        except Exception:
            continue
    return count

def execute_in_area(area_type, operator, *args, **kwargs):
    #在指定类型的区域内执行操作符，自动处理上下文（只执行第一个匹配区域）
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == area_type:
                override = bpy.context.copy()
                override['window'] = window
                override['screen'] = window.screen
                override['area'] = area
                for region in area.regions:
                    if region.type == 'WINDOW':
                        override['region'] = region
                        break
                return operator(override, *args, **kwargs)
    return None

class BetterExperie_OT_SystemOptimization(bpy.types.Operator):
    """释放物理缓存、清理未使用数据并优化撤销内存"""
    bl_idname = "better_experie.system_optimization"
    bl_label = "优化加速"
    bl_description = "释放物理缓存、清理未使用数据，清理撤销堆栈，优化内存"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        start_time = time.perf_counter()
        orphan_before = count_orphan_data_blocks()

        # 记录原撤销步数和全局撤销设置
        prefs_edit = bpy.context.preferences.edit
        self.orig_undo_steps = prefs_edit.undo_steps
        self.orig_undo_memory_limit = prefs_edit.undo_memory_limit
        self.orig_use_global_undo = prefs_edit.use_global_undo

        prefs_system = bpy.context.preferences.system
        self.orig_scrollback = prefs_system.scrollback
        self.orig_texture_time_out = prefs_system.texture_time_out
        self.orig_texture_collection_rate = prefs_system.texture_collection_rate
        self.orig_vbo_time_out = prefs_system.vbo_time_out
        self.orig_vbo_collection_rate = prefs_system.vbo_collection_rate

        # 临时设置
        prefs_edit.undo_steps = 2
        prefs_edit.undo_memory_limit = 1
        prefs_edit.use_global_undo = False

        prefs_system.scrollback = 32
        prefs_system.texture_time_out = 1
        prefs_system.texture_collection_rate = 1
        prefs_system.vbo_time_out = 1
        prefs_system.vbo_collection_rate = 1

        bpy.ops.ed.undo_push()  # 推送一次撤销操作，确保堆栈被刷新

        # 恢复原始设置
        prefs_edit.undo_steps = self.orig_undo_steps
        prefs_edit.undo_memory_limit = self.orig_undo_memory_limit
        prefs_edit.use_global_undo = self.orig_use_global_undo

        prefs_system.scrollback = self.orig_scrollback
        prefs_system.texture_time_out = self.orig_texture_time_out
        prefs_system.texture_collection_rate = self.orig_texture_collection_rate
        prefs_system.vbo_time_out = self.orig_vbo_time_out
        prefs_system.vbo_collection_rate = self.orig_vbo_collection_rate

        # 释放物理缓存
        bpy.ops.ptcache.free_bake_all()

        # 清理未使用的材质槽
        for obj in bpy.data.objects:
            if obj.type == 'MESH' and obj.material_slots:
                for i in range(len(obj.material_slots) - 1, -1, -1):
                    if obj.material_slots[i].material is None:
                        obj.material_slots.remove(obj.material_slots[i])

        # 清理未使用数据（多次调用以确保彻底清理）
        for i in range(5):
            bpy.ops.outliner.orphans_purge(
                do_local_ids=True,
                do_linked_ids=True,
                do_recursive=True
            )

        # 遍历所有三维窗口，切换为实体显示模式
        for window in bpy.context.window_manager.windows:
            for area in window.screen.areas:
                if area.type == 'VIEW_3D':
                    for space in area.spaces:
                        if space.type == 'VIEW_3D':
                            space.shading.type = 'SOLID'

        # 清理动画预览缓存
        execute_in_area('TIMELINE', bpy.ops.anim.previewrange_clear)
        # 清理视频剪辑代理缓存
        execute_in_area('CLIP_EDITOR', bpy.ops.clip.clear_proxy)
        # 重新加载所有图片（刷新图像缓存）
        bpy.ops.image.reload()
        # Python垃圾回收
        gc.collect()

        # 清理后未使用数据块数量
        orphan_after = count_orphan_data_blocks()
        orphan_cleaned = orphan_before - orphan_after

        end_time = time.perf_counter()
        elapsed_time = end_time - start_time

        self.report({'INFO'}, f"清理完成，清理未使用数据块{orphan_cleaned}个，耗时{elapsed_time:.2f}S")

        return {'FINISHED'}


    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=400)

    def draw(self, context):
        layout = self.layout
        layout.label(text="优化加速会尽可能的帮助您清理本文件的可清理缓存，包括：",icon="GHOST_ENABLED")
        # layout.separator(type="LINE")
        box = layout.box()
        box.label(text="撤销记录、物理缓存、未使用材质槽、未使用数据")
        box.label(text="动画预览缓存、剪辑代理缓存、图像缓存、Python垃圾回收")
        # layout.separator(type="LINE")
        layout.label(text="请知悉并确认是否继续？")
        

def register():
    bpy.utils.register_class(BetterExperie_OT_SystemOptimization)

def unregister():
    bpy.utils.unregister_class(BetterExperie_OT_SystemOptimization)

if __name__ == "__main__":
    register()