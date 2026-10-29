# 属性节点快速填写（属性下拉）
# 入口：节点编辑器标题栏 > 属性节点工具（NODE_MT_editor_menus，仅活动节点为「属性」节点时出现）
# 逻辑：依据活动属性节点的 attribute_type，列出该类型可读取的属性名，点选后写回节点

import bpy


# ── 获取活动属性节点 ────────────────────────────────────────────
def get_active_attribute_node(context=None):
    """返回节点编辑器中处于活动状态的「属性」节点，否则返回 None"""
    context = context or bpy.context

    space = getattr(context, "space_data", None)
    if space is None or getattr(space, "type", "") != 'NODE_EDITOR':
        return None

    node_tree = getattr(space, "node_tree", None)
    if node_tree is None:
        return None

    node = node_tree.nodes.active
    if node is not None and node.bl_idname == 'ShaderNodeAttribute':
        return node
    return None


# ── 收集属性名 ──────────────────────────────────────────────────
def _mesh_attribute_names(mesh):
    """读取网格类数据上的属性 / UV / 顶点色名称（缺失的集合自动跳过）

    过滤 Blender 内部属性（.select_vert、.corner_vert 等）：它们带内部标记或以
    "." 开头，用户可以读到但没有写入意义，混在下拉里只是噪音——与 Blender 自身
    属性搜索框的做法一致。
    """
    names = []
    if mesh is None:
        return names

    for attr in getattr(mesh, "attributes", ()):
        if getattr(attr, "is_internal", False) or attr.name.startswith("."):
            continue
        names.append(attr.name)
    for uv_layer in getattr(mesh, "uv_layers", ()):
        names.append(uv_layer.name)
    for color_attr in getattr(mesh, "color_attributes", ()):
        names.append(color_attr.name)
    return names


def _custom_property_names(id_block):
    """读取 ID 块上的自定义属性名，过滤 RNA 内部属性"""
    names = []
    if id_block is None:
        return names
    try:
        for key in id_block.keys():
            if key != "_RNA_UI":
                names.append(key)
    except (AttributeError, TypeError):
        pass
    return names


def collect_attributes_by_type(attr_type, context=None):
    """依据 attribute_type 返回可用属性名列表（已去重、保持出现顺序）"""
    context = context or bpy.context
    names = []
    obj = getattr(context, "active_object", None)

    if attr_type == 'GEOMETRY':
        if obj is not None:
            # 求值后：包含修改器生成的属性
            depsgraph = None
            try:
                depsgraph = context.evaluated_depsgraph_get()
            except (RuntimeError, AttributeError):
                depsgraph = None

            if depsgraph is not None:
                eval_obj = obj.evaluated_get(depsgraph)
                mesh = None
                try:
                    mesh = eval_obj.to_mesh()
                    names.extend(_mesh_attribute_names(mesh))
                except (RuntimeError, AttributeError):
                    pass
                finally:
                    # 必须配对释放，否则每开一次菜单泄漏一份临时网格
                    if mesh is not None:
                        try:
                            eval_obj.to_mesh_clear()
                        except (RuntimeError, AttributeError):
                            pass

            # 求值前：编辑模式下的改动、以及不经过修改器的数据
            names.extend(_mesh_attribute_names(getattr(obj, "data", None)))

            for vertex_group in obj.vertex_groups:
                names.append(vertex_group.name)

    elif attr_type == 'OBJECT':
        names.extend(_custom_property_names(obj))

    elif attr_type == 'INSTANCER':
        # 实例化属性由 Blender 固定提供，无需遍历
        names.extend(["instance_id", "instance_index"])

    elif attr_type == 'VIEW_LAYER':
        scene = getattr(context, "scene", None)
        if scene is not None:
            names.extend(_custom_property_names(scene))
            names.extend(_custom_property_names(getattr(scene, "world", None)))

    # 去重（属性可能同时出现在 attributes / uv_layers / color_attributes 中）
    seen = set()
    result = []
    for name in names:
        if name in seen:
            continue
        seen.add(name)
        result.append(name)
    return result


# ── 算子：把属性名写入活动节点 ──────────────────────────────────
class BetterExperie_OT_SetAttributeName(bpy.types.Operator):
    """将属性名写入活动「属性」节点"""
    bl_idname = "better_experie.set_attribute_name"
    bl_label = "设置属性名"
    bl_description = "将选中的属性名写入活动属性节点"
    bl_options = {'REGISTER', 'UNDO'}

    attribute_name: bpy.props.StringProperty(name="属性名")
    node_name: bpy.props.StringProperty(name="节点名")

    def _find_node(self, context):
        """优先按菜单展开时记录的节点名定位，避免中途切换活动节点写错对象"""
        if self.node_name:
            space = getattr(context, "space_data", None)
            node_tree = getattr(space, "node_tree", None)
            if node_tree is not None:
                node = node_tree.nodes.get(self.node_name)
                if node is not None and node.bl_idname == 'ShaderNodeAttribute':
                    return node
        return get_active_attribute_node(context)

    def execute(self, context):
        node = self._find_node(context)
        if node is None:
            self.report({'WARNING'}, "没有活动属性节点")
            return {'CANCELLED'}

        node.attribute_name = self.attribute_name
        self.report({'INFO'}, f"已设置属性名: {self.attribute_name}")
        return {'FINISHED'}


classes = (
    BetterExperie_OT_SetAttributeName,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
