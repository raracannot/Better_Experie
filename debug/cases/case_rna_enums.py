# -*- coding: utf-8 -*-
"""RNA 体检：操作符的枚举项还在、数值范围没被写反。

新版本删掉某个枚举值（图标、空间类型、着色方式……）是典型的"静默失效"来源。
"""

# 动态枚举（items 是回调）在裸上下文里天然可能为空，这里容忍一部分
MAX_EMPTY_ENUMS = 12


def _enum_items(prop):
    try:
        return list(prop.enum_items)
    except Exception:
        return []


def run(context):
    import bpy

    module = getattr(bpy.ops, "better_experie", None)
    if module is None:
        return [{"name": "操作符模块", "ok": False, "detail": "不存在"}]

    names = sorted(name for name in dir(module) if not name.startswith("_"))
    empty_enums = []
    bad_ranges = []
    checked = 0

    for name in names:
        try:
            rna = getattr(module, name).get_rna_type()
        except Exception:
            continue
        for prop in rna.properties:
            if prop.identifier in ("rna_type",):
                continue
            if prop.type == 'ENUM':
                checked += 1
                items = _enum_items(prop)
                # 动态枚举（items 回调）在本上下文可能为空，容忍
                if not items:
                    empty_enums.append(f"{name}.{prop.identifier}")
            elif prop.type in {'INT', 'FLOAT'}:
                try:
                    if prop.hard_min > prop.hard_max:
                        bad_ranges.append(f"{name}.{prop.identifier}")
                except Exception:
                    pass

    results = [{
        "name": f"空枚举属性 <= {MAX_EMPTY_ENUMS}",
        "ok": len(empty_enums) <= MAX_EMPTY_ENUMS,
        "detail": f"{len(empty_enums)}/{checked}: {empty_enums[:6]}",
    }, {
        "name": "数值范围未写反",
        "ok": not bad_ranges,
        "detail": str(bad_ranges[:6]),
    }]

    # 偏好设置里的枚举也要有值
    try:
        prefs = bpy.context.preferences.addons[context["addon_name"]].preferences
        rna = prefs.bl_rna
        prefs_empty = [prop.identifier for prop in rna.properties
                       if prop.type == 'ENUM' and not _enum_items(prop)]
        results.append({"name": "偏好设置枚举有值", "ok": not prefs_empty,
                        "detail": str(prefs_empty[:5])})
    except Exception as exc:
        results.append({"name": "偏好设置枚举有值", "ok": False, "detail": str(exc)})

    return results
