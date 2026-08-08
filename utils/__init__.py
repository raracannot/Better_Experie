
# import os
import bpy

# ADDON_FOLDER = dirname(dirname(realpath(__file__)))
# BACKUPS_FOLDER = abspath(join(ADDON_FOLDER, "src", "backups"))
# BACKUPS_PREFERENCES_FILE = join(BACKUPS_FOLDER, "preferences")

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
