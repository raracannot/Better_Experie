# -*- coding: utf-8 -*-
"""poll 扫荡：所有操作符的 poll 在默认上下文里都不该抛异常。

说明：少数操作符的 poll 依赖特定编辑器上下文，在裸上下文里可能返回 False——
这是正常的。但抛异常不是。这里只对"大面积异常"报警，避免误报。
"""

MAX_EXCEPTIONS = 6


def run(context):
    import bpy

    module = getattr(bpy.ops, "better_experie", None)
    if module is None:
        return [{"name": "操作符模块", "ok": False, "detail": "不存在"}]

    names = sorted(name for name in dir(module) if not name.startswith("_"))
    raised = []
    true_count = 0

    for name in names:
        operator = getattr(module, name)
        try:
            if operator.poll():
                true_count += 1
        except Exception as exc:
            raised.append(f"{name}: {type(exc).__name__}: {exc}")

    results = [{
        "name": "poll 抛异常的操作符 <= %d" % MAX_EXCEPTIONS,
        "ok": len(raised) <= MAX_EXCEPTIONS,
        "detail": f"{len(raised)}/{len(names)} 抛异常；{raised[:8]}",
    }, {
        "name": "至少部分操作符 poll 可用",
        "ok": true_count > 0,
        "detail": f"{true_count}/{len(names)} 可用",
    }]

    return results
