# GPU 缓存清理
# 入口：文件 > 清理 > 清理GPU缓存（TOPBAR_MT_file_cleanup）
# 交互：弹出对话框，列出检测到的着色器缓存目录（含大小/文件数），可逐项勾选后清理
# 说明：清理的是显卡驱动「重新编译即恢复」的着色器缓存，不涉及用户数据

import bpy
import os
import platform


# ── 缓存目录定义 ────────────────────────────────────────────────
def get_cache_dirs():
    """返回本机存在的缓存目录 [(显示名, 路径), ...]"""
    system = platform.system()
    candidates = []

    if system == "Windows":
        local = os.environ.get("LOCALAPPDATA", "")
        nvidia = os.path.join(local, "NVIDIA")
        candidates += [
            ("NVIDIA OptiX 缓存", os.path.join(nvidia, "OptixCache")),
            ("NVIDIA CUDA 缓存", os.path.join(nvidia, "ComputeCache")),
            ("NVIDIA DX 缓存", os.path.join(nvidia, "DXCache")),
            ("NVIDIA GL 缓存", os.path.join(nvidia, "GLCache")),
            ("NVIDIA 着色器缓存 NV_Cache", os.path.join(local, "NVIDIA Corporation", "NV_Cache")),
            ("DirectX 着色器缓存", os.path.join(local, "D3DSCache")),
            ("AMD DX 缓存", os.path.join(local, "AMD", "DxCache")),
            ("AMD DX9 缓存", os.path.join(local, "AMD", "Dx9Cache")),
            ("AMD DXC 缓存", os.path.join(local, "AMD", "DxcCache")),
            ("AMD GL 缓存", os.path.join(local, "AMD", "GLCache")),
            ("AMD Vulkan 缓存", os.path.join(local, "AMD", "VkCache")),
            ("AMD PIX 缓存", os.path.join(local, "AMD", "PIXCache")),
            ("Intel 着色器缓存", os.path.join(local, "Intel", "ShaderCache")),
        ]

    elif system == "Linux":
        home = os.path.expanduser("~")
        dot_nv = os.path.join(home, ".nv")
        xdg_cache = os.environ.get("XDG_CACHE_HOME", os.path.join(home, ".cache"))
        candidates += [
            ("NVIDIA OptiX 缓存", os.path.join(dot_nv, "OptiXCache")),
            ("NVIDIA Optix 缓存", os.path.join(dot_nv, "OptixCache")),
            ("NVIDIA CUDA 缓存", os.path.join(dot_nv, "ComputeCache")),
            ("NVIDIA GL 缓存", os.path.join(xdg_cache, "nvidia", "GLCache")),
            ("NVIDIA DX 缓存", os.path.join(xdg_cache, "nvidia", "DXCache")),
            ("Mesa 着色器缓存", os.path.join(xdg_cache, "mesa_shader_cache")),
            ("Mesa 着色器缓存 DB", os.path.join(xdg_cache, "mesa_shader_cache_db")),
            ("AMD Vulkan 缓存", os.path.join(xdg_cache, "mesa_vulkan_cache")),
        ]

    else:  # macOS
        home = os.path.expanduser("~")
        caches = os.path.join(home, "Library", "Caches")
        candidates += [
            ("NVIDIA 缓存", os.path.join(caches, "NVIDIA")),
            ("Metal 着色器缓存", os.path.join(caches, "com.apple.metal")),
        ]

    return [(label, path) for label, path in candidates if os.path.isdir(path)]


# ── 统计与清理 ──────────────────────────────────────────────────
def scan_dir(path):
    """统计目录内 (文件数, 总字节数)，不可读的项跳过"""
    file_count = 0
    total_size = 0
    for root, _dirs, files in os.walk(path, followlinks=False):
        for name in files:
            full = os.path.join(root, name)
            try:
                total_size += os.path.getsize(full)
                file_count += 1
            except OSError:
                continue
    return file_count, total_size


def clear_dir(path):
    """清空目录内容，返回 (删除文件数, 失败文件数, 释放字节数)

    逐文件删除而非 shutil.rmtree：某个文件被占用时只记一次失败，
    其余文件仍会被清理（rmtree 会在第一处异常整体中断）。
    """
    removed = 0
    failed = 0
    freed = 0

    for root, dirs, files in os.walk(path, topdown=False, followlinks=False):
        for name in files:
            full = os.path.join(root, name)
            try:
                size = os.path.getsize(full)
            except OSError:
                size = 0
            try:
                os.remove(full)
                removed += 1
                freed += size
            except OSError:
                failed += 1

        # 目录清空后再移除；符号链接只删链接本身
        for name in dirs:
            full = os.path.join(root, name)
            try:
                if os.path.islink(full):
                    os.unlink(full)
                else:
                    os.rmdir(full)
            except OSError:
                continue

    return removed, failed, freed


def format_size(size):
    """字节数转可读文本"""
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024.0 or unit == "GB":
            if unit == "B":
                return f"{int(value)} B"
            return f"{value:.1f} {unit}"
        value /= 1024.0
    return f"{value:.1f} GB"


def display_path(path):
    """把绝对路径缩写为 %LOCALAPPDATA%/~/ 开头，便于在弹窗里阅读"""
    local = os.environ.get("LOCALAPPDATA", "")
    if local and path.lower().startswith(local.lower()):
        return "%LOCALAPPDATA%" + path[len(local):]
    home = os.path.expanduser("~")
    if home and home != "~" and path.startswith(home):
        return "~" + path[len(home):]
    return path


# ── 弹窗内的单条缓存目录 ────────────────────────────────────────
class BetterExperie_GPU_CacheEntry(bpy.types.PropertyGroup):
    label: bpy.props.StringProperty(name="名称")
    path: bpy.props.StringProperty(name="路径")
    selected: bpy.props.BoolProperty(name="清理", default=True)
    file_count: bpy.props.IntProperty(name="文件数", default=0)
    total_size: bpy.props.IntProperty(name="大小", default=0)


# ── 算子：清理 GPU 缓存 ─────────────────────────────────────────
class BetterExperie_OT_CleanGPUCache(bpy.types.Operator):
    """清理显卡着色器缓存（NVIDIA / AMD / Intel / DirectX）"""
    bl_idname = "better_experie.clean_gpu_cache"
    bl_label = "清理GPU缓存"
    bl_description = (
        "清理 NVIDIA / AMD / Intel 及 DirectX 的着色器缓存。"
        "这些缓存由驱动自动重建，清理后首次渲染/视口着色会稍慢，不影响文件数据"
    )
    bl_options = {'REGISTER'}

    entries: bpy.props.CollectionProperty(type=BetterExperie_GPU_CacheEntry)

    def _refresh_entries(self):
        """重新检测缓存目录并统计大小"""
        self.entries.clear()
        for label, path in get_cache_dirs():
            entry = self.entries.add()
            entry.label = label
            entry.path = path
            entry.selected = True
            entry.file_count, entry.total_size = scan_dir(path)

    def invoke(self, context, event):
        self._refresh_entries()
        if not len(self.entries):
            self.report({'WARNING'}, "未找到可清理的 GPU 缓存目录")
            return {'CANCELLED'}
        return context.window_manager.invoke_props_dialog(self, width=560)

    def draw(self, context):
        layout = self.layout

        layout.label(text="检测到以下 GPU 着色器缓存，勾选后确定清理：", icon="INFO")

        box = layout.box()
        if not len(self.entries):
            box.label(text="未检测到缓存目录", icon="ERROR")
        else:
            total_size = 0
            total_files = 0
            for entry in self.entries:
                row = box.row(align=True)
                row.prop(entry, "selected", text="")

                col = row.column(align=True)
                col.label(text=entry.label)
                col.label(
                    text=f"{display_path(entry.path)}    {format_size(entry.total_size)} / {entry.file_count} 个文件"
                )

                if entry.selected:
                    total_size += entry.total_size
                    total_files += entry.file_count

            layout.separator(type="LINE")
            row = layout.row()
            row.label(
                text=f"已勾选：{format_size(total_size)} / {total_files} 个文件",
                icon="CHECKMARK",
            )

        col = layout.column(align=True)
        col.label(text="缓存会被驱动自动重建，清理不会损坏工程文件", icon="BLANK1")
        col.label(text="若 Blender 正在使用这些缓存，建议清理后重启 Blender", icon="ERROR")

    def execute(self, context):
        # 未经弹窗直接执行（菜单快捷键/脚本调用）时，默认清理全部检测到的目录
        if not len(self.entries):
            self._refresh_entries()
            for entry in self.entries:
                entry.selected = True

        targets = [entry for entry in self.entries if entry.selected]
        if not targets:
            self.report({'WARNING'}, "未勾选任何缓存目录")
            return {'CANCELLED'}

        removed = 0
        failed = 0
        freed = 0
        for entry in targets:
            dir_removed, dir_failed, dir_freed = clear_dir(entry.path)
            removed += dir_removed
            failed += dir_failed
            freed += dir_freed

        message = f"GPU缓存清理完成：删除 {removed} 个文件，释放 {format_size(freed)}"
        if failed:
            message += f"，{failed} 个文件被占用未能删除"
            self.report({'WARNING'}, message)
        else:
            self.report({'INFO'}, message)
        return {'FINISHED'}


classes = (
    BetterExperie_GPU_CacheEntry,
    BetterExperie_OT_CleanGPUCache,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
