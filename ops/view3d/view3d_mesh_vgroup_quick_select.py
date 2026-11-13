# 顶点组列表：每行一个快速选择按钮
#
# 原生顶点组列表 MESH_UL_vgroups 是 bl_ui 里的 Python 类（4.2 ~ 5.3 签名一致），
# 直接替换它的 draw_item 就能在每行最左侧加按钮，不需要重做面板。

import bmesh
import bpy
from bpy.props import EnumProperty, IntProperty

from ...addon_prefs import quick_group_tools_enabled

# 原生列表的类名（bl_ui.properties_data_mesh）
LIST_CLASS_NAME = "MESH_UL_vgroups"

# 支持的物体类型：网格与晶格的顶点组都能用原生 operator 选中；
# 蜡笔（GREASEPENCIL）的顶点组权重流程不同，暂不支持
SUPPORTED_TYPES = {'MESH', 'LATTICE'}

_original_draw_item = None


# ------------------------------------------------------------------------
# 补丁
# ------------------------------------------------------------------------
def enabled_object(context):
    """当前上下文里可以用行按钮的对象；不可用时返回 None"""
    obj = getattr(context, "object", None)
    if obj is None or obj.type not in SUPPORTED_TYPES:
        return None
    if not obj.vertex_groups:
        return None
    mode = obj.mode
    if mode == 'EDIT':
        return obj
    if (mode == 'WEIGHT_PAINT' and obj.type == 'MESH'
            and getattr(obj.data, "use_paint_mask_vertex", False)):
        return obj
    return None


def _patched_draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
    if enabled_object(context) is not None and quick_group_tools_enabled():
        row = layout.row(align=True)
        
        select_button = row.operator("better_experie.vgroup_quick_select", text="", emboss=False, icon='RESTRICT_SELECT_OFF')
        select_button.index = index
        
        save_button = row.operator("better_experie.vgroup_quick_assign", text="", emboss=False, icon='IMPORT')
        save_button.index = index
    
    if _original_draw_item is not None:
        _original_draw_item(self, context, layout, data, item, icon, active_data, active_propname, index)


def install_patch():
    """替换原生列表的 draw_item；返回是否成功"""
    global _original_draw_item

    cls = getattr(bpy.types, LIST_CLASS_NAME, None)
    if cls is None:
        return False

    current = getattr(cls, "draw_item", None)
    if current is None:
        return False
    if current is _patched_draw_item:
        return True

    try:
        import inspect
        if len(inspect.signature(current).parameters) != 9:
            print("[VGroup] draw_item 参数与预期不符，跳过行按钮")
            return False
    except Exception:
        pass

    _original_draw_item = current
    cls.draw_item = _patched_draw_item
    return True


def remove_patch():
    """还原原生 draw_item（只还原自己那一层）"""
    global _original_draw_item

    cls = getattr(bpy.types, LIST_CLASS_NAME, None)
    if cls is not None and _original_draw_item is not None:
        if getattr(cls, "draw_item", None) is _patched_draw_item:
            cls.draw_item = _original_draw_item
    _original_draw_item = None


# ------------------------------------------------------------------------
# 选择逻辑
# ------------------------------------------------------------------------
def _clear_selection(obj):
    """按类型清空当前选择"""
    if obj.mode == 'EDIT':
        if obj.type == 'MESH':
            bpy.ops.mesh.select_all(action='DESELECT')
        elif obj.type == 'LATTICE':
            bpy.ops.lattice.select_all(action='DESELECT')
        return
    if obj.type == 'MESH':
        for vertex in obj.data.vertices:
            vertex.select = False


def _in_group(element, index):
    for group in element.groups:
        if group.group == index and group.weight > 0.0:
            return True
    return False


def member_count(obj, index):
    """该顶点组里有权重的元素数量（顶点 / 晶格点）

    两个坑：
    - 网格编辑模式读 obj.data 是旧值，必须走 bmesh；
    - 晶格编辑模式读 point.groups 会让 Blender 直接崩（LatticePoint_groups_begin），
      所以那种情况返回 -1 表示"数不出来"，只报动作不报数量。
    """
    if obj.type == 'MESH':
        if obj.mode == 'EDIT':
            bm = bmesh.from_edit_mesh(obj.data)
            layer = bm.verts.layers.deform.active
            if layer is None:
                return 0
            return sum(1 for vert in bm.verts if vert[layer].get(index, 0.0) > 0.0)
        return sum(1 for vertex in obj.data.vertices if _in_group(vertex, index))

    if obj.type == 'LATTICE':
        if obj.mode == 'EDIT':
            return -1
        return sum(1 for point in obj.data.points if _in_group(point, index))
    return 0


def apply_state(obj, index, state):
    """委托原生算子做选择，覆盖编辑模式与权重绘制"""
    if state == 'REPLACE':
        _clear_selection(obj)
    obj.vertex_groups.active_index = index
    if state == 'REMOVE':
        bpy.ops.object.vertex_group_deselect()
    else:
        bpy.ops.object.vertex_group_select()


# ------------------------------------------------------------------------
# 保存选集（写权重）
# ------------------------------------------------------------------------
def _selected_indices(obj):
    if obj.mode == 'EDIT' and obj.type == 'MESH':
        bm = bmesh.from_edit_mesh(obj.data)
        return {vert.index for vert in bm.verts if vert.select}
    if obj.mode == 'EDIT':
        return {index for index, point in enumerate(obj.data.points) if point.select}
    return {vertex.index for vertex in obj.data.vertices if vertex.select}


def _select_all(obj, select):
    if obj.mode == 'EDIT':
        if obj.type == 'MESH':
            bpy.ops.mesh.select_all(action='SELECT' if select else 'DESELECT')
        else:
            bpy.ops.lattice.select_all(action='SELECT' if select else 'DESELECT')
        return
    for vertex in obj.data.vertices:
        vertex.select = select


def _restore_selection(obj, indices):
    _select_all(obj, False)
    if obj.mode == 'EDIT' and obj.type == 'MESH':
        bm = bmesh.from_edit_mesh(obj.data)
        for vert in bm.verts:
            vert.select = vert.index in indices
        bmesh.update_edit_mesh(obj.data, loop_triangles=False, destructive=False)
        return
    if obj.type == 'LATTICE':
        for index, point in enumerate(obj.data.points):
            point.select = index in indices
        return
    for vertex in obj.data.vertices:
        vertex.select = vertex.index in indices


def apply_weights(obj, index, state):
    """把当前选择写入该顶点组：加入 / 覆盖 / 移除"""
    obj.vertex_groups.active_index = index

    if state == 'ADD':
        bpy.ops.object.vertex_group_assign()
        return
    if state == 'REMOVE':
        bpy.ops.object.vertex_group_remove_from()
        return

    # 覆盖：先把整组清空，再把原来的选择恢复回来写权重
    selected = _selected_indices(obj)
    _select_all(obj, True)
    bpy.ops.object.vertex_group_remove_from()
    _restore_selection(obj, selected)
    bpy.ops.object.vertex_group_assign()


# ------------------------------------------------------------------------
# 算子
# ------------------------------------------------------------------------
class BetterExperie_OT_VGroupQuickSelect(bpy.types.Operator):
    bl_idname = "better_experie.vgroup_quick_select"
    bl_label = "选择顶点组"
    bl_description = "左键点击：添加该顶点组的顶点到选中项（加入）\nShift+左键点击：以该顶点组的顶点设为选中项（覆盖）\nCtrl+左键点击：从选中项中取消选中该顶点组的顶点（移除）"
    bl_options = {'REGISTER', 'UNDO'}

    index: IntProperty(
        name="顶点组下标",
        description="列表行下标；-1 表示当前活动顶点组",
        default=-1,
    )
    state: EnumProperty(
        name="选择方式",
        items=[
            ('REPLACE', "只选", "清空其它选择，只保留该顶点组的顶点"),
            ('ADD', "加选", "把该顶点组的顶点加入当前选择"),
            ('REMOVE', "弃选", "从当前选择里去掉该顶点组的顶点"),
        ],
        default='REPLACE',
    )

    @classmethod
    def poll(cls, context):
        return enabled_object(context) is not None

    def invoke(self, context, event):
        # 列表行按钮（index >= 0）才用修饰键决定方式
        if self.index >= 0 and event is not None:
            if getattr(event, "ctrl", False):
                self.state = 'REMOVE'
            elif getattr(event, "shift", False):
                self.state = 'REPLACE'
            else:
                self.state = 'ADD'
        return self.execute(context)

    def execute(self, context):
        obj = enabled_object(context)
        if obj is None:
            self.report({'WARNING'}, "请在编辑模式或权重绘制（顶点遮罩）下使用")
            return {'CANCELLED'}

        groups = obj.vertex_groups
        index = self.index if self.index >= 0 else groups.active_index
        if not 0 <= index < len(groups):
            self.report({'WARNING'}, "该顶点组已不存在")
            return {'CANCELLED'}

        group = groups[index]
        try:
            apply_state(obj, index, self.state)
        except Exception as error:
            self.report({'ERROR'}, f"选择失败：{error}")
            return {'CANCELLED'}

        action = {'REPLACE': "只选", 'ADD': "加选", 'REMOVE': "弃选"}[self.state]
        count = member_count(obj, index)
        if count < 0:
            self.report({'INFO'}, f"{action}【{group.name}】")
        elif count:
            self.report({'INFO'}, f"{action}【{group.name}】{count} 个顶点")
        else:
            self.report({'INFO'}, f"【{group.name}】里没有已分配的顶点")
        return {'FINISHED'}


class BetterExperie_OT_VGroupQuickAssign(bpy.types.Operator):
    bl_idname = "better_experie.vgroup_quick_assign"
    bl_label = "保存选集到顶点组"
    bl_description = "左键点击：将选中项加入该顶点组（加入）\nShift+左键点击：以选中项作为该顶点组（覆盖）\nCtrl+左键点击：在顶点组中移出选中项（移除）"
    bl_options = {'REGISTER', 'UNDO'}

    index: IntProperty(
        name="顶点组下标",
        description="列表行下标；-1 表示当前活动顶点组",
        default=-1,
    )
    state: EnumProperty(
        name="保存方式",
        items=[
            ('ADD', "加入", "把选中的顶点加入该顶点组"),
            ('REPLACE', "覆盖", "清空该组，只保留选中的顶点"),
            ('REMOVE', "移除", "把选中的顶点移出该顶点组"),
        ],
        default='ADD',
    )

    @classmethod
    def poll(cls, context):
        return enabled_object(context) is not None

    def invoke(self, context, event):
        if self.index >= 0 and event is not None:
            if getattr(event, "ctrl", False):
                self.state = 'REMOVE'
            elif getattr(event, "shift", False):
                self.state = 'REPLACE'
            else:
                self.state = 'ADD'
        return self.execute(context)

    def execute(self, context):
        obj = enabled_object(context)
        if obj is None:
            self.report({'WARNING'}, "请在编辑模式或权重绘制（顶点遮罩）下使用")
            return {'CANCELLED'}

        groups = obj.vertex_groups
        index = self.index if self.index >= 0 else groups.active_index
        if not 0 <= index < len(groups):
            self.report({'WARNING'}, "该顶点组已不存在")
            return {'CANCELLED'}

        group = groups[index]
        try:
            apply_weights(obj, index, self.state)
        except Exception as error:
            self.report({'ERROR'}, f"保存失败：{error}")
            return {'CANCELLED'}

        action = {'ADD': "已加入", 'REPLACE': "已覆盖", 'REMOVE': "已移除"}[self.state]
        count = member_count(obj, index)
        if count < 0:
            self.report({'INFO'}, f"{action}【{group.name}】")
        else:
            self.report({'INFO'}, f"{action}【{group.name}】，当前 {count} 个顶点")
        return {'FINISHED'}


classes = (
    BetterExperie_OT_VGroupQuickSelect,
    BetterExperie_OT_VGroupQuickAssign,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    install_patch()


def unregister():
    remove_patch()
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
