
# import os
import bpy
import importlib

# 子模块清单（供热重载刷新；新增 util 时请同步）
UTIL_MODULES = (
    "clipboard_image",
    "compare_versions",
    "keymap_utils",
    "modal_border",
    "node_tree",
    "rara_snapper",
    "strips_utils",
    "transform_orientation",
    "camera_view_core",
)

# ADDON_FOLDER = dirname(dirname(realpath(__file__)))
# BACKUPS_FOLDER = abspath(join(ADDON_FOLDER, "src", "backups"))
# BACKUPS_PREFERENCES_FILE = join(BACKUPS_FOLDER, "preferences")

def get_addon_name():
    from .. import __package__ as base_package
    from .. import __name__ as base_name
    return base_package or base_name
    
def get_pref():
    from .. import __package__ as base_package
    try:
        return bpy.context.preferences.addons[base_package].preferences
    except (KeyError, AttributeError):
        # 插件注册中途（重载/热更新）addons 集合可能尚未包含本包名
        return None


def register():
    from . import keymap_utils
    keymap_utils.register()


def unregister():
    from . import keymap_utils
    keymap_utils.unregister()


def update():
    # 热重载时刷新所有 util 子模块（register_module.update 会按序调用）
    for name in UTIL_MODULES:
        try:
            module = importlib.import_module(f".{name}", __package__)
            importlib.reload(module)
        except Exception:
            pass
