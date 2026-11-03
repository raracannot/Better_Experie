# -*- coding: utf-8 -*-
"""工具模块：每个 util 子模块都能导入，纯函数行为正确。"""

import importlib


def run(context):
    results = []
    addon = context["addon_name"]

    utils = context["find_module"]("utils")
    modules = getattr(utils, "UTIL_MODULES", ()) if utils else ()

    bad = []
    for name in modules:
        try:
            importlib.import_module(f"{addon}.utils.{name}")
        except Exception as exc:
            bad.append(f"{name}: {exc}")
    results.append({"name": "utils 子模块全部可导入", "ok": not bad, "detail": str(bad[:3])})

    try:
        compare = importlib.import_module(f"{addon}.utils.compare_versions")
    except Exception as exc:
        results.append({"name": "compare_versions", "ok": False, "detail": str(exc)})
        return results

    parsed = compare.parse_version_to_list("v5.2.0-beta")
    results.append({"name": "版本解析 5.2 系", "ok": parsed[:3] == [5, 2, 0], "detail": str(parsed)})
    results.append({"name": "版本解析容错",
                    "ok": compare.parse_version_to_list("") == [0, 0, 0, 0, 0],
                    "detail": str(compare.parse_version_to_list(""))})
    results.append({"name": "旧版本判定",
                    "ok": bool(compare.is_version_older("1.2.0", "1.2.1"))
                    and not bool(compare.is_version_older("1.2.1", "1.2.0")),
                    "detail": ""})

    return results
