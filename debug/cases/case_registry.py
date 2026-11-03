# -*- coding: utf-8 -*-
"""注册面清点：所有操作符 / 面板 / 注册类是否都在。"""


def _operator_names(bpy):
    module = getattr(bpy.ops, "better_experie", None)
    if module is None:
        return []
    return sorted(name for name in dir(module) if not name.startswith("_"))


def run(context):
    import bpy

    results = []
    names = _operator_names(bpy)
    results.append({"name": "操作符数量 >= 200", "ok": len(names) >= 200,
                    "detail": str(len(names))})

    broken = []
    unlabelled = []
    for name in names:
        try:
            rna = getattr(getattr(bpy.ops, "better_experie"), name).get_rna_type()
        except Exception as exc:
            broken.append(f"{name}: {exc}")
            continue
        if not rna.name:
            unlabelled.append(name)

    results.append({"name": "操作符 RNA 全部可读", "ok": not broken, "detail": str(broken[:4])})
    results.append({"name": "操作符都有标签", "ok": not unlabelled,
                    "detail": str(unlabelled[:6])})

    classes = [name for name in dir(bpy.types)
               if name.startswith(("BetterExperie_", "BETTER_EXPERIE_"))]
    results.append({"name": "注册类 >= 150", "ok": len(classes) >= 150,
                    "detail": str(len(classes))})

    panels = [name for name in classes if "_PT_" in name]
    results.append({"name": "面板 >= 10", "ok": len(panels) >= 10, "detail": str(len(panels))})

    menus = [name for name in classes if "_MT_" in name]
    results.append({"name": "菜单 >= 4", "ok": len(menus) >= 4, "detail": str(len(menus))})

    # 关键面板必须在（各自代表一个功能域）
    for required in ("BETTER_EXPERIE_PT_smart_template",):
        results.append({"name": "关键面板 " + required, "ok": required in classes,
                        "detail": "" if required in classes else "缺失"})

    return results
