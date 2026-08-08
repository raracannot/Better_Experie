# 快速跳转至已开启的系统文件夹

import os
import bpy
import subprocess
import time
import sys

from ...utils import get_pref

# 全局变量
_EXPLORER_CACHE = []
_EXPLORER_CACHE_UPDATING = False
_EXPLORER_CACHE_TIME = 0.0
_CACHE_INTERVAL = 10.0  # 秒
_POPEN_PROC = None       # 当前运行中的子进程
_POLL_TIMER = None       # 轮询定时器句柄

IS_WINDOWS = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"
IS_LINUX = sys.platform == "linux"

SYSTEM_FM_NAME = "Windows资源管理器" if IS_WINDOWS else "访达(Finder)" if IS_MAC else "文件管理器"


class BetterExperie_OT_QuickSetDirectory(bpy.types.Operator):
    bl_idname = "better_experie.quick_set_directory"
    bl_label = "快速跳转"
    bl_description = "将文件浏览器跳转至系统文件管理器当前打开的文件夹"
    bl_options = {'REGISTER', 'UNDO'}

    target_path: bpy.props.StringProperty()
    @classmethod
    def description(cls, context, properties):
        return f"识别到已开启的【{SYSTEM_FM_NAME}文件夹】：{os.path.basename(os.path.normpath(properties.target_path))}\n{properties.target_path}\n\n点击可将本【blender文件视图】快速跳转至已打开的【{SYSTEM_FM_NAME}文件夹】路径"
        
    def execute(self, context):
        if self.target_path:
            # path = os.path.normpath(self.target_path).encode()
            path = os.path.normpath(self.target_path).encode('utf-8')
            for area in context.screen.areas:
                if area.type == 'FILE_BROWSER':
                    for space in area.spaces:
                        if space.type == 'FILE_BROWSER':
                            space.params.directory = path
        return {'FINISHED'}

class BetterExperie_OT_ToggleExplorerHeader(bpy.types.Operator):
    bl_idname = "better_experie.toggle_explorer_header"
    bl_label = "切换标题栏显示"
    bl_description = f"切换文件管理器标题栏是否显示{SYSTEM_FM_NAME}路径"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        # prefs = bpy.context.preferences.addons[__package__].preferences
        prefs = get_pref()
        prefs.filebrowser_show_explorer_heder = not prefs.filebrowser_show_explorer_heder        

        if prefs.filebrowser_show_explorer_heder:
            self.report({'INFO'}, f"【{SYSTEM_FM_NAME}快速跳转栏】已显示于文件浏览器")
        else:
            self.report({'INFO'}, f"已退出【{SYSTEM_FM_NAME}快速跳转栏】，你可以前往偏好设置，或在文件浏览器页右键菜单重新启用")

        return {'FINISHED'}
        
class BetterExperie_OT_RefreshExplorerCache(bpy.types.Operator):
    bl_idname = "better_experie.refresh_explorer_cache"
    bl_label = "重建缓存"
    bl_description = "重新扫描已打开的系统文件管理器窗口并更新路径缓存"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def description(cls, context, properties):
        prefs = get_pref()
        # prefs = bpy.context.preferences.addons[__package__].preferences
        if prefs.filebrowser_auto_update:
            next_time = max(_CACHE_INTERVAL -( time.time() - _EXPLORER_CACHE_TIME),0.0)
            return f"重新识别已打开的【{SYSTEM_FM_NAME}文件夹】\n\n当前为【自动更新】模式，在{next_time:.1f}秒后会自动更新缓存\n你可以【ctrl+左键】点击本按钮，可将【自动更新】模式切换至【手动更新】"
        else:
            return f"重新识别已打开的【{SYSTEM_FM_NAME}文件夹】\n\n当前为【手动更新】模式，插件不会实时自动更新缓存，请点击本按钮进行缓存更新\n你可以【ctrl+左键】点击本按钮，可将【手动更新】模式切换至【自动更新】"
    
    def invoke(self, context, event):
        if event.ctrl:
            prefs = get_pref()
            prefs.filebrowser_auto_update = not prefs.filebrowser_auto_update
            mode = "自动更新" if prefs.filebrowser_auto_update else "手动更新"
            self.report({'INFO'}, f"已切换为【{mode}】模式")
            return {'FINISHED'}
        else:
            start_explorer_cache_update()
            self.report({'INFO'}, f"正在重新获取{SYSTEM_FM_NAME}已经打开的文件夹，并构建缓存...")
            return {'FINISHED'}

def start_explorer_cache_update():
    global _EXPLORER_CACHE_UPDATING, _POPEN_PROC, _POLL_TIMER
    
    if not (IS_WINDOWS or IS_MAC):
        return
    
    if _EXPLORER_CACHE_UPDATING or (_POPEN_PROC and _POPEN_PROC.poll() is None):
        return
    
    _EXPLORER_CACHE_UPDATING = True
    
    if IS_WINDOWS:
        ps_script = r'''
        [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
        $shell = New-Object -ComObject Shell.Application
        $paths = @()

        foreach ($w in $shell.Windows()) {
            try {
                if ($w.FullName -match "explorer.exe") {
                    $paths += $w.Document.Folder.Self.Path
                }
            } catch {}
        }

        # 去重并输出
        $paths | Select-Object -Unique | ForEach-Object { $_ }
        '''
        _POPEN_PROC = subprocess.Popen(
            ["powershell", "-NoProfile", "-Command", ps_script],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            encoding="utf-8", errors="ignore")
    elif IS_MAC:
        applescript = '''
        tell application "Finder"
            set windowList to every window
            set pathList to {}
            repeat with aWindow in windowList
                try
                    set currentPath to POSIX path of (target of aWindow as alias)
                    copy currentPath to end of pathList
                end try
            end repeat
            return pathList
        end tell
        '''
        _POPEN_PROC = subprocess.Popen(
            ["osascript", "-e", applescript],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            encoding="utf-8", errors="ignore")
    
    if _POLL_TIMER:
        bpy.app.timers.unregister(_POLL_TIMER)
    _POLL_TIMER = bpy.app.timers.register(_poll_explorer_subprocess, first_interval=0.1)

def _poll_explorer_subprocess():
    global _POPEN_PROC, _EXPLORER_CACHE, _EXPLORER_CACHE_UPDATING, _EXPLORER_CACHE_TIME, _POLL_TIMER
    
    if _POPEN_PROC is None:
        _EXPLORER_CACHE_UPDATING = False
        _POLL_TIMER = None
        return None
    
    ret = _POPEN_PROC.poll()
    if ret is None:
        return 0.2
    
    try:
        stdout, _ = _POPEN_PROC.communicate(timeout=1)
        new_cache = []
        if ret == 0 and stdout:
            if IS_MAC:
                raw_paths = [p.strip() for p in stdout.split(",") if p.strip()]
                new_cache = list(set(raw_paths))
            else:
                new_cache = [p.strip() for p in stdout.splitlines() if p.strip()]
        
        valid_cache = []
        for path in new_cache:
            if os.path.isdir(path):
                valid_cache.append(path)
        
        _EXPLORER_CACHE = new_cache
        _EXPLORER_CACHE_TIME = time.time()
    except subprocess.TimeoutExpired:
        print("警告：获取资源管理器路径超时")
        _EXPLORER_CACHE = []
        _EXPLORER_CACHE_TIME = time.time()
    except Exception as e:
        print(f"更新资源管理器路径时出错: {e}")
        _EXPLORER_CACHE = []
        _EXPLORER_CACHE_TIME = time.time()
    finally:
        _EXPLORER_CACHE_UPDATING = False
        _POPEN_PROC = None
        _POLL_TIMER = None
    
    return None


def get_explorer_paths_cached():
    prefs = get_pref()

    if _EXPLORER_CACHE == [] and time.time() - _EXPLORER_CACHE_TIME > _CACHE_INTERVAL:
        start_explorer_cache_update()
        return _EXPLORER_CACHE.copy()

    if prefs.filebrowser_auto_update:
        now = time.time()
        if now - _EXPLORER_CACHE_TIME > _CACHE_INTERVAL:
            start_explorer_cache_update()

    return _EXPLORER_CACHE.copy()


def quick_set_directory_draw(self, context):
    prefs = get_pref()
    if not (IS_WINDOWS or IS_MAC):
        return
    if not prefs.filebrowser_show_explorer_heder:
        return
    layout = self.layout
    row = layout.row(align=True)

    row.operator("better_experie.refresh_explorer_cache", text="", icon='FILE_REFRESH', depress=prefs.filebrowser_auto_update)

    cached = get_explorer_paths_cached()

    if len(cached) == 0:
        if _EXPLORER_CACHE_UPDATING:
            row.label(text="正在加载...", icon='FILE_REFRESH')
        else:
            row.label(text=f"暂无已打开的{SYSTEM_FM_NAME}窗口")
    else:
        row.separator()
        for p in cached:
            if not os.path.isdir(p):
                continue
            folder_name = os.path.basename(os.path.normpath(p)) + "\u200b"
            op = row.operator("better_experie.quick_set_directory", text=folder_name if folder_name else p, icon='FILE_FOLDER')
            op.target_path = p
    row.separator()
    row.operator("better_experie.toggle_explorer_header", text="", icon='PANEL_CLOSE')


classes = (
    BetterExperie_OT_QuickSetDirectory,
    BetterExperie_OT_ToggleExplorerHeader,
    BetterExperie_OT_RefreshExplorerCache,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.FILEBROWSER_PT_directory_path.append(quick_set_directory_draw)

def unregister():
    bpy.types.FILEBROWSER_PT_directory_path.remove(quick_set_directory_draw)
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

    global _POPEN_PROC, _POLL_TIMER
    if _POLL_TIMER:
        bpy.app.timers.unregister(_POLL_TIMER)
        _POLL_TIMER = None
    if _POPEN_PROC and _POPEN_PROC.poll() is None:
        _POPEN_PROC.terminate()
        _POPEN_PROC = None

# if __name__ == "__main__":
    # register()