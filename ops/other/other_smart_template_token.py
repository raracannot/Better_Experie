# 智能模板表达式的 token 组装弹窗

import re

import bpy

from . import other_render_smart_template as smart_template

# token 名称 -> (中文显示名, 说明文字)
# 唯一配置源：追加按钮、显示名、悬停说明都复用它。
# 这里的每个名字都必须能被 other_render_smart_template.parse_token 解析，
# 否则点出来的按钮会直接报「未知模板变量」。
TOKEN_LABELS = {
    "blend_name": ("Blend 文件名", "Blend 文件名（不含扩展名）"),
    "blend_dir": ("Blend 所在目录", "Blend 文件所在目录"),
    "frame": ("当前活动帧", "当前活动帧"),
    "frame_start": ("起始帧", "动画起始帧"),
    "frame_end": ("结束帧", "动画结束帧"),
    "range": ("动画范围", "动画范围，例如 23_76"),
    "fps": ("当前帧率", "当前帧率"),
    "res": ("分辨率", "实际渲染宽高，例如 800X600"),
    "resolution_x": ("渲染宽度", "实际渲染宽度"),
    "resolution_y": ("渲染高度", "实际渲染高度"),
    "scene_name": ("场景名称", "当前场景名称"),
    "camera_name": ("摄像机名称", "渲染摄像机名称"),
    "engine": ("渲染引擎", "当前渲染引擎标识"),
    "batch": ("渲染编号", "渲染编号，渲染完成后自动加 1"),
    "blender_version": ("Blender 版本", "当前 Blender 版本"),
    "user_name": ("用户名", "当前系统用户名"),
    "computer": ("计算机名", "当前计算机名称"),
    "datetime": ("时间戳", "时间戳，默认 YYYYMMDD_HHmm"),
    "datetime:YYYYMMDD_HHmm": ("时间戳(年月日_时分)", "时间戳，年月日_时分"),
    "datetime:YYYYMMDD_HHmmSS": ("时间戳(年月日_时分秒)", "时间戳，年月日_时分秒"),
    "datetime:YYYY-MM-DD_HH-mm-SS": ("时间戳(带横杠)", "时间戳，2026-12-15_14-00-30"),
    "fps:###": ("帧率(整数3位)", "例如 030"),
    "fps:.###": ("帧率(3位小数)", "例如 29.970"),
    "frame:####": ("当前帧(4位补零)", "例如 0001"),
    "batch:###": ("渲染编号(3位)", "例如 035"),
    "scene_filepath": ("场景输出路径", "当前场景已解析后的渲染输出路径"),
    "node_name": ("节点名称", "当前 File Output 节点名称"),
    "node_tree_name": ("节点树名称", "当前合成器节点树名称"),
}

# 行分组：(行标题, token 列表)。节点专属变量单独一行，只在节点模板里出现。
TOKEN_ROWS = (
    ("文件", ("blend_name", "blend_dir", "user_name", "blender_version", "computer")),
    ("帧信息", ("frame", "frame_start", "frame_end", "range", "fps")),
    ("场景", ("scene_name", "camera_name", "resolution_x", "resolution_y", "res", "engine")),
    ("批次", ("batch",)),
    ("时间", ("datetime", "datetime:YYYYMMDD_HHmm", "datetime:YYYYMMDD_HHmmSS",
              "datetime:YYYY-MM-DD_HH-mm-SS")),
    ("格式", ("fps:###", "fps:.###", "frame:####", "batch:###")),
)
NODE_TOKEN_ROW = ("节点", ("scene_filepath", "node_name", "node_tree_name"))

TOKEN_PATTERN = re.compile(r"\{([^{}]*)\}")

TARGET_LABELS = {
    'SCENE': "智能模板表达式",
    'NODE_DIRECTORY': "路径智能模板表达式",
    'NODE_FILE_NAME': "文件名智能模板表达式",
}


# ----------------------------------------------------------------------
# 纯函数：切分片段 / 追加 / 移除
# ----------------------------------------------------------------------
def split_segments(text):
    """把表达式切成 (类型, 值, 起, 止) 的片段列表。"""
    segments = []
    last = 0
    for match in TOKEN_PATTERN.finditer(text):
        if match.start() > last:
            segments.append(('text', text[last:match.start()], last, match.start()))
        segments.append(('token', match.group(1), match.start(), match.end()))
        last = match.end()
    if last < len(text):
        segments.append(('text', text[last:], last, len(text)))
    return segments


def apply_append(text, token_name):
    """在文本末尾追加一个 {token}。"""
    return text + "{" + token_name + "}"


def apply_remove(text, index):
    """移除第 index 个片段（普通文本或 token）。"""
    segments = split_segments(text)
    if 0 <= index < len(segments):
        _kind, _value, start, end = segments[index]
        return text[:start] + text[end:]
    return text


def tr(text):
    """取当前界面的翻译文本；翻译表里没有就原样返回。

    用于 f-string 拼接出来的文本（整串不是翻译表的键），
    单独翻译其中的固定片段，避免英文界面里夹中文。
    """
    try:
        return bpy.app.translations.pgettext(text, "*")
    except Exception:
        return text


def _lookup(name):
    """先按完整 key 查，查不到再按冒号前的主名查。"""
    entry = TOKEN_LABELS.get(name)
    if entry is None and ':' in name:
        entry = TOKEN_LABELS.get(name.split(':', 1)[0])
    return entry


def token_label(name):
    """取 token 的中文显示名，未配置则回退原名。"""
    entry = _lookup(name)
    return entry[0] if entry else name


def token_desc(name):
    """取 token 的说明文字，未配置则回退默认。"""
    entry = _lookup(name)
    return entry[1] if entry else "未知 token，点击移除"


# ----------------------------------------------------------------------
# 目标定位：场景属性 / File Output 节点的两个表达式
# ----------------------------------------------------------------------
def _find_node_by_pointer(pointer):
    """按 as_pointer 找回 File Output 节点；节点被删掉时返回 None。"""
    if not pointer:
        return None
    try:
        pointer = int(pointer)
    except (TypeError, ValueError):
        return None
    for scene in bpy.data.scenes:
        node_tree = smart_template.get_compositor_node_tree(scene)
        if not node_tree:
            continue
        for node in node_tree.nodes:
            if node.bl_idname == "CompositorNodeOutputFile" and node.as_pointer() == pointer:
                return node
    return None


def _target_text(context, settings):
    """读目标输入框当前内容；目标失效时返回 None。"""
    if settings.target == 'SCENE':
        return context.scene.better_experie_smart_template.expression

    node = _find_node_by_pointer(settings.node_pointer)
    if node is None:
        return None
    group = node.better_experie_smart_template
    if settings.target == 'NODE_DIRECTORY':
        return group.directory_expression
    return group.directory_file_name


def _parse_preview(context, settings):
    """解析草稿，返回 (预览文本, 错误文本)。只读，不写任何属性。"""
    text = settings.text.strip()
    if not text:
        return "", "表达式为空。"

    scene = context.scene
    extra_variables = None
    if settings.target != 'SCENE':
        node = _find_node_by_pointer(settings.node_pointer)
        if node is None:
            return "", "节点已失效，请重新选中 File Output 节点。"
        scene = smart_template.get_node_owner_scene(node) or scene
        extra_variables = smart_template.get_file_output_extra_variables(scene, node)

    try:
        return smart_template.parse_template(text, scene, extra_variables), ""
    except smart_template.BetterExperie_TemplateExpressionError as error:
        return "", str(error)


# ----------------------------------------------------------------------
# 草稿属性
# ----------------------------------------------------------------------
class BetterExperie_SmartTemplateTokenSettings(bpy.types.PropertyGroup):
    """token 组装弹窗的草稿（不写回目标输入框，点确定才写）。"""
    text: bpy.props.StringProperty(
        name="表达式", description="组装结果；点确定后写入对应的智能模板表达式", default="")
    target: bpy.props.EnumProperty(
        name="目标",
        items=[
            ('SCENE', "场景表达式", "渲染输出 > 智能模板表达式"),
            ('NODE_DIRECTORY', "节点路径表达式", "File Output 节点的路径智能模板表达式"),
            ('NODE_FILE_NAME', "节点文件名表达式", "File Output 节点的文件名智能模板表达式"),
        ],
        default='SCENE')
    node_pointer: bpy.props.StringProperty(name="节点指针", default="", options={"HIDDEN"})


# ----------------------------------------------------------------------
# 操作符：编辑草稿（追加 token / 移除片段）
# ----------------------------------------------------------------------
class BetterExperie_OT_SmartTemplateTokenEdit(bpy.types.Operator):
    bl_idname = "better_experie.smart_template_token_edit"
    bl_label = "编辑 token"
    bl_description = "追加 token 或移除指定片段"
    bl_options = {'REGISTER'}

    action: bpy.props.EnumProperty(
        name="动作",
        items=[
            ('APPEND', "追加", "追加一个 token"),
            ('REMOVE', "移除", "移除指定编号的片段"),
        ],
        default='APPEND')
    token_text: bpy.props.StringProperty(name="token", description="追加时使用的 token 名", default="")
    index: bpy.props.IntProperty(name="编号", description="移除时的片段编号（从 0 开始）", default=0)
    desc_data: bpy.props.StringProperty(options={'SKIP_SAVE'})

    @classmethod
    def description(cls, context, properties):
        return properties.desc_data or ""

    def execute(self, context):
        settings = context.scene.better_experie_smart_template_token
        if self.action == 'APPEND':
            settings.text = apply_append(settings.text, self.token_text)
        else:
            settings.text = apply_remove(settings.text, self.index)

        if context.area:
            context.area.tag_redraw()
        return {'FINISHED'}


# ----------------------------------------------------------------------
# 操作符：弹窗
# ----------------------------------------------------------------------
class BetterExperie_OT_SmartTemplateToken(bpy.types.Operator):
    bl_idname = "better_experie.smart_template_token"
    bl_label = "token 组装"
    bl_description = "打开 token 组装面板，拼好后点确定写入这个表达式输入框"
    bl_options = {'REGISTER'}

    target: bpy.props.EnumProperty(
        name="目标",
        items=[
            ('SCENE', "场景表达式", "渲染输出 > 智能模板表达式"),
            ('NODE_DIRECTORY', "节点路径表达式", "File Output 节点的路径智能模板表达式"),
            ('NODE_FILE_NAME', "节点文件名表达式", "File Output 节点的文件名智能模板表达式"),
        ],
        default='SCENE')

    @classmethod
    def poll(cls, context):
        return context.scene is not None

    def invoke(self, context, event):
        settings = context.scene.better_experie_smart_template_token
        settings.target = self.target
        settings.node_pointer = ""

        if self.target != 'SCENE':
            node = getattr(context, "active_node", None)
            if node is None or node.bl_idname != "CompositorNodeOutputFile":
                self.report({'WARNING'}, "请先在节点编辑器中选中 File Output 节点")
                return {'CANCELLED'}
            settings.node_pointer = str(node.as_pointer())

        current = _target_text(context, settings)
        if current is None:
            self.report({'WARNING'}, "目标表达式已失效，请重新打开")
            return {'CANCELLED'}
        settings.text = current
        return context.window_manager.invoke_props_dialog(self, width=760)

    def draw(self, context):
        layout = self.layout
        settings = context.scene.better_experie_smart_template_token

        column = layout.column(align=True)
        column.label(text=f"{tr('正在编辑：')}{tr(TARGET_LABELS.get(settings.target, ''))}")
        column.label(text="token组装结果：")
        column.prop(settings, "text", text="")

        segments = split_segments(settings.text)
        if segments:
            row = column.row(align=True)
            for index, (kind, value, _start, _end) in enumerate(segments):
                if kind == 'text':
                    text = value
                    desc = tr("普通文本片段")
                else:
                    text = f"【{tr(token_label(value))}】"
                    desc = tr(token_desc(value))
                op = row.operator("better_experie.smart_template_token_edit", icon="X", text=text)
                op.action = 'REMOVE'
                op.index = index
                op.desc_data = f"{value}\n{desc}{tr('，点击移除')}"
        else:
            column.label(text="（暂无内容）")

        preview, error = _parse_preview(context, settings)
        box = column.box()
        if error:
            box.alert = True
            box.label(text=error, icon="ERROR")
        else:
            box.label(text=preview, icon="CHECKMARK")

        layout.separator()
        for title, names in TOKEN_ROWS:
            self.draw_token_row(layout, title, names)
        if settings.target != 'SCENE':
            self.draw_token_row(layout, *NODE_TOKEN_ROW)

    def draw_token_row(self, layout, title, names):
        """一行：标题占 20%，按钮占 80%。"""
        row = layout.row(align=True)
        split = row.split(factor=0.16, align=True)
        split.label(text=title)
        btn_row = split.row(align=True)
        for name in names:
            label, desc = TOKEN_LABELS.get(name, (name, ""))
            op = btn_row.operator("better_experie.smart_template_token_edit", text=label)
            op.action = 'APPEND'
            op.token_text = name
            op.desc_data = desc

    def execute(self, context):
        settings = context.scene.better_experie_smart_template_token
        text = settings.text

        if settings.target == 'SCENE':
            scene_settings = context.scene.better_experie_smart_template
            scene_settings.expression = text
            smart_template.update_smart_template_base(context.scene)
            self.report({'INFO'}, f"已写入智能模板表达式：{text}")
            return {'FINISHED'}

        node = _find_node_by_pointer(settings.node_pointer)
        if node is None:
            self.report({'ERROR'}, "File Output 节点已失效，请重新打开面板")
            return {'CANCELLED'}

        group = node.better_experie_smart_template
        if settings.target == 'NODE_DIRECTORY':
            group.directory_expression = text
        else:
            group.directory_file_name = text

        scene = smart_template.get_node_owner_scene(node) or context.scene
        smart_template.update_file_output_template_preview(scene, node)
        self.report({'INFO'}, f"已写入{TARGET_LABELS.get(settings.target, '')}：{text}")
        return {'FINISHED'}


classes = (
    BetterExperie_SmartTemplateTokenSettings,
    BetterExperie_OT_SmartTemplateTokenEdit,
    BetterExperie_OT_SmartTemplateToken,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    bpy.types.Scene.better_experie_smart_template_token = bpy.props.PointerProperty(
        type=BetterExperie_SmartTemplateTokenSettings)


def unregister():
    del bpy.types.Scene.better_experie_smart_template_token

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
