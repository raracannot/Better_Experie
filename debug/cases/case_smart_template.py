# -*- coding: utf-8 -*-
"""智能模板表达式 + token 组装：跨版本（4.5 ~ 5.3）回归。"""

import bpy


def _compositor_tree(scene, name):
    """按版本建一棵合成节点树：5.3+ 走 Effects Stack，5.0+ 走单树，4.x 走 use_nodes。"""
    if hasattr(scene, "compositor_effects"):
        bpy.ops.scene.add_compositor_effect()
        effect = scene.compositor_effects[-1]
        tree = bpy.data.node_groups.new(name, "CompositorNodeTree")
        effect.node_group = tree
        return tree
    if bpy.app.version >= (5, 0, 0):
        tree = bpy.data.node_groups.new(name, "CompositorNodeTree")
        scene.compositing_node_group = tree
        return tree
    scene.use_nodes = True
    return scene.node_tree


def run(context):
    results = []

    st = context["find_module"]("ops.other.other_render_smart_template")
    tk = context["find_module"]("ops.other.other_smart_template_token")
    if st is None or tk is None:
        return [{"name": "模块导入", "ok": False, "detail": "找不到智能模板/token 模块"}]

    scene = bpy.context.scene

    # 1) 场景表达式写回 + 预览
    settings = scene.better_experie_smart_template
    settings.enabled = True
    settings.expression = "//{blend_name}_{batch:###}"
    st.update_smart_template_base(scene)
    results.append({
        "name": "场景表达式预览",
        "ok": str(settings.preview_path).endswith("_000"),
        "detail": settings.preview_path,
    })

    # 2) Token 词表全部可解析（点出来的按钮不能报"未知变量"）
    variables = st.get_template_variables(scene)
    variables.update({"scene_filepath": "X:/out", "node_name": "BET_node",
                      "node_tree_name": "BET_tree"})
    bad = []
    for name in tk.TOKEN_LABELS:
        try:
            st.parse_token(name, variables)
        except Exception as exc:
            bad.append(f"{name}:{exc}")
    results.append({"name": "token 词表全部可解析", "ok": not bad, "detail": str(bad[:3])})

    # 3) File Output 节点模板写回
    tree = _compositor_tree(scene, "BET_comp_tree")
    node = tree.nodes.new("CompositorNodeOutputFile")
    node.name = "BET_FileOutput"
    node_settings = node.better_experie_smart_template
    node_settings.enabled = True
    node_settings.directory_expression = "{scene_filepath}/BET_out"
    node_settings.directory_file_name = "{node_name}"

    st.apply_file_output_templates(scene)
    directory = st.get_file_output_node_directory(node)
    results.append({
        "name": "File Output 目录写回",
        "ok": "BET_out" in str(directory),
        "detail": str(directory),
    })
    results.append({
        "name": "File Output 能归属到场景",
        "ok": st.get_node_owner_scene(node) is not None,
        "detail": "",
    })

    # 4) 5.3 效果栈：多棵树都要被扫到
    trees = st.get_compositor_node_trees(scene)
    results.append({"name": "能枚举合成节点树", "ok": bool(trees),
                    "detail": str([t.name for t in trees])})

    # 5) 模板解析的边界情况
    results.append({"name": "batch 补零", "ok": st.parse_template("{batch:###}", scene) == "000",
                    "detail": st.parse_template("{batch:###}", scene)})

    year = st.parse_template("{datetime:YYYY}", scene)
    results.append({"name": "datetime 格式串", "ok": len(str(year)) == 4 and str(year).isdigit(),
                    "detail": str(year)})

    try:
        st.parse_template("{no_such_token_xyz}", scene)
        unknown_ok, unknown_detail = False, "没有报错"
    except st.BetterExperie_TemplateExpressionError as exc:
        unknown_ok, unknown_detail = True, str(exc)
    except Exception as exc:
        unknown_ok, unknown_detail = False, f"{type(exc).__name__}: {exc}"
    results.append({"name": "未知 token 报错", "ok": unknown_ok, "detail": unknown_detail})

    try:
        st.parse_template("{frame:zzzz}", scene)
        spec_ok, spec_detail = False, "非法格式串没有报错"
    except st.BetterExperie_TemplateExpressionError as exc:
        spec_ok, spec_detail = True, str(exc)
    except Exception as exc:
        spec_ok, spec_detail = False, f"{type(exc).__name__}: {exc}"
    results.append({"name": "非法格式串报错", "ok": spec_ok, "detail": spec_detail})

    return results
