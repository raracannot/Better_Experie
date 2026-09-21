# 智能模板表达式

import bpy
import os
import re
import getpass
import platform
from datetime import datetime
from bpy.app.handlers import persistent

tokens_description = """
-------------------------
可用变量：
{blend_name}：Blend 文件名（不含扩展名）
{prj}：Blend 文件名（不含扩展名）
{blend_dir}：Blend 文件所在目录
{frame}：当前活动帧
{range}：动画范围，例如 23_76
{fps}：当前帧率
{res}：实际渲染宽度高度，例如 800X600
{resolution_x}：实际渲染宽度
{res_x}：实际渲染宽度
{resolution_y}：实际渲染高度
{res_y}：实际渲染高度
{scene_name}：当前场景名称
{scene}：当前场景名称
{camera_name}：渲染摄像机名称
{camera}：渲染摄像机名称
{datetime}：时间戳，默认为 YYYYMMDD_HHmm
{batch}：渲染编号，渲染完成后自动加 1
{engine}：当前渲染引擎标识，例如 BLENDER_EEVEE_NEXT 或 CYCLES
{renderer}：当前渲染引擎标识
{frame_start}：动画起始帧
{frame_end}：动画结束帧
{frame_count}：动画总帧数
{blender_version}：当前 Blender 版本，例如 3.6.0
{blender}：当前 Blender 版本
{user_name}：当前系统用户名
{user}：当前系统用户名
{computer}：当前计算机名称

仅 File Output 节点模板可用：
    {scene_filepath}：当前场景已解析后的渲染输出路径
    {node_name}：当前 File Output 节点名称
    {node_tree_name}：当前合成器节点树名称
-------------------------
数值格式示例：
  {fps:###} → 030
  {fps:.###} → 29.970
  {fps:###.##} → 029.97
  {frame:####} → 0001

日期格式示例：
  {datetime} → 20261215_1400
  {datetime:YY} → 26
  {datetime:YYYY} → 2026
  {datetime:MM} → 12
  {datetime:DD} → 15
  {datetime:hh} → 02
  {datetime:HH} → 14
  {datetime:mm} → 00
  {datetime:SS} → 30
  {datetime:YYYY-MM-DD_HH-mm-SS} → 2026-12-15_14-00-30
  {datetime:YYYY"DD"DD} → 2026DD15

渲染编号示例：
  {batch} → 35
  {batch:#} → 35
  {batch:###} → 035
  {batch:#####} → 00035
-------------------------
花括号转义：
  {{ → {
  }} → }
-------------------------
"""


class BetterExperie_TemplateExpressionError(Exception):
    """模板表达式解析错误。"""
    pass

INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

def sanitize_filename(value):
    """清理 Windows 文件名中不允许出现的字符。"""
    cleaned = INVALID_FILENAME_CHARS.sub("_", str(value))
    cleaned = cleaned.rstrip(" .")
    return cleaned or "_"

def get_blend_name():
    """获取当前 Blend 文件名称，不含扩展名。"""
    filepath = bpy.data.filepath
    if not filepath:
        return "untitled"
    filename = os.path.basename(filepath)
    return os.path.splitext(filename)[0]

def get_blend_dir():
    """获取当前 Blend 文件所在目录。"""
    filepath = bpy.data.filepath
    if not filepath:
        return ""
    return os.path.dirname(filepath)

def get_camera_name(scene):
    """获取当前场景渲染摄像机名称。"""
    if scene.camera:
        return scene.camera.name
    return ""

def is_blender_5_or_later():
    """判断当前 Blender 是否为 5.0 或更高版本。"""
    return bpy.app.version >= (5, 0, 0)

def get_compositor_node_tree(scene):
    """
    获取场景使用的合成器节点树。
    Blender 4.x：
        scene.use_nodes
        scene.node_tree
    Blender 5.0+：
        scene.compositing_node_group
    """
    if is_blender_5_or_later():
        return scene.compositing_node_group
    if not scene.use_nodes:
        return None
    return scene.node_tree

def get_file_output_node_directory(node):
    """
    获取 File Output 节点输出目录。
    Blender 4.x 使用 node.base_path。
    Blender 5.0+ 使用 node.directory。
    """
    if is_blender_5_or_later():
        return node.directory
    return node.base_path

def set_file_output_node_directory(node, directory):
    """
    设置 File Output 节点输出目录。
    Blender 4.x 使用 node.base_path。
    Blender 5.0+ 使用 node.directory。
    """
    if is_blender_5_or_later():
        node.directory = directory
    else:
        node.base_path = directory

def set_file_output_node_file_name(node, file_name):
    """
    设置 File Output 节点文件名。
    Blender 4.x：
        File Output 节点可以拥有多个 File Slot，
        因此模板文件名会写入全部 slot.path。
    Blender 5.0+：
        使用 node.file_name。
    """
    if is_blender_5_or_later():
        node.file_name = file_name
        return
    for slot in node.file_slots:
        slot.path = file_name

def get_node_owner_scene(node):
    """
    查找正在使用该节点树的场景。
    File Output 节点的 id_data 是 NodeTree；
    这里通过 Scene.node_tree 找到该节点树所属场景。
    """
    node_tree = node.id_data
    for scene in bpy.data.scenes:
        if get_compositor_node_tree(scene) == node_tree:
            return scene
    return None

def get_template_variables(scene, extra_variables=None):
    """
    生成可用于模板替换的变量字典。
    extra_variables 用于补充节点专属变量：
    - scene_filepath
    - node_name
    - node_tree_name
    """
    scale = scene.render.resolution_percentage / 100.0
    resolution_x = round(scene.render.resolution_x * scale)
    resolution_y = round(scene.render.resolution_y * scale)
    blend_name = sanitize_filename(get_blend_name())
    camera_name = sanitize_filename(get_camera_name(scene))
    scene_name = sanitize_filename(scene.name)
    frame_count = ((scene.frame_end - scene.frame_start) // scene.frame_step) + 1
    blender_version = ".".join(str(number) for number in bpy.app.version)
    username = sanitize_filename(getpass.getuser())
    computer = sanitize_filename(platform.node())

    variables = {
        "blend_name": blend_name,
        "prj": blend_name,
        "blend_dir": get_blend_dir(),

        "frame": scene.frame_current,
        "frame_start": scene.frame_start,
        "frame_end": scene.frame_end,
        "frame_count": frame_count,
        "range": f"{scene.frame_start}_{scene.frame_end}",
        "batch": scene.better_experie_smart_template.batch,

        "fps": scene.render.fps / scene.render.fps_base,

        "res": f"{resolution_x}X{resolution_y}",
        "resolution_x": resolution_x,
        "res_x": resolution_x,
        "resolution_y": resolution_y,
        "res_y": resolution_y,

        "scene_name": scene_name,
        "scene": scene_name,
        "camera_name": camera_name,
        "camera": camera_name,

        "engine": scene.render.engine,
        "renderer": scene.render.engine,
        "blender_version": blender_version,
        "blender": blender_version,
        "user_name": username,
        "user": username,
        "computer": computer,

        "datetime": datetime.now(),
    }

    if extra_variables:
        variables.update(extra_variables)
    return variables

def format_number(value, format_spec):
    """
    支持以下格式：
    ###    ：至少 N 位整数，例如 030
    .###   ：小数点后固定 N 位，例如 29.970
    ###.## ：整数部分至少 N 位，小数点后固定 N 位，例如 029.97
    """
    if not format_spec:
        return str(value)
    if not re.fullmatch(r"#*(?:\.#*)?", format_spec):
        raise BetterExperie_TemplateExpressionError(f"无效的数值格式指定符：{format_spec}")
    if format_spec.count(".") > 1:
        raise BetterExperie_TemplateExpressionError(f"无效的数值格式指定符：{format_spec}")
    if "." not in format_spec:
        if not format_spec or any( char != "#" for char in format_spec):
            raise BetterExperie_TemplateExpressionError(f"无效的整数格式指定符：{format_spec}")
        width = len(format_spec)
        rounded_value = int(round(float(value)))
        return f"{rounded_value:0{width}d}"

    integer_part, decimal_part = format_spec.split(".", 1)
    if integer_part and any(char != "#" for char in integer_part):
        raise BetterExperie_TemplateExpressionError(f"无效的浮点格式指定符：{format_spec}")
    if decimal_part and any(char != "#" for char in decimal_part):
        raise BetterExperie_TemplateExpressionError(f"无效的浮点格式指定符：{format_spec}")

    integer_width = len(integer_part)
    decimal_places = len(decimal_part)
    rounded_value = round(float(value), decimal_places)
    result = f"{rounded_value:.{decimal_places}f}"
    if integer_width > 0:
        sign = ""
        if result.startswith("-"):
            sign = "-"
            result = result[1:]
        integer_text, decimal_text = result.split(".", 1)
        integer_text = integer_text.zfill(integer_width)
        result = f"{sign}{integer_text}.{decimal_text}"
    return result

def format_datetime(value, format_spec):
    """按照自定义日期 Token 格式化 datetime。"""
    if not isinstance(value, datetime):
        raise BetterExperie_TemplateExpressionError("datetime 不是有效的日期时间值。")
    if not format_spec:
        return value.strftime("%Y%m%d_%H%M")
    format_map = {
        "YYYY": "%Y",
        "yyyy": "%Y",
        "YY": "%y",
        "yy": "%y",
        "MM": "%m",
        "DD": "%d",
        "dd": "%d",
        "HH": "%H",
        "hh": "%I",
        "mm": "%M",
        "SS": "%S",
        "ss": "%S",
    }

    sorted_tokens = sorted(format_map.keys(),key=len,reverse=True)

    result = []
    index = 0
    length = len(format_spec)

    while index < length:
        char = format_spec[index]

        # 单引号或双引号中的内容原样输出。
        if char in ("'", '"'):
            quote = char
            closing_index = format_spec.find(quote,index + 1)
            if closing_index == -1:
                raise BetterExperie_TemplateExpressionError(f"日期格式中的引号“{quote}”未关闭。")

            result.append(format_spec[index + 1:closing_index])
            index = closing_index + 1
            continue
        matched = False

        for token in sorted_tokens:
            if format_spec.startswith(token, index):
                result.append(value.strftime(format_map[token]))
                index += len(token)
                matched = True
                break

        if matched:
            continue
        result.append(char)
        index += 1
    return "".join(result)

def parse_token(token_text, variables):
    """解析单个 Token，例如 fps、fps:###、datetime:YYYY-MM-DD。"""
    if ":" in token_text:
        variable_name, format_spec = token_text.split(":", 1)
    else:
        variable_name = token_text
        format_spec = ""

    variable_name = variable_name.strip()
    format_spec = format_spec.strip()
    if not variable_name:
        raise BetterExperie_TemplateExpressionError("发现空变量名。")
    if variable_name not in variables:
        raise BetterExperie_TemplateExpressionError(f"未知模板变量：{variable_name}")

    value = variables[variable_name]

    if variable_name == "datetime":
        return format_datetime(value, format_spec)
    if format_spec:
        if not isinstance(value, (int, float)):
            raise BetterExperie_TemplateExpressionError(f"变量“{variable_name}”不支持格式指定符。")
        return format_number(value, format_spec)
    return str(value)

def parse_template(template, scene, extra_variables=None):
    """
    解析模板路径。

    支持：
    - {blend_name}
    - {frame:####}
    - {datetime:YYYY-MM-DD}
    - {{ 转义为 {
    - }} 转义为 }
    """
    variables = get_template_variables(scene,extra_variables,)
    result = []
    index = 0
    length = len(template)

    while index < length:
        char = template[index]
        if char == "{":
            if index + 1 < length and template[index + 1] == "{":
                result.append("{")
                index += 2
                continue

            closing_index = template.find("}", index + 1)
            if closing_index == -1:
                raise BetterExperie_TemplateExpressionError("模板表达式未关闭：缺少右花括号“}”。")

            token_text = template[index + 1:closing_index]
            if "{" in token_text or "}" in token_text:
                raise BetterExperie_TemplateExpressionError("模板表达式中存在无效花括号。")
            result.append(parse_token(token_text, variables))
            index = closing_index + 1
            continue

        if char == "}":
            if index + 1 < length and template[index + 1] == "}":
                result.append("}")
                index += 2
                continue
            raise BetterExperie_TemplateExpressionError("发现未转义的右花括号“}”。如需输出右花括号，请使用“}}”。")

        result.append(char)
        index += 1
    return "".join(result)

def update_smart_template_base(scene):
    """
    刷新场景输出路径模板的预览与错误状态。
    不会在编辑模板时直接修改 scene.render.filepath。
    """
    settings = scene.better_experie_smart_template
    if not settings.enabled:
        settings.error = ""
        settings.preview_path = ""
        return
        
    template = settings.expression.strip()
    if not template:
        settings.error = "智能模板表达式为空。"
        settings.preview_path = ""
        return
    
    try:
        settings.preview_path = parse_template(template,scene)
        settings.error = ""
    except BetterExperie_TemplateExpressionError as error:
        settings.preview_path = ""
        settings.error = str(error)

def update_smart_template_expression(self, context):
    """场景 PropertyGroup 属性变更时刷新预览。"""
    scene = self.id_data
    update_smart_template_base(scene)

class BetterExperie_SmartTemplateSettings(bpy.types.PropertyGroup):
    """场景渲染输出路径的智能模板配置。"""
    enabled: bpy.props.BoolProperty(
        name="启用智能模板表达式",description="渲染开始前解析模板并更新渲染输出路径",
        default=False,update=update_smart_template_expression,)
    expression: bpy.props.StringProperty(
        name="智能模板表达式",description=f"用于生成渲染输出路径的模板{tokens_description}",
        default="//{blend_name}_{datetime}",update=update_smart_template_expression,)
    batch: bpy.props.IntProperty(
        name="渲染编号",description="渲染完成后自动加 1，可手动设置或归零",
        default=0,min=0,update=update_smart_template_expression,)

    error: bpy.props.StringProperty(name="模板错误",default="",options={"HIDDEN"},)
    preview_path: bpy.props.StringProperty(name="解析后的路径",default="",options={"HIDDEN"},)

def get_file_output_extra_variables(scene, node):
    """生成 File Output 节点专属模板变量。"""
    return {
        # 该路径会在 render_pre 中优先更新 Scene 输出模板后再读取。
        "scene_filepath": scene.render.filepath,
        "node_name": sanitize_filename(node.name),
        "node_tree_name": sanitize_filename(node.id_data.name),
    }

def update_file_output_template_preview(scene, node):
    """
    更新单个 File Output 节点模板预览。

    此函数仅更新预览，不直接写入 node.base_path 或 slot.path。
    """
    settings = node.better_experie_smart_template
    if not settings.enabled:
        settings.error = ""
        settings.preview_path = ""
        return

    directory_expression = settings.directory_expression.strip()
    file_name_expression = settings.directory_file_name.strip()

    if not directory_expression:
        settings.error = "路径智能模板表达式为空。"
        settings.preview_path = ""
        return

    if not file_name_expression:
        settings.error = "文件名智能模板表达式为空。"
        settings.preview_path = ""
        return

    try:
        extra_variables = get_file_output_extra_variables(scene,node)
        directory = parse_template(directory_expression,scene,extra_variables)
        file_name = parse_template(file_name_expression,scene,extra_variables)
        settings.preview_path = os.path.join(directory,file_name)
        settings.error = ""

    except BetterExperie_TemplateExpressionError as error:
        settings.preview_path = ""
        settings.error = str(error)


def update_file_output_template(self, context):
    """
    File Output 节点模板属性更新回调。

    在 Blender 5.x 中，PropertyGroup.id_data 是 CompositorNodeTree，
    并不是具体的 File Output 节点，因此不能用 self.id_data 作为 node。

    通过当前节点编辑器的活动节点取得实际节点；
    没有可用上下文时，跳过即时预览。渲染前仍会正常更新。
    """
    if context is None:
        return
    node = getattr(context, "active_node", None)
    if node is None:
        return
    if node.bl_idname != "CompositorNodeOutputFile":
        return
    # 确保当前编辑器中的活动节点，正是触发该属性更新的所属节点。
    if not hasattr(node, "better_experie_smart_template"):
        return
    if node.better_experie_smart_template.as_pointer() != self.as_pointer():
        return
    node.show_options = not self.enabled
    scene = get_node_owner_scene(node)
    if scene:
        update_file_output_template_preview(scene, node)


class BetterExperie_SmartTemplateFileOutputSettings(bpy.types.PropertyGroup):
    """File Output 节点的智能模板配置。"""
    enabled: bpy.props.BoolProperty(
        name="启用智能模板表达式", description="渲染开始前解析模板并更新此 File Output 节点路径和文件名",
        default=False, update=update_file_output_template,)
    directory_expression: bpy.props.StringProperty(
        name="路径智能模板表达式", description=f"用于生成 File Output 路径的模板{tokens_description}",
        default="{scene_filepath}", update=update_file_output_template,)
    directory_file_name: bpy.props.StringProperty(
        name="文件名智能模板表达式", description=f"用于生成 File Output 文件名的模板{tokens_description}",
        default="{node_name}", update=update_file_output_template,)

    error: bpy.props.StringProperty(name="模板错误", default="", options={"HIDDEN"})
    preview_path: bpy.props.StringProperty(name="解析后的路径", default="", options={"HIDDEN"})

def update_all_file_output_template_previews(scene):
    """刷新当前场景中所有 File Output 节点的模板预览。"""
    node_tree = get_compositor_node_tree(scene)
    if not node_tree:
        return
    for node in node_tree.nodes:
        if node.bl_idname == "CompositorNodeOutputFile":
            update_file_output_template_preview(scene, node)

def apply_file_output_templates(scene):
    """
    在渲染前解析并写入全部启用的 File Output 节点模板。
    Blender 4.x：
    - node.base_path：目录
    - node.file_slots[*].path：文件名前缀
    Blender 5.0+：
    - node.directory：目录
    - node.file_name：文件名
    """
    node_tree = get_compositor_node_tree(scene)
    if not node_tree:
        return
    for node in node_tree.nodes:
        if node.bl_idname != "CompositorNodeOutputFile":
            continue

        settings = node.better_experie_smart_template
        if not settings.enabled:
            continue

        update_file_output_template_preview(scene, node)
        if settings.error:
            print(f"[智能模板表达式] File Output 节点“{node.name}”模板解析失败：{settings.error}")
            continue

        try:
            extra_variables = get_file_output_extra_variables(scene,node)

            directory = parse_template(settings.directory_expression.strip(),scene,extra_variables,)
            file_name = parse_template(settings.directory_file_name.strip(),scene,extra_variables,)

            set_file_output_node_directory(node, directory)
            set_file_output_node_file_name(node, file_name)

        except BetterExperie_TemplateExpressionError as error:
            settings.error = str(error)
            settings.preview_path = ""

            print(f"[智能模板表达式] File Output 节点“{node.name}”模板解析失败：{settings.error}")

@persistent
def smart_template_render_pre(scene):
    """
    每次渲染前执行。

    执行顺序：
    1. 更新 Scene 渲染输出路径；
    2. 再更新 File Output 节点路径；
    3. 因此节点中的 {scene_filepath} 能取得更新后的场景路径。
    """
    scene_settings = scene.better_experie_smart_template
    if scene_settings.enabled:
        update_smart_template_base(scene)

        if scene_settings.preview_path:
            scene.render.filepath = scene_settings.preview_path
        elif scene_settings.error:
            print(f"[智能模板表达式] 场景模板解析失败：{scene_settings.error}")

    apply_file_output_templates(scene)

@persistent
def smart_template_render_complete(scene):
    """渲染正常完成后，自动增加 Scene 的渲染编号。"""
    settings = scene.better_experie_smart_template
    if not settings.enabled:
        return

    settings.batch += 1

    update_smart_template_base(scene)
    update_all_file_output_template_previews(scene)


class BETTER_EXPERIE_PT_smart_template(bpy.types.Panel):
    """渲染输出中的场景智能模板面板。"""
    bl_label = "智能模板表达式"
    bl_idname = "BETTER_EXPERIE_PT_smart_template"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "output"
    bl_parent_id = "RENDER_PT_output"
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        if context.scene is None:
            return False
        media_type = getattr(context.scene.render.image_settings,"media_type","IMAGE")
        return media_type != 'VIDEO'

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        settings = scene.better_experie_smart_template

        layout.prop(settings,"enabled",text="启用智能模板表达式")

        column = layout.column()
        column.enabled = settings.enabled
        column.prop(settings, "expression", text="智能模板表达式")
        column.prop(settings, "batch", text="渲染编号")

        if settings.enabled:
            box = column.box()
            if settings.error:
                box.alert = True
                box.label(text=settings.error, icon="ERROR")
            elif settings.preview_path:
                box.label(text=settings.preview_path)

def draw_smart_template_node_properties(self, context):
    node = context.active_node
    if node is None or node.bl_idname != "CompositorNodeOutputFile":
        return

    layout = self.layout
    settings = node.better_experie_smart_template

    box = layout.box()
    box.prop(settings, "enabled", text="启用智能模板表达式")
    if settings.enabled:
        column = box.column()
        column.enabled = settings.enabled
        column.prop(settings, "directory_expression", text="路径智能模板表达式")
        column.prop(settings, "directory_file_name", text="文件名智能模板表达式")
        if settings.error:
            column.alert = True
            column.label(text=settings.error, icon="ERROR")
        elif settings.preview_path:
            column.label(text=settings.preview_path)

classes = (
    BetterExperie_SmartTemplateSettings,
    BetterExperie_SmartTemplateFileOutputSettings,
    BETTER_EXPERIE_PT_smart_template,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    bpy.types.Scene.better_experie_smart_template = bpy.props.PointerProperty(type=BetterExperie_SmartTemplateSettings)
    bpy.types.CompositorNodeOutputFile.better_experie_smart_template = (bpy.props.PointerProperty(type=BetterExperie_SmartTemplateFileOutputSettings))

    bpy.types.NODE_PT_active_node_properties.prepend(draw_smart_template_node_properties)
    
    if smart_template_render_pre not in bpy.app.handlers.render_pre:
        bpy.app.handlers.render_pre.append(smart_template_render_pre)
    if smart_template_render_complete not in bpy.app.handlers.render_complete:
        bpy.app.handlers.render_complete.append(smart_template_render_complete)



def unregister():
    if smart_template_render_pre in bpy.app.handlers.render_pre:
        bpy.app.handlers.render_pre.remove(smart_template_render_pre)
    if smart_template_render_complete in bpy.app.handlers.render_complete:
        bpy.app.handlers.render_complete.remove(smart_template_render_complete)

    bpy.types.NODE_PT_active_node_properties.remove(draw_smart_template_node_properties)

    del bpy.types.CompositorNodeOutputFile.better_experie_smart_template
    del bpy.types.Scene.better_experie_smart_template

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
