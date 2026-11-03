# -*- coding: utf-8 -*-
"""真跑几个安全操作符：验证 execute 不只是注册成功，而是真的还能干活。"""

import bpy


def _mesh_object(name, location=(0, 0, 0)):
    mesh = bpy.data.meshes.new(name + "_mesh")
    mesh.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [], [(0, 1, 2)])
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    obj.location = location
    bpy.context.scene.collection.objects.link(obj)
    return obj


def _select(objs):
    bpy.ops.object.select_all(action='DESELECT')
    for obj in objs:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = objs[0] if objs else None


def _view3d_override():
    """找一个 3D 视口区域，用于需要 VIEW_3D 上下文的操作符。"""
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type != 'VIEW_3D':
                continue
            region = next((r for r in area.regions if r.type == 'WINDOW'), None)
            if region is not None:
                return {"window": window, "screen": window.screen,
                        "area": area, "region": region}
    return None


def run(context):
    results = []

    # 1) 清理空材质槽（batch 模式，不依赖编辑器上下文）
    obj = _mesh_object("BET_clear_mat")
    obj.data.materials.append(bpy.data.materials.new("BET_mat_a"))
    obj.data.materials.append(bpy.data.materials.new("BET_mat_b"))
    obj.material_slots[0].material = None
    _select([obj])
    try:
        result = bpy.ops.better_experie.clear_materials(clean_empty_only=True)
        results.append({"name": "清理材质：执行", "ok": result == {'FINISHED'}, "detail": str(result)})
        occupied = sum(1 for slot in obj.material_slots if slot.material is not None)
        results.append({"name": "清理材质：只剩有效槽", "ok": occupied == 1,
                        "detail": f"{occupied} 个有效槽"})
    except Exception as exc:
        results.append({"name": "清理材质：执行", "ok": False, "detail": str(exc)})

    # 2) 创建空物体组：应新建一个父级 Empty 并把所选对象挂上去
    a = _mesh_object("BET_group_a", (1, 0, 0))
    b = _mesh_object("BET_group_b", (2, 0, 0))
    _select([a, b])
    before = len(bpy.data.objects)
    try:
        result = bpy.ops.better_experie.create_empty_group()
        created = len(bpy.data.objects) - before
        parents = {obj.parent.name for obj in (a, b) if obj.parent}
        results.append({"name": "创建空物体组：执行", "ok": result == {'FINISHED'},
                        "detail": str(result)})
        results.append({"name": "创建空物体组：新增父级", "ok": created == 1 and len(parents) == 1,
                        "detail": f"新增{created} 父级{parents}"})
        for name in parents:
            empty = bpy.data.objects.get(name)
            if empty and empty.name.startswith("Empty_Group"):
                bpy.data.objects.remove(empty, do_unlink=True)
    except Exception as exc:
        results.append({"name": "创建空物体组：执行", "ok": False, "detail": str(exc)})

    # 3) 游标对齐到所选对象（poll 要求 VIEW_3D 上下文）
    c = _mesh_object("BET_cursor_obj", (3.5, -2.0, 1.25))
    _select([c])
    bpy.context.scene.cursor.location = (0.0, 0.0, 0.0)
    override = _view3d_override()
    if override is None:
        results.append({"name": "游标到所选：执行", "ok": True,
                        "detail": "没有 3D 视口，跳过"})
    else:
        try:
            with bpy.context.temp_override(**override):
                result = bpy.ops.better_experie.cursor_to_selected()
            cursor = bpy.context.scene.cursor.location
            ok_pos = all(abs(cursor[i] - c.location[i]) < 1e-4 for i in range(3))
            results.append({"name": "游标到所选：执行", "ok": result == {'FINISHED'},
                            "detail": str(result)})
            results.append({"name": "游标到所选：位置正确", "ok": ok_pos,
                            "detail": f"{tuple(round(v, 2) for v in cursor)}"})
        except Exception as exc:
            results.append({"name": "游标到所选：执行", "ok": False, "detail": str(exc)})

    return results
