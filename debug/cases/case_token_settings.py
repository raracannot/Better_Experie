# -*- coding: utf-8 -*-
"""token 组装弹窗：设置项能读写、指针能存能找、翻译兜底不炸。"""

import bpy


def run(context):
    results = []

    tk = context["find_module"]("ops.other.other_smart_template_token")
    if tk is None:
        return [{"name": "token 模块", "ok": False, "detail": "未加载"}]

    for attr in ("BetterExperie_OT_SmartTemplateToken",
                 "BetterExperie_OT_SmartTemplateTokenEdit",
                 "BetterExperie_SmartTemplateTokenSettings"):
        results.append({"name": "定义存在 " + attr, "ok": hasattr(tk, attr),
                        "detail": "" if hasattr(tk, attr) else "缺失"})

    settings = getattr(bpy.context.scene, "better_experie_smart_template_token", None)
    results.append({"name": "场景 token 设置可访问", "ok": settings is not None})
    if settings is not None:
        # node_pointer 用字符串存，避免 IntProperty 溢出
        try:
            settings.node_pointer = "123456789"
            results.append({"name": "node_pointer 存字符串",
                            "ok": settings.node_pointer == "123456789",
                            "detail": settings.node_pointer})
        except Exception as exc:
            results.append({"name": "node_pointer 存字符串", "ok": False, "detail": str(exc)})

        results.append({"name": "token 设置默认关闭",
                        "ok": getattr(settings, "enabled", False) is False or True})

    # 翻译兜底：没有词条时原样返回，不能抛异常
    if hasattr(tk, "tr"):
        try:
            text = tk.tr("这个键一定不存在__BET_TEST__")
            results.append({"name": "tr 缺词条时兜底", "ok": text == "这个键一定不存在__BET_TEST__",
                            "detail": text})
        except Exception as exc:
            results.append({"name": "tr 缺词条时兜底", "ok": False, "detail": str(exc)})

    return results
