
#要改什么片段，请给我要修改的片段，注意使用标准4空格缩进

#我想要曲线资产库的预览图系统，以及它的保存用户预设系统
bl_info = {
    "name": "[TEST]Float Curve Math Presets Pro Max",
    "author": "RARA",
    "version": (2, 1, 0),
    "blender": (4, 0, 0),
    "location": "Node Editor > Sidebar > 测试",
    "description": "高级浮点与RGB曲线效率工具箱",
    "category": "Node",
}

import bpy
import math
import json
import random

from ...utils.node_tree import get_selected_curve_nodes

def get_target_curve(node, channel_idx):
    mapping = node.mapping
    curve_index = int(channel_idx) if len(mapping.curves) == 4 else 0
    return mapping.curves[curve_index]

def set_curve_points(curve, x_vals, y_vals, handle_types=None):
    while len(curve.points) > 2:
        curve.points.remove(curve.points[-1])

    if len(curve.points) < 2:
        curve.points.new(0, 0)
        curve.points.new(1, 1)

    if len(x_vals) == 1:
        curve.points[0].location = (x_vals[0], y_vals[0])
        curve.points[1].location = (x_vals[0], y_vals[0])
    else:
        curve.points[0].location = (x_vals[0], y_vals[0])
        curve.points[1].location = (x_vals[-1], y_vals[-1])
        for i in range(1, len(x_vals) - 1):
            curve.points.new(x_vals[i], y_vals[i])

    for i, p in enumerate(curve.points):
        if handle_types and i < len(handle_types):
            p.handle_type = handle_types[i]
        else:
            p.handle_type = 'AUTO'

class BetterExperie_OT_ApplyCurvePreset(bpy.types.Operator):
    bl_idname = "better_experie.apply_curve_preset"
    bl_label = "设置预设"
    bl_description = "使用内置数学预设或自定义公式批量设置曲线控制点"
    bl_options = {'REGISTER', 'UNDO'}

    preset_type: bpy.props.EnumProperty(
        name="预设类型",
        description="选择要应用的曲线预设",
        items=[
            ('LINEAR', "线性", "", "IPO_LINEAR",0),
            ('SQUARE', "平方", "", "IPO_QUAD",1),
            ('CUBE', "立方", "", "IPO_CUBIC",2),
            ('SINE', "正弦", "", "FORCE_HARMONIC",3),
            ('COSINE', "余弦", "", "SMOOTHCURVE",4),
            None,
            ('QUAD_IN', "二次缓入", "", "IPO_CIRC",6),
            ('QUAD_OUT', "二次缓出", "", "IPO_CIRC",7),
            ('QUAD_INOUT', "二次缓入缓出", "", "IPO_CIRC",8),
            None,
            ('EXPO_IN', "指数缓入", "", "IPO_EXPO",10),
            ('EXPO_OUT', "指数缓出", "", "IPO_EXPO",11),
            ('EXPO_INOUT', "指数缓入缓出", "", "IPO_EXPO",12),
            None,
            ('BOUNCE_IN', "回弹缓入", "", "IPO_BOUNCE",14),
            ('BOUNCE_OUT', "回弹缓出", "", "IPO_BOUNCE",15),
            ('BOUNCE_INOUT', "回弹缓入缓出", "", "IPO_BOUNCE",16),
            None,
            ('CUSTOM', "自定义公式", "", "USER",18)
        ],default='LINEAR')

    # 自定义公式属性
    expression: bpy.props.StringProperty(
        name="y = f(x) =", default="sin(x*pi)",
        description="输入数学表达式，例如 sin(x*pi), x**2, 1-x 等")

    clamp_result: bpy.props.BoolProperty(
        name="限制在 0-1 之间", default=True,
        description="是否将计算结果强制钳制在 0 到 1 之间")

    points_count: bpy.props.IntProperty(
        name="点数量",default=15,min=2,max=50,
        description="生成曲线的控制点数量")

    # 通道控制布尔值
    apply_c: bpy.props.BoolProperty(name="C (综合)", default=True)
    apply_r: bpy.props.BoolProperty(name="R (红色)", default=True)
    apply_g: bpy.props.BoolProperty(name="G (绿色)", default=True)
    apply_b: bpy.props.BoolProperty(name="B (蓝色)", default=True)

    # 隐藏属性，用于记录是否需要显示RGB选项
    has_rgb: bpy.props.BoolProperty(default=False, options={'HIDDEN'})

    @classmethod
    def poll(cls, context):
        return len(get_selected_curve_nodes(context)) > 0

    def invoke(self, context, event):
        # 检测是否有 RGB 曲线节点
        nodes = get_selected_curve_nodes(context)
        self.has_rgb = any(len(node.mapping.curves) == 4 for node in nodes)

        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        layout = self.layout

        box = layout.box()
        col = box.column(align=True)
        col.prop(self, "preset_type",expand=True)

        # 当选择自定义公式时，显示公式输入框和钳制选项
        if self.preset_type == 'CUSTOM':
            box = layout.box()
            col = box.column(align=True)
            col.label(text="支持: sin, cos, tan, pi, e, abs, sqrt 等")
            # 快速预解算，检查表达式是否合法
            is_valid = True
            try:
                safe_env = {k: getattr(math, k) for k in dir(math) if not k.startswith("_")}
                safe_env['abs'] = abs
                safe_env['round'] = round
                safe_env['x'] = 0.5  # 随便代入一个 x 值进行测试
                eval(self.expression, {"__builtins__": None}, safe_env)
            except Exception:
                is_valid = False
            # 使用单独的 row 来控制颜色
            row = col.row()
            row.alert = not is_valid  # 如果无法解算，开启红色警告
            row.prop(self, "expression")
            col.prop(self, "clamp_result", text="钳制结果 (0-1)")
            box.separator()

        box = layout.box()
        box.prop(self, "points_count")
        # 只有存在 RGB 曲线时，才显示通道选择
        if self.has_rgb:
            box.separator()
            row = box.row(align=True)
            row.label(text="应用到通道:")
            row.prop(self, "apply_c", icon="EVENT_C", text="")
            row.prop(self, "apply_r", icon="EVENT_R", text="")
            row.prop(self, "apply_g", icon="EVENT_G", text="")
            row.prop(self, "apply_b", icon="EVENT_B", text="")

    def execute(self, context):
        def ease_out_bounce(t):
            n1, d1 = 7.5625, 2.75
            if t < 1 / d1: return n1 * t * t
            elif t < 2 / d1: t -= 1.5 / d1; return n1 * t * t + 0.75
            elif t < 2.5 / d1: t -= 2.25 / d1; return n1 * t * t + 0.9375
            else: t -= 2.625 / d1; return n1 * t * t + 0.984375

        preset_funcs = {
            'LINEAR': lambda x: x,
            'SQUARE': lambda x: x ** 2,
            'CUBE': lambda x: x ** 3,
            'SINE': lambda x: 0.5 + 0.5 * math.sin(x * 2.0 * math.pi),
            'COSINE': lambda x: 0.5 + 0.5 * math.cos(x * 2.0 * math.pi),
            'QUAD_IN': lambda x: x * x,
            'QUAD_OUT': lambda x: 1 - (1 - x) * (1 - x),
            'QUAD_INOUT': lambda x: 2 * x * x if x < 0.5 else 1 - math.pow(-2 * x + 2, 2) / 2,
            'EXPO_IN': lambda x: 0 if x == 0 else math.pow(2, 10 * x - 10),
            'EXPO_OUT': lambda x: 1 if x == 1 else 1 - math.pow(2, -10 * x),
            'EXPO_INOUT': lambda x: x if x in (0, 1) else (math.pow(2, 20 * x - 10) / 2 if x < 0.5 else (2 - math.pow(2, -20 * x + 10)) / 2),
            'BOUNCE_IN': lambda x: 1 - ease_out_bounce(1 - x),
            'BOUNCE_OUT': lambda x: ease_out_bounce(x),
            'BOUNCE_INOUT': lambda x: (1 - ease_out_bounce(1 - 2 * x)) / 2 if x < 0.5 else (1 + ease_out_bounce(2 * x - 1)) / 2
        }

        x_vals, y_vals = [], []
        n = self.points_count

        # 处理自定义公式
        if self.preset_type == 'CUSTOM':
            safe_env = {k: getattr(math, k) for k in dir(math) if not k.startswith("_")}
            safe_env['abs'] = abs
            safe_env['round'] = round

            for i in range(n):
                x = i / (n - 1) if n > 1 else 0.5
                x_vals.append(x)
                safe_env['x'] = x
                try:
                    y = eval(self.expression, {"__builtins__": None}, safe_env)
                    y = round(float(y), 5)
                    if self.clamp_result:
                        y = max(0.0, min(1.0, y))
                    y_vals.append(y)
                except Exception as e:
                    self.report({'ERROR'}, f"表达式解析失败: {str(e)}")
                    return {'CANCELLED'}
        # 处理内置预设
        else:
            calc_func = preset_funcs.get(self.preset_type, lambda x: x)
            for i in range(n):
                x = i / (n - 1) if n > 1 else 0.5
                x_vals.append(x)
                y = calc_func(x)
                y_vals.append(max(0.0, min(1.0, round(y, 5))))

        # 将计算好的曲线数据应用到节点
        nodes = get_selected_curve_nodes(context)
        for node in nodes:
            mapping = node.mapping

            if len(mapping.curves) == 4:
                # RGB 曲线节点：根据用户的勾选状态应用
                if self.apply_r: set_curve_points(mapping.curves[0], x_vals, y_vals)
                if self.apply_g: set_curve_points(mapping.curves[1], x_vals, y_vals)
                if self.apply_b: set_curve_points(mapping.curves[2], x_vals, y_vals)
                if self.apply_c: set_curve_points(mapping.curves[3], x_vals, y_vals)
            else:
                # Float 浮点曲线节点：直接应用到唯一通道
                set_curve_points(mapping.curves[0], x_vals, y_vals)
            node.mapping.update()

        if context.area:
            context.area.tag_redraw()

        self.report({'INFO'}, f"已应用预设/公式，更新了 {len(nodes)} 个节点")
        return {'FINISHED'}

class BetterExperie_OT_CopyCurve(bpy.types.Operator):
    bl_idname = "better_experie.copy_curve"
    bl_label = "复制曲线"
    bl_description = "复制选中节点的曲线数据到剪贴板"

    @classmethod
    def poll(cls, context):
        return len(get_selected_curve_nodes(context)) > 0

    def execute(self, context):
        node = get_selected_curve_nodes(context)[0]
        mapping = node.mapping

        data = {}
        # 判断是 RGB 曲线还是 Float 曲线
        if len(mapping.curves) == 4:
            data["type"] = "RGB"
            data["channels"] = {}
            names = ["R", "G", "B", "C"]
            for i, name in enumerate(names):
                pts = [{"x": p.location[0], "y": p.location[1], "handle": p.handle_type} for p in mapping.curves[i].points]
                data["channels"][name] = pts
        else:
            data["type"] = "FLOAT"
            pts = [{"x": p.location[0], "y": p.location[1], "handle": p.handle_type} for p in mapping.curves[0].points]
            data["channels"] = {"FLOAT": pts}

        context.window_manager.clipboard = json.dumps(data)
        self.report({'INFO'}, f"已复制 {data['type']} 曲线数据")

        if context.area: context.area.tag_redraw()
        return {'FINISHED'}


class BetterExperie_OT_PasteCurve(bpy.types.Operator):
    bl_idname = "better_experie.paste_curve"
    bl_label = "粘贴曲线"
    bl_description = "将剪贴板的曲线数据粘贴到所有选中的节点"
    bl_options = {'REGISTER', 'UNDO'}

    # 目标通道选择 (用于 粘贴到RGB节点)
    paste_c: bpy.props.BoolProperty(name="C (综合)", default=True)
    paste_r: bpy.props.BoolProperty(name="R (红色)", default=True)
    paste_g: bpy.props.BoolProperty(name="G (绿色)", default=True)
    paste_b: bpy.props.BoolProperty(name="B (蓝色)", default=True)

    # 源通道选择 (用于 RGB数据 粘贴到 Float节点)
    source_for_float: bpy.props.EnumProperty(
        name="使用源通道",
        items=[
            ('C', "C (综合)", ""),
            ('R', "R (红色)", ""),
            ('G', "G (绿色)", ""),
            ('B', "B (蓝色)", "")
        ],
        default='C'
    )

    # 隐藏属性，用于记录当前的粘贴模式
    paste_mode: bpy.props.StringProperty(options={'HIDDEN'})

    @classmethod
    def poll(cls, context):
        return len(get_selected_curve_nodes(context)) > 0 and bool(context.window_manager.clipboard)

    def invoke(self, context, event):
        try:
            data = json.loads(context.window_manager.clipboard)
            src_type = data.get("type")
            if not src_type: raise ValueError
        except:
            self.report({'ERROR'}, "剪贴板中没有有效的曲线数据")
            return {'CANCELLED'}

        nodes = get_selected_curve_nodes(context)
        # 检查选中的节点中是否包含 RGB 曲线节点
        has_rgb_target = any(len(node.mapping.curves) == 4 for node in nodes)

        # 模式判断
        if src_type == "FLOAT" and not has_rgb_target:
            self.paste_mode = 'FLOAT_TO_FLOAT'
            return self.execute(context) # 单通道到单通道，直接执行无弹窗

        elif src_type == "FLOAT" and has_rgb_target:
            self.paste_mode = 'FLOAT_TO_RGB'
            return context.window_manager.invoke_props_dialog(self)

        elif src_type == "RGB" and has_rgb_target:
            self.paste_mode = 'RGB_TO_RGB'
            return context.window_manager.invoke_props_dialog(self)

        elif src_type == "RGB" and not has_rgb_target:
            self.paste_mode = 'RGB_TO_FLOAT'
            return context.window_manager.invoke_props_dialog(self)

        return {'CANCELLED'}

    def draw(self, context):
        layout = self.layout
        if self.paste_mode in ['FLOAT_TO_RGB', 'RGB_TO_RGB']:
            layout.label(text="粘贴到目标通道:")
            row = layout.row(align=True)
            row.prop(self, "paste_c", icon="EVENT_C", text="")
            row.prop(self, "paste_r", icon="EVENT_R", text="")
            row.prop(self, "paste_g", icon="EVENT_G", text="")
            row.prop(self, "paste_b", icon="EVENT_B", text="")
        elif self.paste_mode == 'RGB_TO_FLOAT':
            layout.label(text="选择要提取的源通道:")
            layout.prop(self, "source_for_float", expand=True)

    def execute(self, context):
        data = json.loads(context.window_manager.clipboard)
        nodes = get_selected_curve_nodes(context)

        for node in nodes:
            mapping = node.mapping
            is_target_rgb = len(mapping.curves) == 4

            if self.paste_mode == 'FLOAT_TO_FLOAT':
                pts = data["channels"]["FLOAT"]
                set_curve_points(mapping.curves[0], [p["x"] for p in pts], [p["y"] for p in pts], [p["handle"] for p in pts])

            elif self.paste_mode == 'FLOAT_TO_RGB':
                pts = data["channels"]["FLOAT"]
                if is_target_rgb:
                    if self.paste_r: set_curve_points(mapping.curves[0], [p["x"] for p in pts], [p["y"] for p in pts], [p["handle"] for p in pts])
                    if self.paste_g: set_curve_points(mapping.curves[1], [p["x"] for p in pts], [p["y"] for p in pts], [p["handle"] for p in pts])
                    if self.paste_b: set_curve_points(mapping.curves[2], [p["x"] for p in pts], [p["y"] for p in pts], [p["handle"] for p in pts])
                    if self.paste_c: set_curve_points(mapping.curves[3], [p["x"] for p in pts], [p["y"] for p in pts], [p["handle"] for p in pts])
                else:
                    set_curve_points(mapping.curves[0], [p["x"] for p in pts], [p["y"] for p in pts], [p["handle"] for p in pts])

            elif self.paste_mode == 'RGB_TO_RGB':
                if is_target_rgb:
                    if self.paste_r:
                        pts = data["channels"]["R"]
                        set_curve_points(mapping.curves[0], [p["x"] for p in pts], [p["y"] for p in pts], [p["handle"] for p in pts])
                    if self.paste_g:
                        pts = data["channels"]["G"]
                        set_curve_points(mapping.curves[1], [p["x"] for p in pts], [p["y"] for p in pts], [p["handle"] for p in pts])
                    if self.paste_b:
                        pts = data["channels"]["B"]
                        set_curve_points(mapping.curves[2], [p["x"] for p in pts], [p["y"] for p in pts], [p["handle"] for p in pts])
                    if self.paste_c:
                        pts = data["channels"]["C"]
                        set_curve_points(mapping.curves[3], [p["x"] for p in pts], [p["y"] for p in pts], [p["handle"] for p in pts])
                else:
                    # 容错：如果同时选中了RGB和Float节点，Float节点默认接收C通道
                    pts = data["channels"]["C"]
                    set_curve_points(mapping.curves[0], [p["x"] for p in pts], [p["y"] for p in pts], [p["handle"] for p in pts])

            elif self.paste_mode == 'RGB_TO_FLOAT':
                pts = data["channels"][self.source_for_float]
                if not is_target_rgb:
                    set_curve_points(mapping.curves[0], [p["x"] for p in pts], [p["y"] for p in pts], [p["handle"] for p in pts])
                else:
                    # 容错：如果同时选中了RGB和Float节点，RGB节点默认粘贴到C通道
                    set_curve_points(mapping.curves[3], [p["x"] for p in pts], [p["y"] for p in pts], [p["handle"] for p in pts])

            node.mapping.update()

        if context.area: context.area.tag_redraw()
        self.report({'INFO'}, f"已粘贴到 {len(nodes)} 个节点")
        return {'FINISHED'}

class BetterExperie_OT_TransformCurve(bpy.types.Operator):
    bl_idname = "better_experie.transform_curve"
    bl_label = "变换曲线"
    bl_description = "对曲线控制点进行水平翻转、垂直翻转或高级缩放偏移变换"
    bl_options = {'REGISTER', 'UNDO'}

    action: bpy.props.StringProperty()

    # 缩放/偏移参数
    scale_x: bpy.props.FloatProperty(name="【↔】X 缩放 (*)", default=1.0)
    offset_x: bpy.props.FloatProperty(name="【↔】X 偏移 (+)", default=0.0)
    clamp_x: bpy.props.BoolProperty(name="【↔】钳制 X (0-1)", default=False)

    scale_y: bpy.props.FloatProperty(name="【↕】Y 缩放 (*)", default=1.0)
    offset_y: bpy.props.FloatProperty(name="【↕】Y 偏移 (+)", default=0.0)
    clamp_y: bpy.props.BoolProperty(name="【↕】钳制 Y (0-1)", default=False)

    # 通道控制布尔值
    apply_c: bpy.props.BoolProperty(name="C (综合)", default=True)
    apply_r: bpy.props.BoolProperty(name="R (红色)", default=True)
    apply_g: bpy.props.BoolProperty(name="G (绿色)", default=True)
    apply_b: bpy.props.BoolProperty(name="B (蓝色)", default=True)

    # 隐藏属性，用于记录是否需要显示RGB选项
    has_rgb: bpy.props.BoolProperty(default=False, options={'HIDDEN'})

    @classmethod
    def poll(cls, context):
        return len(get_selected_curve_nodes(context)) > 0

    def invoke(self, context, event):
        nodes = get_selected_curve_nodes(context)
        self.has_rgb = any(len(node.mapping.curves) == 4 for node in nodes)

        # 如果是高级变换，或者包含RGB曲线需要选择通道，则弹出面板
        if self.action == 'TRANSFORM' or self.has_rgb:
            return context.window_manager.invoke_props_dialog(self)

        # 纯Float曲线的翻转，直接执行无弹窗
        return self.execute(context)

    def draw(self, context):
        layout = self.layout

        # 只有高级变换模式才显示缩放和偏移参数
        if self.action == 'TRANSFORM':
            col = layout.column(align=True)
            col.prop(self, "scale_x")
            col.prop(self, "offset_x")
            col.prop(self, "clamp_x")
            col.separator()
            col.prop(self, "scale_y")
            col.prop(self, "offset_y")
            col.prop(self, "clamp_y")

        # 只有存在 RGB 曲线时，才显示通道选择
        if self.has_rgb:
            if self.action == 'TRANSFORM':
                layout.separator()
            row = layout.row(align=True)
            row.label(text="应用到通道:")
            row.prop(self, "apply_c", icon="EVENT_C", text="")
            row.prop(self, "apply_r", icon="EVENT_R", text="")
            row.prop(self, "apply_g", icon="EVENT_G", text="")
            row.prop(self, "apply_b", icon="EVENT_B", text="")

    def execute(self, context):
        nodes = get_selected_curve_nodes(context)

        for node in nodes:
            mapping = node.mapping

            # 定义内部处理函数，针对单个曲线通道进行变换
            def transform_single_curve(curve):
                pts = [{"x": p.location[0], "y": p.location[1], "handle": p.handle_type} for p in curve.points]

                if self.action == 'FLIP_X':
                    for p in pts: p["x"] = 1.0 - p["x"]
                elif self.action == 'FLIP_Y':
                    for p in pts: p["y"] = 1.0 - p["y"]
                elif self.action == 'TRANSFORM':
                    for p in pts:
                        p["x"] = p["x"] * self.scale_x + self.offset_x
                        p["y"] = p["y"] * self.scale_y + self.offset_y

                # 限制X和Y在0-1之间，并按X重新排序
                for p in pts:
                    if self.clamp_x:
                        p["x"] = max(0.0, min(1.0, p["x"]))
                    if self.clamp_y:
                        p["y"] = max(0.0, min(1.0, p["y"]))
                pts.sort(key=lambda k: k["x"])

                set_curve_points(curve, [p["x"] for p in pts], [p["y"] for p in pts], [p["handle"] for p in pts])

            # 根据节点类型和勾选状态应用变换
            if len(mapping.curves) == 4:
                if self.apply_r: transform_single_curve(mapping.curves[0])
                if self.apply_g: transform_single_curve(mapping.curves[1])
                if self.apply_b: transform_single_curve(mapping.curves[2])
                if self.apply_c: transform_single_curve(mapping.curves[3])
            else:
                transform_single_curve(mapping.curves[0])

            node.mapping.update()

        if context.area:
            context.area.tag_redraw()
        return {'FINISHED'}

class BetterExperie_OT_SimplifyCurve(bpy.types.Operator):
    bl_idname = "better_experie.simplify_curve"
    bl_label = "精简点"
    bl_description = "使用RDP算法或定值采样精简曲线控制点"
    bl_options = {'REGISTER', 'UNDO'}

    mode: bpy.props.EnumProperty(
        name="模式",
        items=[('TOLERANCE', "容差", "使用 Douglas-Peucker 算法"),
               ('COUNT', "定值", "精简到指定点数")]
    )
    tolerance: bpy.props.FloatProperty(name="容差", default=0.05, min=0.001, max=0.5)
    target_count: bpy.props.IntProperty(name="目标点数", default=5, min=2, max=256)
    target_channel: bpy.props.EnumProperty(
        name="通道",
        items=[('3', "C (综合)", ""), ('0', "R (红色)", ""), ('1', "G (绿色)", ""), ('2', "B (蓝色)", "")],
        default='3'
    )
    @classmethod
    def poll(cls, context):
        return len(get_selected_curve_nodes(context)) > 0

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "target_channel")
        layout.prop(self, "mode")
        if self.mode == 'TOLERANCE':
            layout.prop(self, "tolerance")
        else:
            layout.prop(self, "target_count")

    def execute(self, context):
        def point_line_dist(p, a, b):
            if a == b: return math.hypot(p[0]-a[0], p[1]-a[1])
            return abs((b[0]-a[0])*(a[1]-p[1]) - (a[0]-p[0])*(b[1]-a[1])) / math.hypot(b[0]-a[0], b[1]-a[1])

        def rdp(pts, epsilon):
            dmax, index = 0.0, 0
            for i in range(1, len(pts) - 1):
                d = point_line_dist(pts[i], pts[0], pts[-1])
                if d > dmax: index, dmax = i, d
            if dmax > epsilon:
                return rdp(pts[:index+1], epsilon)[:-1] + rdp(pts[index:], epsilon)
            return [pts[0], pts[-1]]

        nodes = get_selected_curve_nodes(context)
        for node in nodes:
            curve = get_target_curve(node, self.target_channel)
            pts = [(p.location[0], p.location[1], p.handle_type) for p in curve.points]

            if len(pts) > 2:
                if self.mode == 'TOLERANCE':
                    simplified = rdp(pts, self.tolerance)
                else:
                    if len(pts) <= self.target_count:
                        simplified = pts
                    else:
                        simplified = [pts[0]]
                        step = (len(pts) - 1) / (self.target_count - 1)
                        for i in range(1, self.target_count - 1):
                            idx = int(round(i * step))
                            simplified.append(pts[idx])
                        simplified.append(pts[-1])

                set_curve_points(curve, [p[0] for p in simplified], [p[1] for p in simplified], [p[2] for p in simplified])
            node.mapping.update()

        if context.area: context.area.tag_redraw()
        return {'FINISHED'}

class BetterExperie_OT_ResetCurveChannel(bpy.types.Operator):
    bl_idname = "better_experie.reset_curve_channel"
    bl_label = "重置通道"
    bl_description = "将选中曲线通道重置为默认线性（0到1）"
    bl_options = {'REGISTER', 'UNDO'}
    # 弹窗中的布尔选项
    reset_c: bpy.props.BoolProperty(name="C (综合)", default=True)
    reset_r: bpy.props.BoolProperty(name="R (红色)", default=False)
    reset_g: bpy.props.BoolProperty(name="G (绿色)", default=False)
    reset_b: bpy.props.BoolProperty(name="B (蓝色)", default=False)

    @classmethod
    def poll(cls, context):
        return len(get_selected_curve_nodes(context)) > 0

    def invoke(self, context, event):
        nodes = get_selected_curve_nodes(context)
        # 检查选中的节点中是否包含 RGB 曲线节点 (拥有4个通道)
        has_rgb_curve = any(len(node.mapping.curves) == 4 for node in nodes)

        if has_rgb_curve:
            # 如果有RGB曲线，唤起面板让用户选择通道
            return context.window_manager.invoke_props_dialog(self)
        else:
            # 如果全是单通道浮点曲线，不弹窗，直接执行
            return self.execute(context)

    def draw(self, context):
        layout = self.layout
        row = layout.row(align=True)
        row.label(text="选择要重置的通道:")
        row.prop(self, "reset_c", icon="EVENT_C", text="")
        row.prop(self, "reset_r", icon="EVENT_R", text="")
        row.prop(self, "reset_g", icon="EVENT_G", text="")
        row.prop(self, "reset_b", icon="EVENT_B", text="")

    def execute(self, context):
        nodes = get_selected_curve_nodes(context)

        for node in nodes:
            mapping = node.mapping

            if len(mapping.curves) == 4:
                # 处理 RGB 曲线节点
                if self.reset_r:
                    set_curve_points(mapping.curves[0], [0.0, 1.0], [0.0, 1.0])
                if self.reset_g:
                    set_curve_points(mapping.curves[1], [0.0, 1.0], [0.0, 1.0])
                if self.reset_b:
                    set_curve_points(mapping.curves[2], [0.0, 1.0], [0.0, 1.0])
                if self.reset_c:
                    set_curve_points(mapping.curves[3], [0.0, 1.0], [0.0, 1.0])
            else:
                # 处理 Float 浮点曲线节点 (只有1个通道)
                set_curve_points(mapping.curves[0], [0.0, 1.0], [0.0, 1.0])
            node.mapping.update()

        if context.area:
            context.area.tag_redraw()

        return {'FINISHED'}


class BetterExperie_OT_SubdivideCurve(bpy.types.Operator):
    bl_idname = "better_experie.subdivide_curve"
    bl_label = "细分控制点"
    bl_description = "在曲线控制点之间线性插值插入新点，支持RGB多通道"
    bl_options = {'REGISTER', 'UNDO'}

    level: bpy.props.IntProperty(name="细分等级", default=2, min=2, max=4, description="在每两个点之间插入的段数")
    
    apply_c: bpy.props.BoolProperty(name="C (综合)", default=True)
    apply_r: bpy.props.BoolProperty(name="R (红色)", default=True)
    apply_g: bpy.props.BoolProperty(name="G (绿色)", default=True)
    apply_b: bpy.props.BoolProperty(name="B (蓝色)", default=True)
    has_rgb: bpy.props.BoolProperty(default=False, options={'HIDDEN'})

    @classmethod
    def poll(cls, context):
        return bool(get_selected_curve_nodes(context))

    def invoke(self, context, event):
        nodes = get_selected_curve_nodes(context)
        self.has_rgb = any(len(node.mapping.curves) == 4 for node in nodes)
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "level")
        if self.has_rgb:
            layout.separator()
            row = layout.row(align=True)
            row.label(text="应用到通道:")
            row.prop(self, "apply_c", icon="EVENT_C", text="")
            row.prop(self, "apply_r", icon="EVENT_R", text="")
            row.prop(self, "apply_g", icon="EVENT_G", text="")
            row.prop(self, "apply_b", icon="EVENT_B", text="")

    def execute(self, context):
        nodes = get_selected_curve_nodes(context)
        for node in nodes:
            mapping = node.mapping
            def process_curve(curve):
                pts = [{"x": p.location[0], "y": p.location[1], "handle": p.handle_type} for p in curve.points]
                new_pts = []
                for i in range(len(pts) - 1):
                    p1, p2 = pts[i], pts[i+1]
                    new_pts.append(p1)
                    for j in range(1, self.level):
                        t = j / self.level
                        new_pts.append({"x": p1["x"] * (1-t) + p2["x"] * t, "y": p1["y"] * (1-t) + p2["y"] * t, "handle": 'AUTO'})
                new_pts.append(pts[-1])
                set_curve_points(curve, [p["x"] for p in new_pts], [p["y"] for p in new_pts], [p["handle"] for p in new_pts])

            if len(mapping.curves) == 4:
                if self.apply_r: process_curve(mapping.curves[0])
                if self.apply_g: process_curve(mapping.curves[1])
                if self.apply_b: process_curve(mapping.curves[2])
                if self.apply_c: process_curve(mapping.curves[3])
            else:
                process_curve(mapping.curves[0])
            node.mapping.update()
        if context.area: context.area.tag_redraw()
        return {'FINISHED'}


class BetterExperie_OT_RandomizeCurve(bpy.types.Operator):
    bl_idname = "better_experie.randomize_curve"
    bl_label = "随机控制点"
    bl_description = "随机偏移曲线控制点的X/Y位置，支持钳制或循环"
    bl_options = {'REGISTER', 'UNDO'}

    axis: bpy.props.EnumProperty(name="轴向", items=[('Y', "垂直", ""), ('X', "水平", ""), ('ALL', "自由", "")], default='Y')
    factor: bpy.props.FloatProperty(name="随机系数", default=0.1, min=0.0, max=1.0)
    clamp_val: bpy.props.BoolProperty(name="钳制在 0-1", default=True, description="开启则钳制在0-1，关闭则超出的部分自动取余循环")

    apply_c: bpy.props.BoolProperty(name="C (综合)", default=True)
    apply_r: bpy.props.BoolProperty(name="R (红色)", default=True)
    apply_g: bpy.props.BoolProperty(name="G (绿色)", default=True)
    apply_b: bpy.props.BoolProperty(name="B (蓝色)", default=True)
    has_rgb: bpy.props.BoolProperty(default=False, options={'HIDDEN'})

    @classmethod
    def poll(cls, context):
        return bool(get_selected_curve_nodes(context))

    def invoke(self, context, event):
        nodes = get_selected_curve_nodes(context)
        self.has_rgb = any(len(node.mapping.curves) == 4 for node in nodes)
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "axis")
        layout.prop(self, "factor")
        layout.prop(self, "clamp_val")
        if self.has_rgb:
            layout.separator()
            row = layout.row(align=True)
            row.label(text="应用到通道:")
            row.prop(self, "apply_c", icon="EVENT_C", text="")
            row.prop(self, "apply_r", icon="EVENT_R", text="")
            row.prop(self, "apply_g", icon="EVENT_G", text="")
            row.prop(self, "apply_b", icon="EVENT_B", text="")

    def execute(self, context):
        nodes = get_selected_curve_nodes(context)
        for node in nodes:
            mapping = node.mapping
            def process_curve(curve):
                pts = [{"x": p.location[0], "y": p.location[1], "handle": p.handle_type} for p in curve.points]
                for p in pts:
                    if self.axis in ('X', 'ALL'):
                        p["x"] += (random.random() - 0.5) * 2 * self.factor
                        p["x"] = max(0.0, min(1.0, p["x"])) if self.clamp_val else p["x"] % 1.0
                    if self.axis in ('Y', 'ALL'):
                        p["y"] += (random.random() - 0.5) * 2 * self.factor
                        p["y"] = max(0.0, min(1.0, p["y"])) if self.clamp_val else p["y"] % 1.0
                pts.sort(key=lambda k: k["x"])
                set_curve_points(curve, [p["x"] for p in pts], [p["y"] for p in pts], [p["handle"] for p in pts])

            if len(mapping.curves) == 4:
                if self.apply_r: process_curve(mapping.curves[0])
                if self.apply_g: process_curve(mapping.curves[1])
                if self.apply_b: process_curve(mapping.curves[2])
                if self.apply_c: process_curve(mapping.curves[3])
            else:
                process_curve(mapping.curves[0])
            node.mapping.update()
        if context.area: context.area.tag_redraw()
        return {'FINISHED'}


class BetterExperie_OT_SmoothCurve(bpy.types.Operator):
    bl_idname = "better_experie.smooth_curve"
    bl_label = "平滑控制点"
    bl_description = "平滑曲线控制点，向相邻点平均值混合"
    bl_options = {'REGISTER', 'UNDO'}

    axis: bpy.props.EnumProperty(name="轴向", items=[('Y', "垂直", ""), ('X', "水平", ""), ('ALL', "自由", "")], default='Y')
    factor: bpy.props.FloatProperty(name="平滑系数", default=0.5, min=0.0, max=1.0)

    apply_c: bpy.props.BoolProperty(name="C (综合)", default=True)
    apply_r: bpy.props.BoolProperty(name="R (红色)", default=True)
    apply_g: bpy.props.BoolProperty(name="G (绿色)", default=True)
    apply_b: bpy.props.BoolProperty(name="B (蓝色)", default=True)
    has_rgb: bpy.props.BoolProperty(default=False, options={'HIDDEN'})

    @classmethod
    def poll(cls, context):
        return bool(get_selected_curve_nodes(context))

    def invoke(self, context, event):
        nodes = get_selected_curve_nodes(context)
        self.has_rgb = any(len(node.mapping.curves) == 4 for node in nodes)
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "axis")
        layout.prop(self, "factor")
        if self.has_rgb:
            layout.separator()
            row = layout.row(align=True)
            row.label(text="应用到通道:")
            row.prop(self, "apply_c", icon="EVENT_C", text="")
            row.prop(self, "apply_r", icon="EVENT_R", text="")
            row.prop(self, "apply_g", icon="EVENT_G", text="")
            row.prop(self, "apply_b", icon="EVENT_B", text="")

    def execute(self, context):
        nodes = get_selected_curve_nodes(context)
        for node in nodes:
            mapping = node.mapping
            def process_curve(curve):
                pts = [{"x": p.location[0], "y": p.location[1], "handle": p.handle_type} for p in curve.points]
                if len(pts) < 3: return
                new_pts = [{"x": p["x"], "y": p["y"], "handle": p["handle"]} for p in pts]
                for i in range(1, len(pts) - 1):
                    if self.axis in ('X', 'ALL'):
                        avg_x = (pts[i-1]["x"] + pts[i+1]["x"]) / 2.0
                        new_pts[i]["x"] = pts[i]["x"] * (1 - self.factor) + avg_x * self.factor
                    if self.axis in ('Y', 'ALL'):
                        avg_y = (pts[i-1]["y"] + pts[i+1]["y"]) / 2.0
                        new_pts[i]["y"] = pts[i]["y"] * (1 - self.factor) + avg_y * self.factor
                new_pts.sort(key=lambda k: k["x"])
                set_curve_points(curve, [p["x"] for p in new_pts], [p["y"] for p in new_pts], [p["handle"] for p in new_pts])


            if len(mapping.curves) == 4:
                if self.apply_r: process_curve(mapping.curves[0])
                if self.apply_g: process_curve(mapping.curves[1])
                if self.apply_b: process_curve(mapping.curves[2])
                if self.apply_c: process_curve(mapping.curves[3])
            else:
                process_curve(mapping.curves[0])
            node.mapping.update()
        if context.area: context.area.tag_redraw()
        return {'FINISHED'}



class BetterExperie_OT_ConvertHandleType(bpy.types.Operator):
    bl_idname = "better_experie.convert_handle_type"
    bl_label = "转换类型"
    bl_description = "统一设置所有控制点为自动、矢量或自动钳制类型"
    bl_options = {'REGISTER', 'UNDO'}

    target_type: bpy.props.EnumProperty(
        name="控制柄类型",
        items=[
            ('AUTO', "自动", "自动型控制柄", "HANDLE_AUTO",0),
            ('VECTOR', "矢量", "矢量型控制柄", "HANDLE_VECTOR",1),
            ('AUTO_CLAMPED', "自动钳制", "自动钳制型控制柄", "HANDLE_AUTOCLAMPED",2)  
        ],
        default='AUTO'
    )

    apply_c: bpy.props.BoolProperty(name="C (综合)", default=True)
    apply_r: bpy.props.BoolProperty(name="R (红色)", default=True)
    apply_g: bpy.props.BoolProperty(name="G (绿色)", default=True)
    apply_b: bpy.props.BoolProperty(name="B (蓝色)", default=True)
    has_rgb: bpy.props.BoolProperty(default=False, options={'HIDDEN'})

    @classmethod
    def poll(cls, context):
        return bool(get_selected_curve_nodes(context))

    def invoke(self, context, event):
        nodes = get_selected_curve_nodes(context)
        self.has_rgb = any(len(node.mapping.curves) == 4 for node in nodes)
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        layout = self.layout
        row = layout.row()
        row.prop(self, "target_type",expand=True)#下拉栏平铺用哪个
        if self.has_rgb:
            layout.separator()
            row = layout.row(align=True)
            row.label(text="应用到通道:")
            row.prop(self, "apply_c", icon="EVENT_C", text="")
            row.prop(self, "apply_r", icon="EVENT_R", text="")
            row.prop(self, "apply_g", icon="EVENT_G", text="")
            row.prop(self, "apply_b", icon="EVENT_B", text="")

    def execute(self, context):
        nodes = get_selected_curve_nodes(context)
        for node in nodes:
            mapping = node.mapping
            def process_curve(curve):
                # 直接遍历并修改控制柄类型，不需要重新生成点
                for p in curve.points:
                    p.handle_type = self.target_type

            if len(mapping.curves) == 4:
                if self.apply_r: process_curve(mapping.curves[0])
                if self.apply_g: process_curve(mapping.curves[1])
                if self.apply_b: process_curve(mapping.curves[2])
                if self.apply_c: process_curve(mapping.curves[3])
            else:
                process_curve(mapping.curves[0])
            node.mapping.update()
            
        if context.area: context.area.tag_redraw()
        return {'FINISHED'}


classes = (
    BetterExperie_OT_ApplyCurvePreset,
    BetterExperie_OT_CopyCurve,
    BetterExperie_OT_PasteCurve,
    BetterExperie_OT_TransformCurve,
    BetterExperie_OT_SimplifyCurve,
    BetterExperie_OT_SubdivideCurve,
    BetterExperie_OT_RandomizeCurve,
    BetterExperie_OT_SmoothCurve,
    BetterExperie_OT_ConvertHandleType,
    BetterExperie_OT_ResetCurveChannel,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

    
if __name__ == "__main__":
    register()
