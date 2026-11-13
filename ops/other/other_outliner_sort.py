# 大纲：按名称 / 类型 / 颜色重排所选对象的显示顺序（Blender 5.3+）

import colorsys
import re

import bpy
from bpy.props import BoolProperty, EnumProperty

# 5.3 起 CollectionObject 才有自定义排序索引
SORT_KEYS = [
    ("NAME", "名称", "按名称自然排序（a2 排在 a10 前面）"),
    ("TYPE", "类型", "按物体类型分组"),
    ("COLOR_HV", "颜色（色相→明度）", "先按色相，再按明度"),
    ("COLOR_VH", "颜色（明度→色相）", "先按明度，再按色相"),
]

TYPE_ORDER = [
    "MESH", "CURVE", "SURFACE", "META", "FONT", "ARMATURE", "LATTICE",
    "EMPTY", "LIGHT", "CAMERA", "SPEAKER", "GREASEPENCIL", "GPENCIL",
    "VOLUME", "POINTCLOUD", "CURVES", "HAIR",
]


def has_custom_sort():
    """当前 Blender 是否支持大纲自定义排序"""
    cls = getattr(bpy.types, "CollectionObject", None)
    if cls is None:
        return False
    return "sort_index" in cls.bl_rna.properties


def natural_key(text):
    """自然排序键：a2 排在 a10 前面"""
    parts = re.split(r"(\d+)", text.lower())
    return [int(part) if part.isdigit() else part for part in parts]


def _type_rank(obj):
    try:
        return TYPE_ORDER.index(obj.type)
    except ValueError:
        return len(TYPE_ORDER)


def _color_key_factory(kind):
    cache = {}

    def hsv(obj):
        if obj.name not in cache:
            red, green, blue = obj.color[0], obj.color[1], obj.color[2]
            hue, _saturation, value = colorsys.rgb_to_hsv(red, green, blue)
            cache[obj.name] = (hue, value)
        return cache[obj.name]

    if kind == "COLOR_HV":
        return lambda obj: (hsv(obj)[0], hsv(obj)[1], natural_key(obj.name))
    return lambda obj: (hsv(obj)[1], hsv(obj)[0], natural_key(obj.name))


def sort_key_function(kind):
    if kind == "TYPE":
        return lambda obj: (_type_rank(obj), natural_key(obj.name))
    if kind in ("COLOR_HV", "COLOR_VH"):
        return _color_key_factory(kind)
    return lambda obj: natural_key(obj.name)


def _all_collections(context):
    collections = list(bpy.data.collections)
    scene = getattr(context, "scene", None)
    if scene is not None and scene.collection not in collections:
        collections.append(scene.collection)
    return collections


def _contains_any(collection, objects):
    for obj in objects:
        if collection.objects.get(obj.name) is not None:
            return True
    return False


def resolve_collection(context, objects):
    """优先用当前右键的集合；否则退到包含这些对象最多的集合"""
    if not objects:
        return None
    current = getattr(context, "collection", None)
    if current is not None and _contains_any(current, objects):
        return current

    scores = []
    for collection in _all_collections(context):
        count = sum(1 for obj in objects if collection.objects.get(obj.name) is not None)
        if count:
            scores.append((count, collection))
    if not scores:
        return None
    scores.sort(key=lambda pair: pair[0], reverse=True)
    return scores[0][1]


def _current_order(entries, parented):
    """按大纲当前的显示顺序排列：有索引的升序在前，没有索引的按名称在后面"""
    def key(pair):
        obj, item = pair
        index = item.parented_sort_index if parented else item.sort_index
        return (index < 0, index, natural_key(obj.name))

    return sorted(entries, key=key)


def sort_collection_objects(collection, objects, kind, reverse=False):
    """只在集合内、按父级分组重排所选对象；返回被重排的对象数"""
    pairs = list(zip(collection.objects, collection.collection_objects))
    if len(pairs) < 2:
        return 0

    wanted = {obj.name for obj in objects}
    member_names = {obj.name for obj, _item in pairs}

    groups = {}
    for obj, item in pairs:
        parent = obj.parent
        parented = parent is not None and parent.name in member_names
        groups.setdefault(parent.name if parented else "", []).append((obj, item, parented))

    keyfunc = sort_key_function(kind)
    touched = 0
    for members in groups.values():
        if len(members) < 2:
            continue
        parented = members[0][2]
        entries = [(obj, item) for obj, item, _ in members]
        by_name = {obj.name: (obj, item) for obj, item in entries}

        ordered = _current_order(entries, parented)
        positions = [index for index, (obj, _item) in enumerate(ordered) if obj.name in wanted]
        if len(positions) < 2:
            continue

        chosen = sorted((ordered[index][0] for index in positions),
                        key=keyfunc, reverse=reverse)
        reordered = list(ordered)
        for slot, obj in zip(positions, chosen):
            reordered[slot] = by_name[obj.name]

        attribute = "parented_sort_index" if parented else "sort_index"
        for index, (_obj, item) in enumerate(reordered):
            setattr(item, attribute, index)
        touched += len(positions)
    return touched


def force_custom_sort(context):
    """把大纲切到「自定义排序」，否则索引设置看不到效果"""
    changed = False
    manager = getattr(context, "window_manager", None)
    windows = manager.windows if manager is not None else []
    for window in windows:
        for area in window.screen.areas:
            if area.type != 'OUTLINER':
                continue
            for space in area.spaces:
                if space.type == 'OUTLINER' and space.sort_method != 'CUSTOM':
                    space.sort_method = 'CUSTOM'
                    changed = True
            area.tag_redraw()
    return changed


def draw_outliner_sort(self, context):
    """大纲右键菜单入口"""
    if not has_custom_sort():
        return
    selected = [obj for obj in context.selected_objects if obj is not None]
    if len(selected) < 2:
        return
    layout = self.layout
    layout.separator()
    layout.operator("better_experie.outliner_sort_selected", icon="SORT_ASC")


class BetterExperie_OT_OutlinerSortSelected(bpy.types.Operator):
    bl_idname = "better_experie.outliner_sort_selected"
    bl_label = "重排序所选对象"
    bl_description = "在当前集合内，按指定规则重排所选对象的大纲显示顺序（不改变父子层级）"
    bl_options = {'REGISTER', 'UNDO'}

    sort_key: EnumProperty(name="排序方式", items=SORT_KEYS, default="NAME")
    reverse: BoolProperty(name="倒序", default=False)

    @classmethod
    def poll(cls, context):
        if not has_custom_sort():
            return False
        return len([obj for obj in context.selected_objects if obj is not None]) >= 1

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=340)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "sort_key")
        layout.prop(self, "reverse")
        collection = resolve_collection(context, context.selected_objects)
        selected = len([obj for obj in context.selected_objects if obj is not None])
        if collection is not None:
            layout.label(text=f"目标集合：{collection.name}")
        else:
            layout.label(text="目标集合：未找到", icon="ERROR")
        layout.label(text=f"对象：{selected} 个")

    def execute(self, context):
        if not has_custom_sort():
            self.report({'WARNING'}, "需要 Blender 5.3 或更高版本")
            return {'CANCELLED'}

        objects = [obj for obj in context.selected_objects if obj is not None]
        if len(objects) < 2:
            self.report({'WARNING'}, "至少选择两个对象")
            return {'CANCELLED'}

        collection = resolve_collection(context, objects)
        if collection is None:
            self.report({'WARNING'}, "找不到这些对象所在的集合")
            return {'CANCELLED'}

        touched = sort_collection_objects(collection, objects, self.sort_key, self.reverse)
        if touched == 0:
            self.report({'INFO'}, "所选对象在同一层级内不足两个，未重排")
            return {'CANCELLED'}

        force_custom_sort(context)
        self.report({'INFO'}, f"已重排 {touched} 个对象（{collection.name}）")
        return {'FINISHED'}


classes = (
    BetterExperie_OT_OutlinerSortSelected,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
