# -*- coding: utf-8 -*-
"""优化加速：空材质槽清理（olpha 报过的 AttributeError 回归）。"""

import bpy


def _make_object(name, materials):
    mesh = bpy.data.meshes.new(name + "_mesh")
    mesh.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [], [(0, 1, 2)])
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    for mat_name in materials:
        if mat_name is None:
            obj.data.materials.append(bpy.data.materials.new(name + "_tmp"))
            obj.material_slots[len(obj.material_slots) - 1].material = None
        else:
            if mat_name not in bpy.data.materials:
                bpy.data.materials.new(mat_name)
            obj.data.materials.append(bpy.data.materials[mat_name])
    return obj


def _slots(obj):
    return [(slot.material.name if slot.material else None) for slot in obj.material_slots]


def run(context):
    results = []

    obj = _make_object("BET_slot_obj", [None, "BET_mat_keep"])
    before = _slots(obj)
    results.append({"name": "测试对象准备", "ok": before == [None, "BET_mat_keep"],
                    "detail": str(before)})

    try:
        result = bpy.ops.better_experie.system_optimization('EXEC_DEFAULT')
        error = ""
    except Exception as exc:
        result, error = None, f"{type(exc).__name__}: {exc}"

    results.append({"name": "优化加速不抛异常", "ok": not error, "detail": error})
    results.append({"name": "优化加速返回 FINISHED", "ok": result == {'FINISHED'},
                    "detail": str(result)})

    if obj.name in bpy.data.objects:
        after = _slots(bpy.data.objects[obj.name])
        results.append({"name": "空材质槽已删除", "ok": after == ["BET_mat_keep"],
                        "detail": str(after)})
    else:
        results.append({"name": "空材质槽已删除", "ok": False, "detail": "对象消失了"})

    return results
