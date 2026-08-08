# 颜色渐变预设库

import bpy
import os
import json
import shutil
import datetime
import numpy as np
from mathutils import Vector
from bpy.props import StringProperty
from bpy_extras.io_utils import ExportHelper, ImportHelper

from ...utils.node_tree import stick_selected_node_to_cursor

# 路径计算：ops/nodetree/ → ops/ → addon root → data/
ADDON_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
DATA_DIR = os.path.join(ADDON_ROOT, "data")
os.makedirs(DATA_DIR, exist_ok=True)
_LIB_PATH = os.path.join(DATA_DIR, "ramp_lib.blend")

_LIB_NODE_GROUP_NAME = "RampPresetsLibrary"


# ═══════════════════════════════════════════════════════════
# DATA LAYER
# ═══════════════════════════════════════════════════════════

from dataclasses import dataclass

@dataclass
class RampPreset:
    preset_id: str
    name: str
    stops: list
    interpolation: str = "LINEAR"
    avg_color: tuple = (0.5, 0.5, 0.5)
    history: bool = False
    history_time: str = ""


_user_presets: dict[str, RampPreset] = {}


def _calculate_avg_color(stops):
    if not stops:
        return (0.5, 0.5, 0.5)
    arr = np.array([col[:3] for _, col in stops], dtype=np.float32)
    return tuple(np.mean(arr, axis=0))


def _load_user_presets():
    old_history = {pid: p for pid, p in _user_presets.items() if p.history}
    _user_presets.clear()

    if not os.path.isfile(_LIB_PATH):
        return

    try:
        with bpy.data.libraries.load(_LIB_PATH, link=False) as (data_from, data_to):
            if _LIB_NODE_GROUP_NAME in data_from.node_groups:
                data_to.node_groups = [_LIB_NODE_GROUP_NAME]

        for ng in data_to.node_groups:
            if ng is None:
                continue
            for node in ng.nodes:
                if node.type == 'VALTORGB':
                    preset_name = node.label if node.label else node.name
                    cr = node.color_ramp
                    stops = [(elem.position, tuple(elem.color)) for elem in cr.elements]
                    preset = RampPreset(
                        preset_id=node.name,
                        name=preset_name,
                        stops=stops,
                        interpolation=cr.interpolation,
                        avg_color=_calculate_avg_color(stops))
                    if preset.preset_id in old_history:
                        preset.history = True
                        preset.history_time = old_history[preset.preset_id].history_time
                    _user_presets[preset.preset_id] = preset
            bpy.data.node_groups.remove(ng)
    except Exception as e:
        print(f"加载渐变库失败: {e}")


def _modify_lib_blend(action_func, *args, **kwargs):
    temp_ng = None

    if os.path.isfile(_LIB_PATH):
        try:
            with bpy.data.libraries.load(_LIB_PATH, link=False) as (data_from, data_to):
                if _LIB_NODE_GROUP_NAME in data_from.node_groups:
                    data_to.node_groups = [_LIB_NODE_GROUP_NAME]
            if data_to.node_groups and data_to.node_groups[0]:
                temp_ng = data_to.node_groups[0]
        except Exception:
            pass

    if not temp_ng:
        temp_ng = bpy.data.node_groups.new(_LIB_NODE_GROUP_NAME, 'ShaderNodeTree')

    try:
        result = action_func(temp_ng, *args, **kwargs)
        bpy.data.libraries.write(_LIB_PATH, {temp_ng}, fake_user=True)
    finally:
        if temp_ng in bpy.data.node_groups.values():
            bpy.data.node_groups.remove(temp_ng)

    _load_user_presets()
    return result


def _action_save_preset(ng, preset_id, name, stops, interpolation):
    if preset_id in ng.nodes:
        node = ng.nodes[preset_id]
    else:
        node_count = len(ng.nodes)
        node = ng.nodes.new('ShaderNodeValToRGB')
        node.name = preset_id
        col = node_count % 10
        row = node_count // 10
        node.location = (col * 300, -row * 300)

    node.label = name

    cr = node.color_ramp
    sorted_stops = sorted(stops, key=lambda s: s[0])
    while len(cr.elements) > 2:
        cr.elements.remove(cr.elements[-1])

    cr.elements[0].position = sorted_stops[0][0]
    cr.elements[0].color = sorted_stops[0][1]
    cr.elements[1].position = sorted_stops[-1][0]
    cr.elements[1].color = sorted_stops[-1][1]

    for pos, col in sorted_stops[1:-1]:
        elem = cr.elements.new(pos)
        elem.color = col

    cr.interpolation = interpolation
    return node.name


def _action_delete_preset(ng, preset_id):
    if preset_id in ng.nodes:
        ng.nodes.remove(ng.nodes[preset_id])
        return True
    return False


def get_preset(preset_id: str) -> RampPreset | None:
    return _user_presets.get(preset_id)


def save_user_preset(preset_id: str, name: str, stops, interpolation: str = "LINEAR") -> str:
    if not preset_id:
        preset_id = "preset_" + os.urandom(4).hex()
    return _modify_lib_blend(_action_save_preset, preset_id, name, stops, interpolation)


def remove_user_preset(preset_id: str) -> bool:
    return _modify_lib_blend(_action_delete_preset, preset_id)


# ═══════════════════════════════════════════════════════════
# PREVIEW GENERATION
# ═══════════════════════════════════════════════════════════

_preview_collections = {}


def _sample_gradient(stops, t):
    sorted_stops = sorted(stops, key=lambda s: s[0])
    t = max(0.0, min(1.0, t))
    if t <= sorted_stops[0][0]:
        return sorted_stops[0][1]
    if t >= sorted_stops[-1][0]:
        return sorted_stops[-1][1]
    for i in range(len(sorted_stops) - 1):
        a_pos, a_col = sorted_stops[i]
        b_pos, b_col = sorted_stops[i + 1]
        if a_pos <= t < b_pos:
            local_t = (t - a_pos) / (b_pos - a_pos)
            return tuple(a + (b - a) * local_t for a, b in zip(a_col, b_col))
    return sorted_stops[-1][1]


def _generate_preview(pcoll, preset_id, stops, img_w=64, img_h=8, ico_w=32, ico_h=32):
    if preset_id in pcoll:
        return
    preview = pcoll.new(preset_id)
    preview.image_size = (img_w, img_h)
    flat = []
    for x in range(img_w):
        flat.extend(_sample_gradient(stops, x / (img_w - 1) if img_w > 1 else 0.0))
    preview.image_pixels_float[:] = flat * img_h
    preview.icon_size = (ico_w, ico_h)
    flat = []
    for x in range(ico_w):
        flat.extend(_sample_gradient(stops, x / (ico_w - 1) if ico_w > 1 else 0.0))
    preview.icon_pixels_float[:] = flat * ico_h


def _init_previews():
    if "ramp_lib" in _preview_collections:
        return _preview_collections["ramp_lib"]
    pcoll = bpy.utils.previews.new()
    for preset in _user_presets.values():
        _generate_preview(pcoll, preset.preset_id, preset.stops)
    _preview_collections["ramp_lib"] = pcoll
    return pcoll


def _refresh_previews():
    _free_previews()
    _init_previews()


def _free_previews():
    for pcoll in _preview_collections.values():
        bpy.utils.previews.remove(pcoll)
    _preview_collections.clear()


# ═══════════════════════════════════════════════════════════
# OPERATORS
# ═══════════════════════════════════════════════════════════

class BetterExperie_OT_RampLibApply(bpy.types.Operator):
    bl_idname = "better_experie.ramp_lib_apply"
    bl_label = "应用渐变预设"
    bl_description = "用此预设替换当前颜色渐变"
    bl_options = {'REGISTER', 'UNDO'}

    preset_id: bpy.props.StringProperty()
    node_name: bpy.props.StringProperty(options={"HIDDEN"})

    def invoke(self, context, event):
        ui_scale = context.preferences.system.ui_scale
        x, y = context.region.view2d.region_to_view(event.mouse_region_x, event.mouse_region_y)
        self.invoke_location = Vector((x / ui_scale, y / ui_scale))
        return self.execute(context)

    def execute(self, context):
        preset = get_preset(self.preset_id)
        if preset is None:
            self.report({'ERROR'}, f"未找到预设：{self.preset_id}")
            return {'CANCELLED'}

        preset.history = True
        preset.history_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        node = context.space_data.edit_tree.nodes.get(self.node_name) if self.node_name else context.active_node

        is_new_node = False
        if node is None or node.type != "VALTORGB":
            bpy.ops.node.select(deselect_all=True)
            tree_type = context.space_data.tree_type
            if tree_type == 'CompositorNodeTree':
                node_idname = 'CompositorNodeValToRGB'
            elif tree_type == 'TextureNodeTree':
                node_idname = 'TextureNodeValToRGB'
            else:
                node_idname = 'ShaderNodeValToRGB'
            node = context.space_data.edit_tree.nodes.new(type=node_idname)
            node.location = (0, 0)
            node.label = preset.name
            is_new_node = True

        node.label = preset.name

        cr = node.color_ramp
        sorted_stops = sorted(preset.stops, key=lambda s: s[0])

        while len(cr.elements) > 2:
            cr.elements.remove(cr.elements[-1])

        cr.elements[0].position = sorted_stops[0][0]
        cr.elements[0].color = sorted_stops[0][1]
        cr.elements[1].position = sorted_stops[-1][0]
        cr.elements[1].color = sorted_stops[-1][1]

        for pos, col in sorted_stops[1:-1]:
            elem = cr.elements.new(pos)
            elem.color = col

        cr.interpolation = preset.interpolation

        if is_new_node:
            stick_selected_node_to_cursor(getattr(self, "invoke_location", None))

        return {'FINISHED'}


class BetterExperie_OT_RampLibSave(bpy.types.Operator):
    bl_idname = "better_experie.ramp_lib_save"
    bl_label = "保存渐变预设"
    bl_description = "将当前颜色渐变保存为可复用的预设"
    bl_options = {'REGISTER', 'INTERNAL'}

    node_name: bpy.props.StringProperty(options={"HIDDEN"})
    preset_name: bpy.props.StringProperty(name="名称", default="我的渐变")
    preset_id: bpy.props.StringProperty(options={"HIDDEN"}, default="")

    def invoke(self, context, event):
        node = context.space_data.edit_tree.nodes.get(self.node_name) if self.node_name else context.active_node
        if node and node.label:
            self.preset_name = node.label
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        self.layout.prop(self, "preset_name")

    def execute(self, context):
        node = context.space_data.edit_tree.nodes.get(self.node_name) if self.node_name else context.active_node
        if node is None or node.type != "VALTORGB":
            self.report({'ERROR'}, "未选择有效的颜色渐变节点")
            return {'CANCELLED'}

        cr = node.color_ramp
        stops = [(elem.position, tuple(elem.color)) for elem in cr.elements]
        interpolation = cr.interpolation

        save_user_preset(self.preset_id, self.preset_name, stops, interpolation)
        _refresh_previews()

        self.report({'INFO'}, f"已保存：{self.preset_name}")
        return {'FINISHED'}


class BetterExperie_OT_RampLibRename(bpy.types.Operator):
    bl_idname = "better_experie.ramp_lib_rename"
    bl_label = "重命名预设"
    bl_description = "重命名此用户预设"
    bl_options = {'REGISTER', 'INTERNAL'}

    preset_id: bpy.props.StringProperty()
    new_name: bpy.props.StringProperty(name="名称", default="")

    def invoke(self, context, event):
        preset = get_preset(self.preset_id)
        if preset is not None:
            self.new_name = preset.name
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        self.layout.prop(self, "new_name")

    def execute(self, context):
        if not self.new_name.strip():
            self.report({'WARNING'}, "名称不能为空")
            return {'CANCELLED'}
        preset = get_preset(self.preset_id)
        if preset:
            save_user_preset(self.preset_id, self.new_name, preset.stops, preset.interpolation)
            _refresh_previews()
            self.report({'INFO'}, f"已重命名为：{self.new_name}")
        else:
            self.report({'WARNING'}, "未找到预设")
        return {'FINISHED'}


class BetterExperie_OT_RampLibDelete(bpy.types.Operator):
    bl_idname = "better_experie.ramp_lib_delete"
    bl_label = "删除预设"
    bl_description = "永久删除此用户预设"
    bl_options = {'REGISTER', 'INTERNAL'}

    preset_id: bpy.props.StringProperty()

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        if remove_user_preset(self.preset_id):
            _refresh_previews()
            self.report({'INFO'}, "已删除")
        else:
            self.report({'WARNING'}, "未找到预设")
        return {'FINISHED'}


class BetterExperie_OT_RampLibExport(bpy.types.Operator, ExportHelper):
    bl_idname = "better_experie.ramp_lib_export"
    bl_label = "导出渐变库"
    bl_description = "将当前所有预设导出为 .blend 文件"

    filename_ext = ".blend"
    filter_glob: bpy.props.StringProperty(default="*.blend", options={'HIDDEN'})

    def execute(self, context):
        if not os.path.isfile(_LIB_PATH):
            self.report({'WARNING'}, "当前没有可导出的预设")
            return {'CANCELLED'}
        try:
            shutil.copy2(_LIB_PATH, self.filepath)
            self.report({'INFO'}, f"成功导出至: {self.filepath}")
        except Exception as e:
            self.report({'ERROR'}, f"导出失败: {e}")
            return {'CANCELLED'}
        return {'FINISHED'}


class BetterExperie_OT_RampLibImport(bpy.types.Operator, ImportHelper):
    bl_idname = "better_experie.ramp_lib_import"
    bl_label = "导入渐变库"
    bl_description = "从 .blend 文件中导入渐变预设"

    filename_ext = ".blend"
    filter_glob: bpy.props.StringProperty(default="*.blend", options={'HIDDEN'})

    def execute(self, context):
        if not os.path.isfile(self.filepath):
            return {'CANCELLED'}
        imported_count = 0
        try:
            with bpy.data.libraries.load(self.filepath, link=False) as (data_from, data_to):
                if _LIB_NODE_GROUP_NAME in data_from.node_groups:
                    data_to.node_groups = [_LIB_NODE_GROUP_NAME]
            for ng in data_to.node_groups:
                if ng is None:
                    continue
                for node in ng.nodes:
                    if node.type == 'VALTORGB':
                        preset_name = node.label if node.label else node.name
                        cr = node.color_ramp
                        stops = [(elem.position, tuple(elem.color)) for elem in cr.elements]
                        new_id = "preset_" + os.urandom(4).hex()
                        save_user_preset(new_id, preset_name, stops, cr.interpolation)
                        imported_count += 1
                bpy.data.node_groups.remove(ng)
            if imported_count > 0:
                _refresh_previews()
                self.report({'INFO'}, f"成功导入 {imported_count} 个预设")
            else:
                self.report({'WARNING'}, "未在文件中找到有效的渐变预设")
        except Exception as e:
            self.report({'ERROR'}, f"导入失败: {e}")
            return {'CANCELLED'}
        return {'FINISHED'}


class BetterExperie_OT_RampLibPopup(bpy.types.Operator):
    bl_idname = "better_experie.ramp_lib_popup"
    bl_label = "渐变库"
    bl_description = "浏览并应用颜色渐变预设"
    bl_options = {'INTERNAL'}

    node_name: bpy.props.StringProperty(options={"HIDDEN"})
    show_ramp_setting: bpy.props.BoolProperty(name="详细设置", description="启用后展开列表详细设置", default=False)

    search_mode: bpy.props.EnumProperty(
        name="筛查模式",
        items=[('NAME', '名称', '按名称筛查'), ('COLOR', '颜色', '按颜色相似度排序'), ('HISTORY', '历史', '仅显示历史项')],
        default='NAME')
    search_name: bpy.props.StringProperty(name="筛查", description="输入名称关键字进行筛查", default="")
    search_color: bpy.props.FloatVectorProperty(name="目标色", subtype='COLOR', size=3, default=(0.5, 0.5, 0.5), min=0.0, max=1.0, description="筛查目标颜色")
    icon_columns: bpy.props.IntProperty(name="每行列数", description="设置每行显示的图标数量", default=5, min=1, max=5)

    def invoke(self, context, event):
        _load_user_presets()
        _refresh_previews()
        context.window_manager.invoke_popup(self, width=450)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        return {'FINISHED'}

    def draw(self, context):
        layout = self.layout
        pcoll = _preview_collections.get("ramp_lib")

        layout.label(text="渐变库", icon="COLOR")
        layout.separator(type="LINE")

        row = layout.row(align=True)
        row.prop(self, "icon_columns", text="每行数量")
        row.prop(self, "show_ramp_setting", text="", icon="PREFERENCES")

        row = layout.row(align=True)
        row.prop(self, "search_mode", expand=True)
        if self.search_mode == 'NAME':
            row.separator()
            row.prop(self, "search_name", text="")
        elif self.search_mode == 'COLOR':
            row.separator()
            row.prop(self, "search_color", text="")
        elif self.search_mode == 'HISTORY':
            row.label(text=" ")

        layout.separator()

        items = list(_user_presets.values())
        if self.search_mode == 'NAME':
            filter_text = self.search_name.strip().lower()
            show_items = [item for item in items if filter_text in item.name.lower()] if filter_text else items
        elif self.search_mode == 'COLOR':
            target = np.array(self.search_color)
            show_items = sorted(items, key=lambda item: np.linalg.norm(np.array(item.avg_color) - target))
        elif self.search_mode == 'HISTORY':
            show_items = [item for item in items if item.history]
            show_items = sorted(show_items, key=lambda x: x.history_time if x.history_time else "0000-00-00 00:00:00", reverse=True)
        else:
            show_items = items

        if not show_items:
            if self.search_mode == 'HISTORY':
                layout.label(text="未找到历史记录")
            else:
                layout.label(text="未找到渐变预设")
            layout.separator(type="LINE")
            op = layout.operator(BetterExperie_OT_RampLibSave.bl_idname, text="保存当前渐变", icon="ADD")
            op.node_name = self.node_name
            return

        box = layout.box()
        columns = self.icon_columns

        for i in range(0, len(show_items), columns):
            row = box.row(align=True)
            for j in range(columns):
                idx = i + j
                if idx < len(show_items):
                    item = show_items[idx]
                    icon_id = pcoll[item.preset_id].icon_id if pcoll and item.preset_id in pcoll else 0

                    op = row.operator(BetterExperie_OT_RampLibApply.bl_idname, text=item.name, icon_value=icon_id)
                    op.preset_id = item.preset_id
                    op.node_name = self.node_name

                    if self.show_ramp_setting:
                        op_ren = row.operator(BetterExperie_OT_RampLibRename.bl_idname, text="", icon="GREASEPENCIL")
                        op_ren.preset_id = item.preset_id
                        op_del = row.operator(BetterExperie_OT_RampLibDelete.bl_idname, text="", icon="X")
                        op_del.preset_id = item.preset_id
                else:
                    row.label(text="")
                    if self.show_ramp_setting:
                        row.label(text="", icon="BLANK1")
                        row.label(text="", icon="BLANK1")

        op = layout.operator(BetterExperie_OT_RampLibSave.bl_idname, text="保存当前渐变", icon="ADD")
        op.node_name = self.node_name

        if self.show_ramp_setting:
            row = layout.row(align=True)
            row.operator(BetterExperie_OT_RampLibImport.bl_idname, text="导入", icon="IMPORT")
            row.operator(BetterExperie_OT_RampLibExport.bl_idname, text="导出", icon="EXPORT")


classes = (
    BetterExperie_OT_RampLibApply,
    BetterExperie_OT_RampLibSave,
    BetterExperie_OT_RampLibRename,
    BetterExperie_OT_RampLibDelete,
    BetterExperie_OT_RampLibPopup,
    BetterExperie_OT_RampLibExport,
    BetterExperie_OT_RampLibImport,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    _free_previews()
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
