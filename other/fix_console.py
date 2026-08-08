import sys
import os
import bpy
from bpy.app.handlers import persistent

IS_WINDOWS = sys.platform == "win32"

@persistent
def load_handler(dummy):
    if not IS_WINDOWS:
        return

    from ..utils import get_pref

    try:
        prefs = get_pref()
    except (KeyError, AttributeError):
        return

    if not prefs.console_multilang_fix:
        return

    os.system("chcp 65001 > nul")


def register():
    bpy.app.handlers.load_post.append(load_handler)


def unregister():
    handlers = bpy.app.handlers.load_post
    if load_handler in handlers:
        handlers.remove(load_handler)
