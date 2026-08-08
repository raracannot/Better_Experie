# V2.0

import bpy
import os
import sys
import subprocess

import time
import ctypes

# ==================== 把剪贴板对象粘贴为Blender Image ====================
def import_image_from_clipboard() -> bpy.types.Image | None:
    """
    解析系统剪贴板并将结果传入为Blender Image对象
    :param: 虽无额外要求，但建议执行前确保剪贴板有有效图像
    :return: 成功返回bpy.types.Image，失败返回None
    """
    exts = (".png", ".jpg", ".jpeg", ".bmp", ".exr", ".webp", ".hdr", ".tga", ".tif", ".tiff")
    # 优先从文件路径加载，面向超大图像时有极强的兼容性，避免闪退
    paths = []
    try:
        if sys.platform == "win32":
            cmd = ('powershell -NoProfile -Command "[Console]::OutputEncoding='
                   '[System.Text.Encoding]::UTF8; (Get-Clipboard -Format FileDropList).FullName"')
            res = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', creationflags=0x08000000)
            if res.returncode == 0:
                paths = [p.strip() for p in res.stdout.splitlines() if p.strip()]
        elif sys.platform == "darwin":
            res = subprocess.run(["osascript", "-e", 'get POSIX path of (get clipboard as alias list)'], capture_output=True, text=True)
            if res.returncode == 0:
                paths = [p.strip() for p in res.stdout.splitlines() if p.strip()]
        elif sys.platform.startswith("linux"):
            def cmd_exists(cmd):
                return subprocess.run(["which", cmd], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL ).returncode == 0
            tool = None
            if cmd_exists("xclip"):
                tool = ["xclip", "-selection", "clipboard", "-t", "text/uri-list", "-o"]
            elif cmd_exists("wl-paste"):
                tool = ["wl-paste", "-t", "text/uri-list"]
            if tool:
                res = subprocess.run(tool, capture_output=True, text=True, stderr=subprocess.DEVNULL)
                if res.returncode == 0:
                    for line in res.stdout.splitlines():
                        line = line.strip()
                        if line.startswith("file://"):
                            paths.append(line[7:].replace("%20", " "))
    except:
        pass
    if paths:
        for p in paths:
            fp = os.path.abspath(p)
            if os.path.isfile(fp) and fp.lower().endswith(exts):
                try:
                    # 使用默认方法加载
                    clipboard_image = bpy.data.images.load(fp)
                    return clipboard_image
                except:
                    continue
    # 保底：原生剪贴板粘贴，支持直接解析像素数据，但是面对HDR超大图，有概率闪退 
    area = None
    space = None
    old_type = None
    old_image = None
    clipboard_image = None
    try:
        # 保存当前界面状态
        area = bpy.context.area
        if not area:
            print("错误：无可用的界面区域")
            return None  # 无可用区域，直接返回
        old_type = area.ui_type
        area.ui_type = 'IMAGE_EDITOR'
        # 保存图像编辑器的原始图像状态
        space = area.spaces.active
        old_image = space.image if space else None
        # 核心操作：粘贴剪贴板图像
        bpy.ops.image.clipboard_paste()
        # 粘贴成功：
        clipboard_image = space.image
        clipboard_image.pack()
    except Exception:
        # 任意步骤出错，都标记为粘贴失败
        clipboard_image = None
        print(f"未找到有效剪贴板图像数据")
    finally:
        # 无论成功/失败，恢复原始界面状态（不干扰用户操作）
        if space and old_image is not None:
            space.image = old_image        
        if area and old_type is not None:
            area.ui_type = old_type
    return clipboard_image


# ==================== 把Blender Image对象复制到剪贴板 ====================
def copy_image_to_clipboard(bimg: bpy.types.Image) -> bool:
    """
    把传入的Blender Image对象复制到系统剪贴板
    :param bimg: 要复制的Blender Image对象
    :return: 成功返回True，失败返回False
    """
    if not bimg:
        print("错误：传入的Image对象为空")
        return False
    area = None
    space = None
    old_type = None
    old_image = None
    try:
        # 获取当前界面区域，确保有可用区域
        area = bpy.context.area
        if not area:
            print("错误：无可用的界面区域")
            return False
        # 保存原始界面状态
        old_type = area.ui_type
        area.ui_type = 'IMAGE_EDITOR'        
        space = area.spaces.active
        old_image = space.image if space else None
        # 把目标图像设为图像编辑器的激活图像
        if space:
            space.image = bimg
            # print(bimg)
            # 执行剪贴板复制（clipboard_paste的逆操作）
            bpy.ops.image.clipboard_copy()
            return True
    except Exception as e:
        print(f"复制图像到剪贴板失败: {e}")
        return False
    finally:
        # 无论成功/失败，恢复原始界面状态
        if space and old_image is not None:
            space.image = old_image        
        if area and old_type is not None:
            area.ui_type = old_type


# ===================== 剪贴板非空校验 =====================
CLIPBOARD_CACHE = False
CLIPBOARD_LAST_CHECK = 0
def has_content_in_clipboard():
    global CLIPBOARD_CACHE, CLIPBOARD_LAST_CHECK
    now = time.time()
    if now - CLIPBOARD_LAST_CHECK < 0.5:
        return CLIPBOARD_CACHE
    CLIPBOARD_CACHE = False
    
    try:
        if sys.platform == "win32":
            # Windows: user32 API
            user32 = ctypes.WinDLL("user32", use_last_error=True)
            # CF_TEXT = 1
            CF_BITMAP = 2
            CF_HDROP = 15  # 文件

            user32.OpenClipboard(None)
            # user32.IsClipboardFormatAvailable(CF_TEXT)#不判断文本，只判断图像或文件
            has = (
                user32.IsClipboardFormatAvailable(CF_BITMAP)
                or user32.IsClipboardFormatAvailable(CF_HDROP)
            )
            user32.CloseClipboard()
            CLIPBOARD_CACHE = bool(has)

        # ----------------------------------------------------------------------
        elif sys.platform == "darwin":
            # macOS: 使用 ctypes 调用 Cocoa 原生 API（超快，无 osascript）
            objc = ctypes.CDLL("/usr/lib/libobjc.A.dylib")

            id = ctypes.c_void_p
            SEL = ctypes.c_void_p

            objc.objc_getClass.restype = id
            objc.sel_getUid.restype = SEL
            objc.objc_msgSend.restype = id

            pb_class = objc.objc_getClass(b"NSPasteboard")
            general_pb = objc.objc_msgSend(pb_class, objc.sel_getUid(b"generalPasteboard"))
            types = objc.objc_msgSend(general_pb, objc.sel_getUid(b"types"))
            count = objc.objc_msgSend(types, objc.sel_getUid(b"count"))

            CLIPBOARD_CACHE = count > 0

        # ----------------------------------------------------------------------
        elif sys.platform.startswith("linux"):
            CLIPBOARD_CACHE = True
            # 使用 subprocess 来检验，简直太慢了，想了想，还是不检验吧，免得影响面板绘制，那就要命了
            # try:
                # res = subprocess.run(["xclip", "-o", "-selection", "clipboard"],capture_output=True)
                # CLIPBOARD_CACHE = len(res.stdout) > 0
            # except:
                # try:
                    # res = subprocess.run(["wl-paste"], capture_output=True)
                    # CLIPBOARD_CACHE = len(res.stdout) > 0
                # except:
                    # pass

    except Exception:
        pass
        
    CLIPBOARD_LAST_CHECK = time.time()
    return CLIPBOARD_CACHE


