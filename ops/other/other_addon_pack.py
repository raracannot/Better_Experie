# 插件打包工具

import re
import json
import bpy
import os
import subprocess
import ast
import datetime
import shutil

from ...utils import get_pref


ALLOWED_TAGS = {
    "3D View", "Add Curve", "Add Mesh", "All", "Animation", "Bake",
    "Camera", "Compositing", "Development", "Game Engine", "Geometry Nodes",
    "Grease Pencil", "Import-Export", "Lighting", "Material", "Mesh",
    "Modeling", "Node", "Object", "Paint", "Physics", "Pipeline",
    "Render", "Rigging", "Scene", "Sculpt", "Sequencer", "System",
    "Text Editor", "Tracking", "UV", "User Interface"
}

TAG_PROP_MAP = {
    tag: "tag_" + re.sub(r'[^a-z0-9]', '_', tag.lower().replace('-', '_')).strip('_')
    for tag in ALLOWED_TAGS
}


class BetterExperie_OT_PackAddon(bpy.types.Operator):
    bl_idname = "better_experie.pack_addon"
    bl_label = "一键打包"
    bl_description = "一键验证并生成可分发zip包"
    bl_options = {'REGISTER'}

    def execute(self, context):
        prefs = get_pref()
        plugin_path = prefs.output_path
        blender_path = bpy.app.binary_path

        if not os.path.isdir(plugin_path):
            self.report({'ERROR'}, f"插件路径不存在：{plugin_path}")
            return {'CANCELLED'}

        init_file = os.path.join(plugin_path, "__init__.py")
        manifest_file = os.path.join(plugin_path, "blender_manifest.toml")

        if not os.path.isfile(init_file):
            self.report({'ERROR'}, "__init__.py 文件不存在")
            return {'CANCELLED'}
        if not os.path.isfile(manifest_file):
            self.report({'ERROR'}, "blender_manifest.toml 文件不存在，请先生成")
            return {'CANCELLED'}

        def run_blender_command(cmd_desc, cmd_args):
            self.report({'INFO'}, f"正在执行：{cmd_desc}")
            try:
                result = subprocess.run(
                    cmd_args,
                    cwd=plugin_path,
                    capture_output=True,
                    text=True,
                    encoding='utf-8',
                    errors='ignore'
                )
                if result.stdout:
                    print(f"[命令输出] {result.stdout}")
                if result.stderr:
                    print(f"[命令错误] {result.stderr}")
                if result.returncode != 0:
                    error_msg = result.stderr or result.stdout or "未知错误"
                    self.report({'ERROR'}, f"{cmd_desc}失败：{error_msg[:200]}")
                    return False
                return True
            except Exception as e:
                self.report({'ERROR'}, f"{cmd_desc}异常：{str(e)}")
                return False

        validate_cmd = [blender_path, "--factory-startup", "--command", "extension", "validate"]
        if not run_blender_command("验证插件", validate_cmd):
            return {'CANCELLED'}

        build_cmd = [blender_path, "--factory-startup", "--command", "extension", "build"]
        if not run_blender_command("打包插件", build_cmd):
            return {'CANCELLED'}

        self.report({'INFO'}, "正在查找打包文件...")

        possible_dirs = [
            plugin_path,
            os.path.join(plugin_path, "dist"),
        ]

        generated_zip_path = None
        for check_dir in possible_dirs:
            if not os.path.isdir(check_dir):
                continue
            zip_files = []
            for f in os.listdir(check_dir):
                if f.endswith('.zip'):
                    f_path = os.path.join(check_dir, f)
                    zip_files.append((f_path, os.path.getmtime(f_path)))
            if zip_files:
                zip_files.sort(key=lambda x: x[1], reverse=True)
                generated_zip_path = zip_files[0][0]
                break

        if not generated_zip_path:
            self.report({'ERROR'}, "未找到生成的打包文件！请查看系统控制台了解详细错误")
            return {'CANCELLED'}

        final_path = generated_zip_path
        if plugin_path and os.path.isdir(plugin_path):
            target_path = os.path.join(plugin_path, os.path.basename(generated_zip_path))
            try:
                shutil.move(generated_zip_path, target_path)
                final_path = target_path
                self.report({'INFO'}, f"打包成功！文件已保存到：{final_path}")
            except Exception as e:
                self.report({'WARNING'}, f"打包成功，但移动文件失败（已保存在原位置）：{str(e)}")
                self.report({'INFO'}, f"文件位置：{generated_zip_path}")
        else:
            self.report({'INFO'}, f"打包成功！文件保存在：{final_path}")

        return {'FINISHED'}


class BetterExperie_OT_GenerateAddonManifest(bpy.types.Operator):
    bl_idname = "better_experie.generate_addon_manifest"
    bl_label = "生成 manifest"
    bl_description = "一键生成或编辑插件的 blender_manifest.toml 配置文件"
    bl_options = {'REGISTER'}

    addons_blender_version_min: bpy.props.StringProperty(name="最低版本", default="4.2.0",
        description="插件所支持的最低blender版本号")

    addons_id: bpy.props.StringProperty(name="插件ID", default="rara_test_tools",
        description="插件所用的ID，建议使用英文+下划线")

    addons_license: bpy.props.StringProperty(name="插件许可", default='["SPDX:GPL-3.0-or-later"]',
        description="插件所使用的开源许可证")

    addons_maintainer: bpy.props.StringProperty(name="维护人员", default="rara",
        description="在这里签署你的大名")

    addons_name: bpy.props.StringProperty(name="插件名称", default="Rara Test Tools",
        description="给插件取一个朗朗上口的名称吧")

    addons_schema_version: bpy.props.StringProperty(name="格式版本", default="1.0.0",
        description="使用 1.0.0即可，否则可能影响打包")

    addons_tagline: bpy.props.StringProperty(name="插件标语", default="插件简述",
        description="简短的插件介绍")

    addons_type: bpy.props.EnumProperty(
        name="插件类型",
        items=[('add-on', "插件", "附加组件类型"), ('theme', "主题", "附加主题类型")],
        default='add-on',
        description="一般使用默认插件类型即可")

    addons_version: bpy.props.StringProperty(name="插件版本", default="0.0.1",
        description="插件当前的版本号")

    addons_blender_version_max: bpy.props.StringProperty(name="最高版本", default="",
        description="插件所支持的最高blender版本号")

    addons_website: bpy.props.StringProperty(name="插件网站", default="https://space.bilibili.com/27284213",
        description="填写可以与你进行联系的网址")

    addons_copyright: bpy.props.StringProperty(name="版权所有",
        default=f'["{datetime.datetime.now().year} RARA"]',
        description="插件的版权信息")

    addons_tags: bpy.props.StringProperty(name="插件标签", default='["Object","3D View","Scene"]',
        description="插件的类型标签")

    show_tags_panel: bpy.props.BoolProperty(name="展开标签", default=False,
        description="展开/折叠标签白名单选择")

    tag_3d_view: bpy.props.BoolProperty(name="3D View", default=False)
    tag_add_curve: bpy.props.BoolProperty(name="Add Curve", default=False)
    tag_add_mesh: bpy.props.BoolProperty(name="Add Mesh", default=False)
    tag_all: bpy.props.BoolProperty(name="All", default=False)
    tag_animation: bpy.props.BoolProperty(name="Animation", default=False)
    tag_bake: bpy.props.BoolProperty(name="Bake", default=False)
    tag_camera: bpy.props.BoolProperty(name="Camera", default=False)
    tag_compositing: bpy.props.BoolProperty(name="Compositing", default=False)
    tag_development: bpy.props.BoolProperty(name="Development", default=False)
    tag_game_engine: bpy.props.BoolProperty(name="Game Engine", default=False)
    tag_geometry_nodes: bpy.props.BoolProperty(name="Geometry Nodes", default=False)
    tag_grease_pencil: bpy.props.BoolProperty(name="Grease Pencil", default=False)
    tag_import_export: bpy.props.BoolProperty(name="Import-Export", default=False)
    tag_lighting: bpy.props.BoolProperty(name="Lighting", default=False)
    tag_material: bpy.props.BoolProperty(name="Material", default=False)
    tag_mesh: bpy.props.BoolProperty(name="Mesh", default=False)
    tag_modeling: bpy.props.BoolProperty(name="Modeling", default=False)
    tag_node: bpy.props.BoolProperty(name="Node", default=False)
    tag_object: bpy.props.BoolProperty(name="Object", default=False)
    tag_paint: bpy.props.BoolProperty(name="Paint", default=False)
    tag_physics: bpy.props.BoolProperty(name="Physics", default=False)
    tag_pipeline: bpy.props.BoolProperty(name="Pipeline", default=False)
    tag_render: bpy.props.BoolProperty(name="Render", default=False)
    tag_rigging: bpy.props.BoolProperty(name="Rigging", default=False)
    tag_scene: bpy.props.BoolProperty(name="Scene", default=False)
    tag_sculpt: bpy.props.BoolProperty(name="Sculpt", default=False)
    tag_sequencer: bpy.props.BoolProperty(name="Sequencer", default=False)
    tag_system: bpy.props.BoolProperty(name="System", default=False)
    tag_text_editor: bpy.props.BoolProperty(name="Text Editor", default=False)
    tag_tracking: bpy.props.BoolProperty(name="Tracking", default=False)
    tag_uv: bpy.props.BoolProperty(name="UV", default=False)
    tag_user_interface: bpy.props.BoolProperty(name="User Interface", default=False)

    addons_platforms: bpy.props.StringProperty(name="系统平台", default="",
        description="留空表示全平台支持")

    addons_wheels: bpy.props.StringProperty(name="插件轮子", default="",
        description="")

    permission_files: bpy.props.StringProperty(name="文件", default="",
        description="解释为何需要文件系统访问权限（≤64字，不以标点结尾）")
    permission_network: bpy.props.StringProperty(name="网络", default="",
        description="解释为何需要网络访问权限（≤64字，不以标点结尾）")
    permission_clipboard: bpy.props.StringProperty(name="剪贴板", default="",
        description="解释为何需要剪贴板访问权限（≤64字，不以标点结尾）")
    permission_camera: bpy.props.StringProperty(name="摄像头", default="",
        description="解释为何需要摄像头访问权限（≤64字，不以标点结尾）")
    permission_microphone: bpy.props.StringProperty(name="麦克风", default="",
        description="解释为何需要麦克风访问权限（≤64字，不以标点结尾）")

    build_paths_exclude_pattern: bpy.props.StringProperty(
        name="排除模式",
        default='["__pycache__/", ".git", "*.zip"]',
        description="打包时排除的文件模式（gitignore格式）")
    build_paths: bpy.props.StringProperty(
        name="包含路径",
        default="",
        description="打包时包含的相对路径列表（与排除模式互斥）")

    show_optional: bpy.props.BoolProperty(name="显示附加项", default=False,
        description="展开完整的注册信息设置项")

    manifest_data = [
        ("schema_version", "addons_schema_version", "REQUIRED"),
        ("blender_version_min", "addons_blender_version_min", "REQUIRED"),
        ("blender_version_max", "addons_blender_version_max", "OPTIONAL"),
        ("version", "addons_version", "REQUIRED"),
        ("id", "addons_id", "REQUIRED"),
        ("name", "addons_name", "REQUIRED"),
        ("tagline", "addons_tagline", "REQUIRED"),
        ("license", "addons_license", "REQUIRED"),
        ("maintainer", "addons_maintainer", "REQUIRED"),
        ("type", "addons_type", "REQUIRED"),
        ("website", "addons_website", "OPTIONAL"),
        ("copyright", "addons_copyright", "OPTIONAL"),
        ("tags", "addons_tags", "OPTIONAL"),
        ("platforms", "addons_platforms", "OPTIONAL"),
        ("wheels", "addons_wheels", "OPTIONAL"),
    ]
    manifest_list = ["tags", "license", "platforms", "wheels", "copyright"]

    def _sync_bools_to_tags(self):
        selected = []
        for tag in sorted(ALLOWED_TAGS):
            prop_name = TAG_PROP_MAP[tag]
            if getattr(self, prop_name, False):
                selected.append(tag)
        self.addons_tags = json.dumps(selected, ensure_ascii=False)

    def _sync_tags_to_bools(self, context):
        try:
            tags = json.loads(self.addons_tags.replace("'", '"'))
        except Exception:
            tags = []
        if not isinstance(tags, list):
            tags = []
        for prop_name in TAG_PROP_MAP.values():
            try:
                setattr(self, prop_name, False)
            except AttributeError:
                pass
        for tag in tags:
            if tag in TAG_PROP_MAP:
                try:
                    setattr(self, TAG_PROP_MAP[tag], True)
                except AttributeError:
                    pass

    def _parse_manifest_toml(self, plugin_path):
        manifest_path = os.path.join(plugin_path, "blender_manifest.toml")
        if not os.path.exists(manifest_path):
            return None
        data = {}
        try:
            import tomllib
            with open(manifest_path, "rb") as f:
                data = tomllib.load(f)
        except ImportError:
            try:
                with open(manifest_path, "r", encoding="utf-8") as f:
                    content = f.read()
                for match in re.finditer(r'^([a-zA-Z0-9_]+)\s*=\s*(.+)$', content, re.MULTILINE):
                    key = match.group(1).strip()
                    val = match.group(2).strip()
                    if val.startswith('"') and val.endswith('"'):
                        val = val[1:-1]
                    data[key] = val
            except Exception as e:
                self.report({'WARNING'}, f"正则解析 TOML 失败: {str(e)}")
                return None
        except Exception as e:
            self.report({'WARNING'}, f"读取 TOML 失败: {str(e)}")
            return None
        return data

    def _parse_bl_info(self, plugin_path):
        init_path = os.path.join(plugin_path, "__init__.py")
        if not os.path.exists(init_path):
            self.report({'WARNING'}, f"未找到插件文件：{init_path}")
            return None
        encodings = ['utf-8-sig', 'utf-8', 'gbk', 'latin-1']
        content = None
        for enc in encodings:
            try:
                with open(init_path, 'r', encoding=enc) as f:
                    content = f.read()
                break
            except UnicodeDecodeError:
                continue
            except Exception as e:
                self.report({'WARNING'}, f"读取文件失败（{enc}）：{str(e)}")
                return None
        if content is None:
            self.report({'WARNING'}, "无法解析文件编码")
            return None
        try:
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name) and target.id == "bl_info":
                            if isinstance(node.value, ast.Dict):
                                return ast.literal_eval(node.value)
        except SyntaxError as e:
            self.report({'WARNING'}, f"解析代码语法错误：第{e.lineno}行 - {e.msg}")
            return None
        except Exception as e:
            self.report({'WARNING'}, f"解析bl_info失败：{str(e)}")
            return None
        return None

    def _auto_fill_props(self, context):
        prefs = get_pref()
        plugin_path = prefs.output_path

        manifest_data_dict = self._parse_manifest_toml(plugin_path)
        if manifest_data_dict:
            self.report({'INFO'}, "检测到 blender_manifest.toml，优先使用其配置")
            for key, name, type_ in self.manifest_data:
                if key in manifest_data_dict:
                    val = manifest_data_dict[key]
                    if isinstance(val, (list, dict)):
                        setattr(self, name, json.dumps(val, ensure_ascii=False))
                    else:
                        setattr(self, name, str(val))
            if "permissions" in manifest_data_dict and isinstance(manifest_data_dict["permissions"], dict):
                perms = manifest_data_dict["permissions"]
                for key in ["files", "network", "clipboard", "camera", "microphone"]:
                    if key in perms:
                        setattr(self, f"permission_{key}", str(perms[key]))
            if "build" in manifest_data_dict and isinstance(manifest_data_dict["build"], dict):
                build = manifest_data_dict["build"]
                if "paths_exclude_pattern" in build:
                    val = build["paths_exclude_pattern"]
                    if isinstance(val, list):
                        setattr(self, "build_paths_exclude_pattern", json.dumps(val, ensure_ascii=False))
                    else:
                        setattr(self, "build_paths_exclude_pattern", str(val))
                if "paths" in build:
                    val = build["paths"]
                    if isinstance(val, list):
                        setattr(self, "build_paths", json.dumps(val, ensure_ascii=False))
                    else:
                        setattr(self, "build_paths", str(val))
            return

        bl_info = self._parse_bl_info(plugin_path)
        if not bl_info:
            self.report({'INFO'}, "未检测到bl_info，使用默认值（可手动修改）")
            return

        if bl_info.get("name"):
            self.addons_name = bl_info["name"]

        folder_name = os.path.basename(os.path.normpath(plugin_path))
        clean_id = folder_name.lower().replace(" ", "_")
        clean_id = re.sub(r'[^a-z0-9_]', '', clean_id)
        if clean_id:
            self.addons_id = clean_id

        if bl_info.get("version") and isinstance(bl_info["version"], tuple):
            self.addons_version = ".".join(map(str, bl_info["version"]))

        if bl_info.get("author"):
            self.addons_maintainer = bl_info["author"]

        if bl_info.get("blender") and isinstance(bl_info["blender"], tuple):
            self.addons_blender_version_min = ".".join(map(str, bl_info["blender"]))

        author = bl_info.get("author", "Unknown")
        current_year = datetime.datetime.now().year
        self.addons_copyright = f'["{current_year} {author}"]'

        if bl_info.get("description"):
            self.addons_tagline = bl_info["description"]
        elif bl_info.get("name"):
            self.addons_tagline = f"{bl_info['name']} - Blender插件"

    def execute(self, context):
        self._sync_bools_to_tags()
        prefs = get_pref()
        plugin_path = prefs.output_path
        manifest_path = os.path.join(plugin_path, "blender_manifest.toml")

        try:
            with open(manifest_path, 'w', encoding='utf-8') as f:
                for manifest in self.manifest_data:
                    key, name, type_ = manifest
                    value = getattr(self, name, "")
                    if type_ == "OPTIONAL" and value == "":
                        continue
                    if key in self.manifest_list:
                        f.write(f'{key} = {value}\n')
                    else:
                        f.write(f'{key} = "{value}"\n')

                perm_data = [
                    ("files", "permission_files"),
                    ("network", "permission_network"),
                    ("clipboard", "permission_clipboard"),
                    ("camera", "permission_camera"),
                    ("microphone", "permission_microphone"),
                ]
                perm_lines = []
                for perm_key, prop_name in perm_data:
                    val = getattr(self, prop_name, "").strip()
                    if val:
                        perm_lines.append(f'{perm_key} = "{val}"')
                if perm_lines:
                    f.write("\n[permissions]\n")
                    for line in perm_lines:
                        f.write(line + "\n")

                build_exclude = getattr(self, "build_paths_exclude_pattern", "").strip()
                build_paths_val = getattr(self, "build_paths", "").strip()
                if build_paths_val or build_exclude:
                    f.write("\n[build]\n")
                    if build_paths_val:
                        f.write(f'paths = {build_paths_val}\n')
                    elif build_exclude:
                        f.write(f'paths_exclude_pattern = {build_exclude}\n')

            self.report({'INFO'}, f"blender_manifest已生成到 {manifest_path}")
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, f"生成blender_manifest失败: {str(e)}")
            return {'CANCELLED'}

    def invoke(self, context, event):
        self._auto_fill_props(context)
        self._sync_tags_to_bools(context)
        return context.window_manager.invoke_props_dialog(self, width=600)

    def draw(self, context):
        layout = self.layout
        prefs = get_pref()
        layout.label(text=f"路径: {prefs.output_path or '（请在偏好设置中设置）'}")
        row = layout.row()
        row.prop(self, "show_optional")
        op = row.operator("wm.url_open", text="", icon='QUESTION')
        op.url = "https://docs.blender.org/manual/en/latest/advanced/extensions/getting_started.html"

        layout.separator()
        errors = []

        if not re.match(r'^[a-zA-Z0-9_]+$', self.addons_id):
            errors.append("插件ID仅限英文大小写、数字和下划线")

        tagline = self.addons_tagline.strip()
        if len(tagline) > 64:
            errors.append(f"标语过长 ({len(tagline)}/64)")
        if tagline and tagline[-1] in ".,;:!?。，；：！？":
            errors.append("标语绝对不能以标点符号结尾")

        if self.addons_schema_version != "1.0.0":
            errors.append("格式版本(schema_version)必须为 1.0.0")

        ver_parts = self.addons_version.split('.')
        if len(ver_parts) < 3 or not all(p.isdigit() for p in ver_parts):
            errors.append("插件版本必须遵循语义化(如 0.0.1)")

        min_v_str = self.addons_blender_version_min.split('.')
        current_version = bpy.app.version
        try:
            user_v_tuple = tuple(int(x) for x in min_v_str if x.isdigit())
            while len(user_v_tuple) < 3:
                user_v_tuple += (0,)
            if user_v_tuple > current_version:
                current_v_str = ".".join(map(str, current_version))
                errors.append(f"最低支持版本不能高于当前环境版本 ({current_v_str})")
        except Exception:
            errors.append("最低支持版本格式错误 (应为如 5.2.0)")

        if self.addons_copyright and self.show_optional:
            if not re.search(r'\d{4}', self.addons_copyright):
                errors.append("版权(copyright)必须包含年份")

        if self.addons_tags and self.show_optional:
            input_tags = re.findall(r'["\']([^"\']+)["\']', self.addons_tags)
            invalid_tags = [tag for tag in input_tags if tag not in ALLOWED_TAGS]
            if invalid_tags:
                errors.append(f"包含非法标签: {', '.join(invalid_tags)}")

        if getattr(self, "addons_wheels", "") and self.show_optional:
            wheels_str = self.addons_wheels.strip()
            if not (wheels_str.startswith('[') and wheels_str.endswith(']')):
                errors.append("wheels 必须是列表格式")
            else:
                wheel_items = re.findall(r'["\']([^"\']+)["\']', wheels_str)
                invalid_wheels = [w for w in wheel_items if not w.endswith('.whl')]
                if invalid_wheels:
                    errors.append(f"wheel 文件必须以 .whl 结尾: {', '.join(invalid_wheels)}")

        if self.show_optional:
            perm_props = [
                ("permission_files", "文件权限"),
                ("permission_network", "网络权限"),
                ("permission_clipboard", "剪贴板权限"),
                ("permission_camera", "摄像头权限"),
                ("permission_microphone", "麦克风权限"),
            ]
            for prop_name, label in perm_props:
                val = getattr(self, prop_name, "").strip()
                if val:
                    if len(val) > 64:
                        errors.append(f"{label}说明过长 ({len(val)}/64)")
                    if val[-1] in ".,;:!?。，；：！？":
                        errors.append(f"{label}说明不能以标点结尾")

        if self.show_optional:
            build_paths_val = getattr(self, "build_paths", "").strip()
            build_exclude_val = getattr(self, "build_paths_exclude_pattern", "").strip()
            if build_paths_val and build_exclude_val:
                errors.append("包含路径(paths)与排除模式(paths_exclude_pattern)互斥")

        if self.addons_type != 'add-on':
            errors.append("本工具暂时仅支持打包插件")

        if errors:
            box = layout.box()
            box.alert = True
            for err in errors:
                box.label(text=f"错误：{err}！", icon='ERROR')

        layout.separator()

        for manifest in self.manifest_data:
            key, name, type_ = manifest
            if name == "addons_tags":
                if self.show_optional:
                    row = layout.row()
                    row.prop(self, "show_tags_panel", icon='TRIA_DOWN' if self.show_tags_panel else 'TRIA_RIGHT',
                             emboss=False, text="插件标签")
                    selected_count = 0
                    if self.addons_tags:
                        try:
                            tags_list = json.loads(self.addons_tags.replace("'", '"'))
                            if isinstance(tags_list, list):
                                selected_count = len(tags_list)
                        except Exception:
                            pass
                    row.label(text=f"已选 {selected_count} 个" if selected_count else "未选择")
                    if self.show_tags_panel:
                        box = layout.box()
                        flow = box.grid_flow(columns=3, even_columns=True, align=True)
                        for tag in sorted(ALLOWED_TAGS):
                            flow.prop(self, TAG_PROP_MAP[tag])
                continue
            if self.show_optional:
                layout.prop(self, name)
            elif type_ == "REQUIRED":
                layout.prop(self, name)

        if self.show_optional:
            layout.separator()
            layout.label(text="[permissions] 插件权限声明:", icon='LOCKED')
            layout.prop(self, "permission_files")
            layout.prop(self, "permission_network")
            layout.prop(self, "permission_clipboard")
            layout.prop(self, "permission_camera")
            layout.prop(self, "permission_microphone")

            layout.separator()
            layout.label(text="[build] 打包高级选项:", icon='PACKAGE')
            layout.prop(self, "build_paths_exclude_pattern")
            layout.prop(self, "build_paths")


classes = (
    BetterExperie_OT_PackAddon,
    BetterExperie_OT_GenerateAddonManifest,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
