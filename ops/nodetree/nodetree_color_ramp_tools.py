# 颜色渐变工具箱

import bpy
import json
import random
import numpy as np

from ...utils.node_tree import get_selected_ramp_nodes

# -----------------------------------------------------------------------------
# 工具函数
# -----------------------------------------------------------------------------

def apply_ramp(ramp, new_ramp):
    if not isinstance(new_ramp, list) or len(new_ramp) == 0:
        return

    cleaned = []
    for item in new_ramp:
        try:
            pos, col = item
            pos = max(0.0, min(1.0, float(pos)))
            r = max(0.0, min(1.0, float(col[0])))
            g = max(0.0, min(1.0, float(col[1])))
            b = max(0.0, min(1.0, float(col[2])))
            a = max(0.0, min(1.0, float(col[3])))
            cleaned.append((pos, (r, g, b, a)))
        except:
            continue
    if len(cleaned) == 0:
        return

    cleaned = cleaned[:32]

    if ramp and hasattr(ramp, "elements"):
        while len(ramp.elements) > 1:
            ramp.elements.remove(ramp.elements[1])

    first_pos, first_col = cleaned[0]
    ramp.elements[0].position = first_pos
    ramp.elements[0].color = first_col
    for pos, col in cleaned[1:]:
        elem = ramp.elements.new(pos)
        elem.color = col


class BetterExperie_OT_ColorRampFlipPositions(bpy.types.Operator):
    bl_idname = "better_experie.color_ramp_flip_positions"
    bl_label = "翻转位置"
    bl_description = "翻转渐变色标的位置顺序"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        for node in get_selected_ramp_nodes(context):
            ramp = node.color_ramp
            data = [(e.position, e.color[:]) for e in ramp.elements]
            new_data = [(1 - p, c) for p, c in reversed(data)]
            apply_ramp(ramp, new_data)
        return {'FINISHED'}


class BetterExperie_OT_ColorRampInvertColors(bpy.types.Operator):
    bl_idname = "better_experie.color_ramp_invert_colors"
    bl_label = "反色颜色"
    bl_description = "反色渐变的所有颜色（RGB取反，透明度不变）"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        for node in get_selected_ramp_nodes(context):
            ramp = node.color_ramp
            data = [(e.position, e.color[:]) for e in ramp.elements]
            new_data = [(p, (1-r, 1-g, 1-b, a)) for p, (r,g,b,a) in data]
            apply_ramp(ramp, new_data)
        return {'FINISHED'}

class BetterExperie_OT_ColorRampDouble(bpy.types.Operator):
    bl_idname = "better_experie.color_ramp_double"
    bl_label = "双色标"
    bl_description = "将渐变复制/镜像为双倍长度"
    bl_options = {'REGISTER', 'UNDO'}

    mirror_ramp: bpy.props.BoolProperty(name="镜像色标", default=False)

    def execute(self, context):
        for node in get_selected_ramp_nodes(context):
            ramp = node.color_ramp
            data = [(e.position, e.color[:]) for e in ramp.elements]
            if len(data) >= 16:
                self.report({'ERROR'}, "色标最大支持32个，当前色标过多")
                return {'FINISHED'}
            new_data = []
            for p, c in data:
                new_data.append((p * 0.499, c))
            if self.mirror_ramp:
                for p, c in data:
                    new_data.append((1 - p * 0.5, c))
            else:
                for p, c in data:
                    new_data.append((0.5 + p * 0.499, c))
            apply_ramp(ramp, new_data)
        return {'FINISHED'}

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)


class BetterExperie_OT_ColorRampEvenDistribution(bpy.types.Operator):
    bl_idname = "better_experie.color_ramp_even_distribution"
    bl_label = "均匀散布"
    bl_description = "将所有色标均匀分布在0~1区间"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        for node in get_selected_ramp_nodes(context):
            ramp = node.color_ramp
            n = len(ramp.elements)
            if n < 2: continue
            new_data = [(i/(n-1), e.color) for i, e in enumerate(ramp.elements)]
            apply_ramp(ramp, new_data)
        return {'FINISHED'}


class BetterExperie_OT_ColorRampNormalizePositions(bpy.types.Operator):
    bl_idname = "better_experie.color_ramp_normalize_positions"
    bl_label = "归一散布"
    bl_description = "将色标位置归一化到0~1区间"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        for node in get_selected_ramp_nodes(context):
            ramp = node.color_ramp
            data = [(e.position, e.color) for e in ramp.elements]
            if len(data) < 2: continue
            min_p = min(p for p,_ in data)
            max_p = max(p for p,_ in data)
            if max_p == min_p: continue
            new_data = [((p-min_p)/(max_p-min_p), c) for p,c in data]
            apply_ramp(ramp, new_data)
        return {'FINISHED'}


class BetterExperie_OT_ColorRampResample(bpy.types.Operator):
    bl_idname = "better_experie.color_ramp_resample"
    bl_label = "色标重采样"
    bl_description = "重采样色标到指定数量（保留Blender原生颜色）"
    bl_options = {'REGISTER', 'UNDO'}

    count: bpy.props.IntProperty(name="目标数量", default=5, min=1, max=32)

    def execute(self, context):
        for node in get_selected_ramp_nodes(context):
            ramp = node.color_ramp
            if self.count == 1:
                col = ramp.evaluate(0.5)
                new_data = [(0.5, col)]
            else:
                positions = np.linspace(0.0, 1.0, self.count, dtype=np.float32)
                new_data = []
                for pos in positions:
                    color = ramp.evaluate(float(pos))
                    new_data.append((float(pos), color))
            apply_ramp(ramp, new_data)
        return {'FINISHED'}

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)


# RDP 道格拉斯普克算法（纯numpy）
def rdp_simplify_curve(data, target_points=8):
    indices = [0, len(data)-1]
    points = data.copy()
    def distance(p, a, b):
        dx = b[0] - a[0]
        dy = b[1:] - a[1:]
        dpx = p[0] - a[0]
        dpy = p[1:] - a[1:]
        if dx < 1e-8:
            return np.sum(np.abs(dpy))
        t = dpx / dx
        proj = a + t * np.concatenate([[dx], dy])
        return np.sqrt(np.sum((p - proj)**2))

    while len(indices) < target_points and len(indices) < len(points):
        max_dist = -1
        best_idx = -1
        for i in range(len(indices)-1):
            start = indices[i]
            end = indices[i+1]
            if end - start <= 1:
                continue
            segment = points[start:end+1]
            a = points[start]
            b = points[end]
            for j in range(1, len(segment)-1):
                p = segment[j]
                d = distance(p, a, b)
                if d > max_dist:
                    max_dist = d
                    best_idx = start + j
        if best_idx == -1:
            break
        indices.append(best_idx)
        indices = sorted(indices)
    return points[indices]


class BetterExperie_OT_ColorRampClean(bpy.types.Operator):
    bl_idname = "better_experie.color_ramp_clean"
    bl_label = "清理/精简色标"
    bl_description = "使用RDP算法精简、按最小间距合并或按范围删除色标"
    bl_options = {'REGISTER', 'UNDO'}

    mode: bpy.props.EnumProperty(
        name="处理模式",
        items=[
            ('RDP', "RDP 视觉精简", "保留视觉关键色标，删除冗余点"),
            ('DISTANCE', "最小间距合并", "合并距离过近的色标"),
            ('DELETE_RANGE', "范围删除", "删除两个端点之间的所有色标")
        ],
        default='RDP'
    )

    target_count: bpy.props.IntProperty(name="目标数量", default=8, min=2, max=32)
    distance: bpy.props.FloatProperty(name="最小间距", default=0.02, min=0, max=0.5, subtype="FACTOR")
    range_a: bpy.props.FloatProperty(name="范围端点 A", default=0.25, min=0, max=1, subtype="FACTOR")
    range_b: bpy.props.FloatProperty(name="范围端点 B", default=0.75, min=0, max=1, subtype="FACTOR")

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "mode", expand=True)
        if self.mode == 'RDP':
            layout.prop(self, "target_count")
        elif self.mode == 'DISTANCE':
            layout.prop(self, "distance")
        elif self.mode == 'DELETE_RANGE':
            layout.prop(self, "range_a")
            layout.prop(self, "range_b")

    def execute(self, context):
        for node in get_selected_ramp_nodes(context):
            ramp = node.color_ramp
            if self.mode == 'RDP':
                self.execute_rdp(ramp)
            elif self.mode == 'DISTANCE':
                self.execute_distance(ramp)
            elif self.mode == 'DELETE_RANGE':
                self.execute_delete_range(ramp)
        return {'FINISHED'}

    def execute_rdp(self, ramp):
        points = [(e.position, e.color) for e in ramp.elements]
        n = len(points)
        if self.target_count >= n or n <= 2:
            return
        data = []
        for pos, col in points:
            data.append([pos, *col])
        data = np.array(data, dtype=np.float32)
        data = data[np.argsort(data[:, 0])]
        simplified = rdp_simplify_curve(data, target_points=self.target_count)
        new_data = []
        for row in simplified:
            pos = float(row[0])
            col = (float(row[1]), float(row[2]), float(row[3]), float(row[4]))
            new_data.append((pos, col))
        apply_ramp(ramp, new_data)

    def execute_distance(self, ramp):
        data = sorted([(e.position, e.color) for e in ramp.elements], key=lambda x:x[0])
        if not data: return
        result = []
        group = [data[0]]
        for p, c in data[1:]:
            if abs(p - group[-1][0]) < self.distance:
                group.append((p, c))
            else:
                result.append(self.merge_group(group))
                group = [(p, c)]
        result.append(self.merge_group(group))
        apply_ramp(ramp, result)

    def execute_delete_range(self, ramp):
        data = [(e.position, e.color) for e in ramp.elements]
        new_data = []
        min_f = min(self.range_a, self.range_b)
        max_f = max(self.range_a, self.range_b)
        for p, c in data:
            if p < min_f or p > max_f:
                new_data.append((p, c))
        if not new_data:
            new_data.append(data[0])
        apply_ramp(ramp, new_data)

    def merge_group(self, group):
        n = len(group)
        avg_p = sum(p for p, _ in group) / n
        r = sum(c[0] for _, c in group) / n
        g = sum(c[1] for _, c in group) / n
        b = sum(c[2] for _, c in group) / n
        a = sum(c[3] for _, c in group) / n
        return avg_p, (r, g, b, a)

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)


class BetterExperie_OT_ColorRampSmoothContrast(bpy.types.Operator):
    bl_idname = "better_experie.color_ramp_smooth_contrast"
    bl_label = "渐变平滑/对比"
    bl_description = "平滑或增强渐变颜色/位置差异"
    bl_options = {'REGISTER', 'UNDO'}

    factor: bpy.props.FloatProperty(name="系数", default=0.01, min=-1, max=1)
    iterations: bpy.props.IntProperty(name="迭代次数", default=30, min=1, max=50)
    mode: bpy.props.EnumProperty(name="模式", items=[("COLOR","颜色",""),("POSITION","位置","")], default="COLOR")

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "mode", expand=True)
        layout.prop(self, "factor")
        layout.prop(self, "iterations")

    def execute(self, context):
        for node in get_selected_ramp_nodes(context):
            ramp = node.color_ramp
            data = [(e.position, e.color) for e in ramp.elements]
            if len(data) < 3:
                apply_ramp(ramp, data)
                continue
            arr = np.array([p for p,_ in data], dtype=np.float32)
            cols = np.array([c for _,c in data], dtype=np.float32)
            for _ in range(self.iterations):
                if self.mode == "COLOR":
                    avg = (cols[:-2] + cols[2:]) * 0.5
                    cur = cols[1:-1]
                    f = self.factor
                    if f >= 0:
                        cols[1:-1] = (1-f)*cur + f*avg
                    else:
                        f = -f
                        cols[1:-1] = cur + (cur - avg)*f
                    cols = np.clip(cols, 0, 1)
                else:
                    avg = (arr[:-2] + arr[2:]) * 0.5
                    cur = arr[1:-1]
                    f = self.factor
                    if f >=0:
                        arr[1:-1] = (1-f)*cur + f*avg
                    else:
                        f = -f
                        arr[1:-1] = cur + (cur - avg)*f
                    arr = np.clip(arr, 0, 1)
            data = list(zip(arr.tolist(), cols.tolist()))
            apply_ramp(ramp, data)
        return {'FINISHED'}

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)


class BetterExperie_OT_ColorRampRandomize(bpy.types.Operator):
    bl_idname = "better_experie.color_ramp_randomize"
    bl_label = "随机渐变"
    bl_description = "随机扰动渐变的位置或颜色"
    bl_options = {'REGISTER', 'UNDO'}

    mode: bpy.props.EnumProperty(name="模式", items=[("POS","随机位置",""),("COL","随机颜色","")])
    strength: bpy.props.FloatProperty(name="强度", default=0.2, min=0, max=1)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "mode", expand=True)
        layout.prop(self, "strength")

    def execute(self, context):
        for node in get_selected_ramp_nodes(context):
            ramp = node.color_ramp
            data = [(e.position, e.color) for e in ramp.elements]
            new_data = []
            for p,c in data:
                if self.mode == "POS":
                    np_val = (p + random.uniform(-self.strength, self.strength)) % 1.0
                    new_data.append((np_val, c))
                else:
                    r = c[0] + random.uniform(-self.strength, self.strength)
                    g = c[1] + random.uniform(-self.strength, self.strength)
                    b = c[2] + random.uniform(-self.strength, self.strength)
                    new_data.append((p, (r,g,b,c[3])))
            apply_ramp(ramp, new_data)
        return {'FINISHED'}

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)


def srgb_to_linear_np(c):
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)

def linear_to_srgb_np(c):
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * (c ** (1.0 / 2.4)) - 0.055)

def mix_colors(color1, color2, factor=0.5, gamma=False):
    if not isinstance(color1, np.ndarray):
        color1 = np.asarray(color1, dtype=np.float32)
    if not isinstance(color2, np.ndarray):
        color2 = np.asarray(color2, dtype=np.float32)
    if gamma:
        color1 = linear_to_srgb_np(color1)
        color2 = linear_to_srgb_np(color2)
    result = color1 * (1 - factor) + color2 * factor
    if gamma:
        result = srgb_to_linear_np(result)
    if result.shape == (3,):
        return tuple(result)
    return result


class BetterExperie_OT_ColorRampColorMix(bpy.types.Operator):
    bl_idname = "better_experie.color_ramp_color_mix"
    bl_label = "染色"
    bl_description = "按系数将目标颜色线性混合到渐变所有色标"
    bl_options = {'REGISTER', 'UNDO'}

    mix_color: bpy.props.FloatVectorProperty(name="染色颜色", subtype='COLOR', size=4, default=(1.0, 0.2, 0.2, 1.0), min=0, max=1)
    mix_factor: bpy.props.FloatProperty(name="染色系数", default=0.5, min=0, max=1)
    use_gamma: bpy.props.BoolProperty(name="伽马空间混合", default=False)

    def execute(self, context):
        for node in get_selected_ramp_nodes(context):
            ramp = node.color_ramp
            data = []
            for elem in ramp.elements:
                pos = elem.position
                src_color = elem.color
                new_color = mix_colors(
                    color1=src_color,
                    color2=self.mix_color,
                    factor=self.mix_factor,
                    gamma=self.use_gamma
                )
                data.append((pos, new_color))
            apply_ramp(ramp, data)
        return {'FINISHED'}

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=300)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "mix_color")
        layout.prop(self, "mix_factor")
        layout.prop(self, "use_gamma")


class BetterExperie_OT_ColorRampCopy(bpy.types.Operator):
    bl_idname = "better_experie.color_ramp_copy"
    bl_label = "复制渐变"
    bl_description = "复制选中节点的渐变数据到剪贴板"

    @classmethod
    def poll(cls, context):
        return len(get_selected_ramp_nodes(context)) > 0

    def execute(self, context):
        node = get_selected_ramp_nodes(context)[0]
        ramp = node.color_ramp

        data = {
            "type": "COLOR_RAMP",
            "color_mode": ramp.color_mode,
            "interpolation": ramp.interpolation,
            "elements": [
                {"position": e.position, "color": list(e.color)}
                for e in ramp.elements
            ],
        }
        context.window_manager.clipboard = json.dumps(data)
        self.report({'INFO'}, f"已复制 {len(ramp.elements)} 个色标")
        return {'FINISHED'}


class BetterExperie_OT_ColorRampPaste(bpy.types.Operator):
    bl_idname = "better_experie.color_ramp_paste"
    bl_label = "粘贴渐变"
    bl_description = "将剪贴板的渐变数据粘贴到所有选中节点"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return len(get_selected_ramp_nodes(context)) > 0 and bool(context.window_manager.clipboard)

    def execute(self, context):
        try:
            data = json.loads(context.window_manager.clipboard)
            if data.get("type") != "COLOR_RAMP":
                raise ValueError
        except:
            self.report({'ERROR'}, "剪贴板中没有有效的渐变数据")
            return {'CANCELLED'}

        elements = data.get("elements", [])
        color_mode = data.get("color_mode", "RGB")
        interpolation = data.get("interpolation", "LINEAR")

        nodes = get_selected_ramp_nodes(context)
        for node in nodes:
            ramp = node.color_ramp
            ramp.color_mode = color_mode
            ramp.interpolation = interpolation

            new_data = [(e["position"], tuple(e["color"])) for e in elements]
            apply_ramp(ramp, new_data)

        self.report({'INFO'}, f"已粘贴到 {len(nodes)} 个节点")

        return {'FINISHED'}


classes = (
    BetterExperie_OT_ColorRampCopy,
    BetterExperie_OT_ColorRampPaste,
    BetterExperie_OT_ColorRampFlipPositions,
    BetterExperie_OT_ColorRampInvertColors,
    BetterExperie_OT_ColorRampDouble,
    BetterExperie_OT_ColorRampEvenDistribution,
    BetterExperie_OT_ColorRampResample,
    BetterExperie_OT_ColorRampNormalizePositions,
    BetterExperie_OT_ColorRampSmoothContrast,
    BetterExperie_OT_ColorRampRandomize,
    BetterExperie_OT_ColorRampColorMix,
    BetterExperie_OT_ColorRampClean,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
