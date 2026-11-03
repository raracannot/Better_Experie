# -*- coding: utf-8 -*-
"""Better_Experie 快速自检入口。

用法（必须 GUI 模式，插件在 -b 模式下不注册）：

    blender.exe --python "<插件目录>/debug/run_tests.py"

可选参数（放在 `--` 之后）：

    --only smart_template,force_update     只跑指定用例
    --list                                 只列出用例，不执行
    --verbose                              打印每个用例的细节

输出约定（方便 agent 解析）：
    每个用例一行：  [PASS] 用例名
                    [FAIL] 用例名 :: 原因
    最后一行：      BET_RESULT {"version": "...", "pass": 12, "fail": 0, "skip": 0, "cases": [...]}

结果同时写到系统临时目录的 better_experie_debug_last.json。
"""

import glob
import importlib.util
import json
import os
import sys
import tempfile
import time
import traceback

import bpy

DEBUG_DIR = os.path.dirname(os.path.abspath(__file__))
ADDON_ROOT = os.path.dirname(DEBUG_DIR)
ADDON_NAME = os.path.basename(ADDON_ROOT)
CASES_DIR = os.path.join(DEBUG_DIR, "cases")
RESULT_FILE = os.path.join(tempfile.gettempdir(), "better_experie_debug_last.json")


def _argv():
    """取 `--` 之后的参数。"""
    args = sys.argv
    if "--" in args:
        return args[args.index("--") + 1:]
    return []


def _load_cases():
    # 不往插件目录写 __pycache__，保持仓库干净
    previous = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    files = sorted(glob.glob(os.path.join(CASES_DIR, "case_*.py")))
    cases = []
    try:
        for path in files:
            name = os.path.splitext(os.path.basename(path))[0]
            spec = importlib.util.spec_from_file_location("bet_" + name, path)
            module = importlib.util.module_from_spec(spec)
            try:
                spec.loader.exec_module(module)
            except Exception:
                print(f"[FAIL] {name} :: 载入失败\n{traceback.format_exc()}")
                continue
            cases.append((name, module))
    finally:
        sys.dont_write_bytecode = previous
    return cases


def _find_module(suffix):
    """按后缀找已加载的插件子模块（不依赖插件目录名）。

    必须限定在插件自己的包里：系统里可能还装着别的插件，
    它们的子模块名同样以 translation.en_US 之类结尾。
    """
    for name, module in list(sys.modules.items()):
        if name != ADDON_NAME and not name.startswith(ADDON_NAME + "."):
            continue
        if name.endswith(suffix):
            return module
    return None


def _cleanup():
    """清掉用例造出来的临时数据，避免互相影响。"""
    for obj in [o for o in bpy.data.objects if o.name.startswith("BET_")]:
        bpy.data.objects.remove(obj, do_unlink=True)
    for mesh in [m for m in bpy.data.meshes if m.name.startswith("BET_")]:
        bpy.data.meshes.remove(mesh)
    for group in [g for g in bpy.data.node_groups if g.name.startswith("BET_")]:
        bpy.data.node_groups.remove(group)
    for mat in [m for m in bpy.data.materials if m.name.startswith("BET_")]:
        bpy.data.materials.remove(mat)
    scene = bpy.context.scene
    try:
        if getattr(scene, "compositor_effects", None) is not None:
            while len(scene.compositor_effects):
                bpy.ops.scene.remove_compositor_effect()
    except Exception:
        pass


def main():
    argv = _argv()
    only = ""
    verbose = "--verbose" in argv
    if "--only" in argv:
        index = argv.index("--only")
        if index + 1 < len(argv):
            only = argv[index + 1]
    wanted = {item.strip() for item in only.split(",") if item.strip()}

    print(f"BET_START addon={ADDON_NAME} version={bpy.app.version_string} "
          f"background={bpy.app.background}")

    if bpy.app.background:
        print("[FAIL] 后台模式 :: 插件在 -b 模式不注册，请用 GUI 运行（去掉 -b）")
        print("BET_RESULT " + json.dumps({"version": bpy.app.version_string,
                                          "pass": 0, "fail": 1, "skip": 0,
                                          "cases": [{"name": "background",
                                                     "ok": False,
                                                     "detail": "need GUI"}]},
                                         ensure_ascii=False))
        return

    cases = _load_cases()
    if "--list" in argv:
        for name, _module in cases:
            print("CASE", name)
        print("BET_RESULT " + json.dumps({"version": bpy.app.version_string,
                                          "pass": 0, "fail": 0, "skip": len(cases),
                                          "cases": []}, ensure_ascii=False))
        return

    started = time.time()
    results = []

    # 插件本身先启用（已启用则无副作用）
    try:
        result = bpy.ops.preferences.addon_enable(module=ADDON_NAME)
        enabled = result == {'FINISHED'}
    except Exception as exc:
        enabled = False
        print(f"[FAIL] enable :: {exc}")
    results.append({"name": "enable", "ok": enabled,
                    "detail": "" if enabled else "addon_enable 失败"})

    context = {
        "addon_name": ADDON_NAME,
        "addon_root": ADDON_ROOT,
        "find_module": _find_module,
        "addon_enabled": enabled,
    }

    for name, module in cases:
        if wanted and name not in wanted:
            results.append({"name": name, "ok": True, "detail": "skipped"})
            continue
        try:
            case_results = module.run(context) or []
        except Exception:
            case_results = [{"name": name, "ok": False,
                             "detail": traceback.format_exc(limit=3)}]
        results.extend(case_results)
        _cleanup()

    for item in results:
        mark = "PASS" if item.get("ok") else "FAIL"
        line = f"[{mark}] {item.get('name', '?')}"
        if not item.get("ok") or verbose:
            line += " :: " + str(item.get("detail", "")).replace("\n", " | ")
        print(line)

    counted = [r for r in results if r.get("detail") != "skipped"]
    passed = sum(1 for r in counted if r.get("ok"))
    failed = len(counted) - passed
    payload = {
        "version": bpy.app.version_string,
        "addon": ADDON_NAME,
        "pass": passed,
        "fail": failed,
        "skip": len(results) - len(counted),
        "seconds": round(time.time() - started, 2),
        "cases": [{"name": r.get("name", "?"), "ok": r.get("ok", False),
                   "detail": str(r.get("detail", ""))}
                  for r in results if not r.get("ok")],
    }
    try:
        with open(RESULT_FILE, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=1)
    except Exception:
        pass

    print("BET_RESULT " + json.dumps(payload, ensure_ascii=False))
    print(f"BET_DONE pass={passed} fail={failed} 用时 {payload['seconds']}s "
          f"-> {RESULT_FILE}")


def _run_once():
    try:
        main()
    except Exception:
        print("[FAIL] runner ::")
        traceback.print_exc()
    finally:
        try:
            bpy.ops.wm.quit_blender()
        except Exception:
            pass
    return None


if bpy.app.background:
    _run_once()
else:
    bpy.app.timers.register(_run_once, first_interval=1.0)
