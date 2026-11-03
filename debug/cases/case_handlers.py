# -*- coding: utf-8 -*-
"""回调注册：插件挂到 bpy.app.handlers 上的函数必须还在。"""

import bpy

LISTS = ("render_pre", "render_post", "render_complete", "load_post",
         "save_pre", "depsgraph_update_post", "frame_change_pre")


def _owned(callback, addon):
    module = getattr(callback, "__module__", "") or ""
    return module == addon or module.startswith(addon + ".")


def run(context):
    addon = context["addon_name"]
    results = []
    total = 0
    per_list = {}

    for name in LISTS:
        handlers = getattr(bpy.app.handlers, name, None)
        if handlers is None:
            continue
        mine = [cb for cb in handlers if _owned(cb, addon)]
        if mine:
            per_list[name] = len(mine)
        total += len(mine)

    results.append({"name": "至少注册 3 个回调", "ok": total >= 3,
                    "detail": f"{total} 个：{per_list}"})
    results.append({"name": "渲染前回调在位", "ok": per_list.get("render_pre", 0) >= 1,
                    "detail": str(per_list.get("render_pre", 0))})

    # 同一个回调函数被注册两次，是重复注册的明确信号
    duplicated = []
    for name in LISTS:
        mine = [cb for cb in getattr(bpy.app.handlers, name, []) if _owned(cb, addon)]
        if len(mine) != len(set(mine)):
            duplicated.append(name)
    results.append({"name": "回调无重复注册", "ok": not duplicated, "detail": str(duplicated)})

    return results
