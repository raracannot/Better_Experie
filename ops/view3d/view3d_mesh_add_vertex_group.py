# 智能属性写入：顶点组 / 属性组（点·边·面 × 布尔·浮点·整数·颜色）/ 颜色组（点·面拐）

import bpy
import bmesh

KIND_ITEMS = (
    ('VGROUP', "顶点组", "写到对象的顶点组（点域浮点权重 0-1）"),
    ('ATTR', "属性组", "写到网格的通用属性（点/边/面 × 布尔/浮点/整数/颜色）"),
    ('COLOR', "颜色组", "写到网格的颜色属性（点/面拐，浮点颜色）"),
)

TYPE_TO_ATTR = {
    'BOOLEAN': 'BOOLEAN',
    'FLOAT': 'FLOAT',
    'INT': 'INT',
    'COLOR': 'FLOAT_COLOR',
}

ATTR_TO_LAYER = {
    'BOOLEAN': 'bool',
    'FLOAT': 'float',
    'INT': 'int',
    'COLOR': 'float_color',
}

ZERO_VALUE = {
    'BOOLEAN': False,
    'FLOAT': 0.0,
    'INT': 0,
    'COLOR': (0.0, 0.0, 0.0, 0.0),
}

DEFAULT_NAMES = {
    ('VGROUP', 'POINT', 'FLOAT'): "verts_group",
    ('ATTR', 'EDGE', 'FLOAT'): "edges_group",
    ('ATTR', 'FACE', 'BOOLEAN'): "faces_group",
}


def _kind(op):
    return getattr(op, "kind", 'VGROUP')


# ── 动态枚举 ──

def _domain_items(self, context):
    if _kind(self) == 'COLOR':
        return [('POINT', "点", ""), ('CORNER', "面拐", "")]
    return [('POINT', "点", ""), ('EDGE', "边", ""), ('FACE', "面", "")]


def _type_items(self, context):
    kind = _kind(self)
    if kind == 'VGROUP':
        return [('FLOAT', "浮点", "")]
    if kind == 'COLOR':
        return [('COLOR', "颜色", "")]
    items = [('BOOLEAN', "布尔", ""), ('FLOAT', "浮点", ""), ('INT', "整数", "")]
    if getattr(self, "domain", 'POINT') == 'POINT':
        items.append(('COLOR', "颜色", ""))
    return items


def _target_items(self, context):
    """按 类型 + 域 + 参数类型 过滤可复用的目标"""
    names = []
    kind = _kind(self)
    domain = getattr(self, "domain", 'POINT')
    data_type = getattr(self, "data_type", 'FLOAT')

    if kind == 'VGROUP':
        for obj in context.selected_objects:
            if obj.type == 'MESH':
                names.extend(vg.name for vg in obj.vertex_groups)
    else:
        want = TYPE_TO_ATTR[data_type]
        for obj in context.selected_objects:
            if obj.type != 'MESH':
                continue
            for attr in obj.data.attributes:
                if attr.domain == domain and attr.data_type == want:
                    names.append(attr.name)

    items = [('CREATE_A_NEW_VERTEX_GROUPS', "新建", "新建一个目标")]
    for name in sorted(set(names)):
        items.append((name, name, f"使用现有的目标: {name}"))
    return items


def _coerce(op):
    """把三个枚举收敛到合法组合"""
    kind = op.kind
    if kind == 'VGROUP':
        if op.domain != 'POINT':
            op.domain = 'POINT'
        if op.data_type != 'FLOAT':
            op.data_type = 'FLOAT'
    elif kind == 'COLOR':
        if op.domain not in {'POINT', 'CORNER'}:
            op.domain = 'POINT'
        if op.data_type != 'COLOR':
            op.data_type = 'COLOR'
    else:
        if op.domain == 'CORNER':
            op.domain = 'POINT'
        if op.data_type == 'COLOR' and op.domain != 'POINT':
            op.data_type = 'FLOAT'


def _on_change(self, context):
    _coerce(self)


def preset_for_mode(select_mode):
    """按选择模式给出预设（invoke 与测试共用）"""
    if select_mode[1]:
        return {'kind': 'ATTR', 'domain': 'EDGE', 'data_type': 'FLOAT',
                'name': "edges_group", 'value_float': 1.0}
    if select_mode[2]:
        return {'kind': 'ATTR', 'domain': 'FACE', 'data_type': 'BOOLEAN',
                'name': "faces_group", 'value_bool': True}
    return {'kind': 'VGROUP', 'domain': 'POINT', 'data_type': 'FLOAT',
            'name': "verts_group", 'value_float': 1.0}


# ── 写入（模块级，便于测试） ──

def unique_attr_name(mesh, base):
    """属性名跨域/类型全局唯一；重名时自己加 .001。

    不能依赖 bmesh 层自动改名：实测同名跨域创建会把已有属性顶掉。
    """
    existing = {attr.name for attr in mesh.attributes}
    if base not in existing:
        return base
    index = 1
    while f"{base}.{index:03d}" in existing:
        index += 1
    return f"{base}.{index:03d}"


def _all_elements(bm, domain):
    if domain == 'POINT':
        return bm.verts
    if domain == 'EDGE':
        return bm.edges
    if domain == 'FACE':
        return bm.faces
    return bm.loops


def _selected_elements(bm, domain):
    if domain == 'POINT':
        return [v for v in bm.verts if v.select]
    if domain == 'EDGE':
        return [e for e in bm.edges if e.select]
    if domain == 'FACE':
        return [f for f in bm.faces if f.select]
    return [loop for face in bm.faces if face.select for loop in face.loops]


def _get_layer(bm, mesh, domain, data_type, name):
    coll = {'POINT': bm.verts, 'EDGE': bm.edges,
            'FACE': bm.faces, 'CORNER': bm.loops}[domain]
    layers = getattr(coll.layers, ATTR_TO_LAYER[data_type])
    layer = layers.get(name)
    if layer is None:
        layer = layers.new(unique_attr_name(mesh, name))
    return layer


def write_attribute(bm, mesh, domain, data_type, name, mode, value):
    """写通用属性 / 颜色属性，返回 (实际名称, 写入元素数)"""
    layer = _get_layer(bm, mesh, domain, data_type, name)
    zero = ZERO_VALUE[data_type]

    if mode == 'REPLACE':
        for elem in _all_elements(bm, domain):
            elem[layer] = zero

    target_value = zero if mode == 'SUBTRACT' else value
    selected = _selected_elements(bm, domain)
    for elem in selected:
        elem[layer] = target_value

    bmesh.update_edit_mesh(mesh, loop_triangles=False, destructive=False)
    return layer.name, len(selected)


def write_vertex_group(obj, indices, name, weight, mode):
    """写顶点组，返回 (实际名称, 顶点数)。调用前需处于物体模式"""
    group = obj.vertex_groups.get(name) or obj.vertex_groups.new(name=name)
    if indices:
        group.add(indices, weight, mode)
    return group.name, len(indices)


class BetterExperie_OT_MeshAddVertexGroup(bpy.types.Operator):
    bl_idname = "better_experie.mesh_add_vertex_group"
    bl_label = "保存选集"
    bl_description = "按模式保存所选元素为选集：点 → 顶点组，边 → 边属性，面 → 面属性；也可手动切换为颜色组"
    bl_options = {'REGISTER', 'UNDO'}

    operator_mode: bpy.props.EnumProperty(
        name="操作模式",
        items=[
            ('ADD', "添加", "只写选中元素，其它保持不动"),
            ('REPLACE', "替换", "先把全部元素清零，再写入选中元素"),
            ('SUBTRACT', "移除", "把选中元素清零"),
        ], default='ADD')

    kind: bpy.props.EnumProperty(
        name="属性类型", items=KIND_ITEMS, default='VGROUP', update=_on_change)
    domain: bpy.props.EnumProperty(
        name="属性域", items=_domain_items, default=0, update=_on_change)
    data_type: bpy.props.EnumProperty(
        name="参数类型", items=_type_items, default=0, update=_on_change)

    target_list: bpy.props.EnumProperty(
        name="属性名称", description="指定要写入的目标", items=_target_items)
    new_name: bpy.props.StringProperty(name="新建名称", default="")

    value_float: bpy.props.FloatProperty(name="浮点值", default=1.0, min=0.0, max=1.0)
    value_int: bpy.props.IntProperty(name="整数值", default=1)
    value_bool: bpy.props.BoolProperty(name="布尔值", default=True)
    value_color: bpy.props.FloatVectorProperty(
        name="颜色", subtype='COLOR', size=4, min=0.0, max=1.0,
        default=(1.0, 1.0, 1.0, 1.0))

    @classmethod
    def poll(cls, context):
        return context.active_object and context.mode == 'EDIT_MESH'

    def _value(self):
        if self.data_type == 'BOOLEAN':
            return self.value_bool
        if self.data_type == 'INT':
            return self.value_int
        if self.data_type == 'COLOR':
            return tuple(self.value_color)
        return self.value_float

    def _target_name(self):
        if self.target_list == 'CREATE_A_NEW_VERTEX_GROUPS':
            name = self.new_name.strip()
        else:
            name = self.target_list
        if name:
            return name
        return DEFAULT_NAMES.get((self.kind, self.domain, self.data_type),
                                 f"{self.domain.lower()}_group")

    def execute(self, context):
        _coerce(self)
        active_object = context.active_object
        selected_objects = [obj for obj in context.selected_objects
                            if obj.type == 'MESH' and obj.mode == 'EDIT']
        requested = self._target_name()

        total_obj = 0
        total_elem = 0
        actual_name = requested

        for obj in selected_objects:
            bpy.context.view_layer.objects.active = obj
            mesh = obj.data
            bm = bmesh.from_edit_mesh(mesh)
            bm.verts.ensure_lookup_table()

            if self.kind == 'VGROUP':
                indices = [v.index for v in bm.verts if v.select]
                bm.free()
                bpy.ops.object.mode_set(mode='OBJECT')
                actual_name, count = write_vertex_group(
                    obj, indices, requested, self.value_float, self.operator_mode)
                bpy.ops.object.mode_set(mode='EDIT')
            else:
                actual_name, count = write_attribute(
                    bm, mesh, self.domain, self.data_type,
                    requested, self.operator_mode, self._value())
                bm.free()

            total_elem += count
            total_obj += 1

        if active_object:
            bpy.context.view_layer.objects.active = active_object

        if actual_name != requested:
            self.report({'WARNING'},
                        f"名称【{requested}】已被其它属性占用，已新建为【{actual_name}】")

        kind_text = {'VGROUP': "顶点组", 'ATTR': "属性", 'COLOR': "颜色属性"}[self.kind]
        unit = {'POINT': "个点", 'EDGE': "条边", 'FACE': "个面", 'CORNER': "个面拐"}[self.domain]
        self.report({'INFO'},
                    f"写入{kind_text}【{actual_name}】，共 {total_obj} 个对象，{total_elem} {unit}")
        return {'FINISHED'}

    def invoke(self, context, event):
        preset = preset_for_mode(context.tool_settings.mesh_select_mode)
        self.kind = preset['kind']
        _coerce(self)
        self.domain = preset['domain']
        self.data_type = preset['data_type']
        self.new_name = preset['name']
        self.target_list = "CREATE_A_NEW_VERTEX_GROUPS"
        if 'value_float' in preset:
            self.value_float = preset['value_float']
        if 'value_bool' in preset:
            self.value_bool = preset['value_bool']
        self.execute(context)
        return {'FINISHED'}

    def draw(self, context):
        layout = self.layout
        col = layout.column(align=True)

        row = col.row()
        split = row.split(factor=0.3)
        split.label(text="操作模式")
        split.prop(self, "operator_mode", text="")

        row = col.row()
        split = row.split(factor=0.3)
        split.label(text="属性类型")
        split.prop(self, "kind", text="")

        row = col.row()
        split = row.split(factor=0.3)
        split.label(text="属性名称")
        sub = split.row(align=True)
        sub.prop(self, "target_list", text="")
        if self.target_list == "CREATE_A_NEW_VERTEX_GROUPS":
            sub.prop(self, "new_name", text="")

        row = col.row()
        split = row.split(factor=0.3)
        split.label(text="属性域")
        split.prop(self, "domain", text="")

        row = col.row()
        split = row.split(factor=0.3)
        split.label(text="参数类型")
        if self.kind == 'VGROUP':
            split.label(text="该类型仅限浮点")
        elif self.kind == 'COLOR':
            split.label(text="该类型仅限颜色")
        else:
            split.prop(self, "data_type", text="")

        row = col.row()
        split = row.split(factor=0.3)
        split.label(text="参数数值")
        if self.data_type == 'BOOLEAN':
            split.prop(self, "value_bool", text="")
        elif self.data_type == 'INT':
            split.prop(self, "value_int", text="")
        elif self.data_type == 'COLOR':
            split.prop(self, "value_color", text="")
        else:
            split.prop(self, "value_float", text="", slider=True)


classes = (
    BetterExperie_OT_MeshAddVertexGroup,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
