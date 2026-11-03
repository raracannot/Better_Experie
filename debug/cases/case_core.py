# -*- coding: utf-8 -*-
"""基础自检：插件注册出来的操作符 / 面板 / 属性是否齐全。"""

# 这些是各功能的关键入口，任何一个消失都说明注册链断了
OPERATORS = (
    "better_experie.reload_addon",
    "better_experie.check_update",
    "better_experie.force_update",
    "better_experie.smart_template_apply",
    "better_experie.smart_template_apply_node",
    "better_experie.smart_template_token",
    "better_experie.smart_template_token_edit",
    "better_experie.system_optimization",
    "better_experie.compositor_add_file_output",
    "better_experie.compositor_bake_node",
)

PANELS = (
    "BETTER_EXPERIE_PT_smart_template",
)

SCENE_PROPS = (
    "better_experie_smart_template",
    "better_experie_smart_template_token",
)


def run(context):
    import bpy

    results = []

    for full in OPERATORS:
        module, _, name = full.partition(".")
        try:
            getattr(getattr(bpy.ops, module), name)
            ok, detail = True, ""
        except Exception as exc:
            ok, detail = False, str(exc)
        results.append({"name": "操作符 " + full, "ok": ok, "detail": detail})

    for name in PANELS:
        exists = hasattr(bpy.types, name)
        results.append({"name": "面板 " + name, "ok": exists,
                        "detail": "" if exists else "未注册"})

    for name in SCENE_PROPS:
        exists = hasattr(bpy.context.scene, name)
        results.append({"name": "场景属性 " + name, "ok": exists,
                        "detail": "" if exists else "未注册"})

    try:
        prefs = bpy.context.preferences.addons[context["addon_name"]].preferences
        prefs_ok = prefs is not None
        prefs_detail = type(prefs).__name__ if prefs else "None"
    except Exception as exc:
        prefs_ok, prefs_detail = False, str(exc)
    results.append({"name": "偏好设置可用", "ok": prefs_ok, "detail": prefs_detail})

    # 强制更新模块的关键内部状态应当在
    fu = context["find_module"]("ops.other.other_force_update")
    results.append({"name": "强制更新模块可导入", "ok": fu is not None,
                    "detail": "" if fu else "导入失败"})
    if fu:
        for attr in ("_ROUTE_CACHE", "_find_proxies", "_build_attempts"):
            results.append({"name": "强制更新内部 " + attr, "ok": hasattr(fu, attr),
                            "detail": "" if hasattr(fu, attr) else "缺失"})

    return results
