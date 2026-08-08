# 文件工具集

import os
import re
import bpy
import tempfile


def get_filebrowser_directory(context):
    try:
        d = context.space_data.params.directory
        return d.decode() if isinstance(d, bytes) else str(d)
    except Exception:
        return ""


class BetterExperie_OT_BatchRename(bpy.types.Operator):
    bl_idname = "better_experie.batch_rename"
    bl_label = "批量重命名"
    bl_description = "批量重命名指定文件夹内的文件，支持查找替换、前后缀和编号模式"
    bl_options = {'REGISTER', 'UNDO'}

    directory: bpy.props.StringProperty(options={'HIDDEN'})

    mode: bpy.props.EnumProperty(
        name="模式",
        items=[
            ('FIND_REPLACE', "查找替换", "查找并替换文件名中的文本"),
            ('PREFIX_SUFFIX', "前后缀", "在文件名前/后添加文本"),
            ('NUMBERING', "编号", "统一编号重命名"),
        ],
        default='FIND_REPLACE'
    )

    find: bpy.props.StringProperty(name="查找", default="")
    replace: bpy.props.StringProperty(name="替换为", default="")
    use_regex: bpy.props.BoolProperty(name="使用正则", default=False)
    case_sensitive: bpy.props.BoolProperty(name="区分大小写", default=False)

    prefix: bpy.props.StringProperty(name="前缀", default="")
    suffix: bpy.props.StringProperty(name="后缀", default="")

    base_name: bpy.props.StringProperty(name="基础名称", default="file")
    start_number: bpy.props.IntProperty(name="起始编号", default=1, min=0)
    padding: bpy.props.IntProperty(name="编号位数", default=3, min=1, max=6)
    keep_extension: bpy.props.BoolProperty(name="保留扩展名", default=True)

    filter_pattern: bpy.props.StringProperty(name="过滤", default="*", description="仅重命名匹配的文件，如 *.png")

    @classmethod
    def poll(cls, context):
        return context.space_data.type == 'FILE_BROWSER'

    def invoke(self, context, event):
        self.directory = get_filebrowser_directory(context)
        if not self.directory or not os.path.isdir(self.directory):
            self.report({'ERROR'}, "无法获取有效的文件夹路径")
            return {'CANCELLED'}
        return context.window_manager.invoke_props_dialog(self, width=520)

    def draw(self, context):
        layout = self.layout
        layout.label(text=f"目录: {self.directory}")

        layout.prop(self, "filter_pattern")
        layout.separator()
        layout.prop(self, "mode", expand=True)

        if self.mode == 'FIND_REPLACE':
            col = layout.column(align=True)
            col.prop(self, "find")
            col.prop(self, "replace")
            row = layout.row(align=True)
            row.prop(self, "use_regex")
            row.prop(self, "case_sensitive")
        elif self.mode == 'PREFIX_SUFFIX':
            col = layout.column(align=True)
            col.prop(self, "prefix")
            col.prop(self, "suffix")
        elif self.mode == 'NUMBERING':
            col = layout.column(align=True)
            col.prop(self, "base_name")
            row = layout.row(align=True)
            row.prop(self, "start_number")
            row.prop(self, "padding")
            layout.prop(self, "keep_extension")

        layout.separator()
        layout.label(text=f"匹配文件: {len(self.get_target_files())} 个")

    def get_target_files(self):
        try:
            files = os.listdir(self.directory)
        except Exception:
            return []
        files = [f for f in files if os.path.isfile(os.path.join(self.directory, f))]
        if self.filter_pattern != "*":
            import fnmatch
            files = [f for f in files if fnmatch.fnmatch(f, self.filter_pattern)]
        return sorted(files)

    def compute_new_name(self, filename):
        name, ext = os.path.splitext(filename)

        if self.mode == 'FIND_REPLACE':
            if self.use_regex:
                flags = 0 if self.case_sensitive else re.IGNORECASE
                try:
                    new_name = re.sub(self.find, self.replace, filename, flags=flags)
                except re.error:
                    return filename
            else:
                if self.case_sensitive:
                    new_name = filename.replace(self.find, self.replace)
                else:
                    pattern = re.compile(re.escape(self.find), re.IGNORECASE)
                    new_name = pattern.sub(self.replace, filename)
            return new_name

        elif self.mode == 'PREFIX_SUFFIX':
            return self.prefix + filename + self.suffix

        elif self.mode == 'NUMBERING':
            if self.keep_extension:
                new_name = f"{self.base_name}_{str(self.start_number).zfill(self.padding)}{ext}"
            else:
                new_name = f"{self.base_name}_{str(self.start_number).zfill(self.padding)}"
            return new_name

        return filename

    def execute(self, context):
        files = self.get_target_files()
        if not files:
            self.report({'WARNING'}, "没有找到匹配的文件")
            return {'CANCELLED'}

        renamed = 0
        errors = []
        counter = self.start_number

        for f in files:
            old_path = os.path.join(self.directory, f)
            new_name = self.compute_new_name(f)

            if self.mode == 'NUMBERING':
                name, ext = os.path.splitext(f)
                if self.keep_extension:
                    new_name = f"{self.base_name}_{str(counter).zfill(self.padding)}{ext}"
                else:
                    new_name = f"{self.base_name}_{str(counter).zfill(self.padding)}"

            new_path = os.path.join(self.directory, new_name)

            if old_path == new_path:
                counter += 1
                continue

            if os.path.exists(new_path):
                errors.append(f"{f} -> {new_name}（目标已存在）")
                counter += 1
                continue

            try:
                os.rename(old_path, new_path)
                renamed += 1
            except Exception as e:
                errors.append(f"{f}（{str(e)}）")

            counter += 1

        msg = f"已重命名 {renamed} 个文件"
        if errors:
            msg += f"，{len(errors)} 个失败"
        self.report({'INFO'}, msg)
        return {'FINISHED'}


class BetterExperie_OT_GenerateFileTree(bpy.types.Operator):
    bl_idname = "better_experie.generate_file_tree"
    bl_label = "生成文件树"
    bl_description = "生成所选文件夹的完整文件树结构并在文本编辑器中打开"
    bl_options = {'REGISTER', 'UNDO'}

    max_depth: bpy.props.IntProperty(name="最大深度", default=10, min=1, max=999)
    show_hidden: bpy.props.BoolProperty(name="显示隐藏文件", default=False)
    dirs_only: bpy.props.BoolProperty(name="仅目录", default=True)

    @classmethod
    def poll(cls, context):
        return context.space_data.type == 'FILE_BROWSER'

    def invoke(self, context, event):
        directory = get_filebrowser_directory(context)
        if not directory or not os.path.isdir(directory):
            self.report({'ERROR'}, "无法获取有效的文件夹路径")
            return {'CANCELLED'}
        return context.window_manager.invoke_props_dialog(self, width=360)

    def draw(self, context):
        layout = self.layout
        row = layout.row(align=True)
        row.prop(self, "max_depth")
        row.prop(self, "show_hidden")
        row.prop(self, "dirs_only")

    def build_tree(self, path, prefix="", depth=0):
        if depth >= self.max_depth:
            return ""

        try:
            entries = sorted(os.listdir(path))
        except PermissionError:
            return f"{prefix}[拒绝访问]\n"

        lines = ""
        for i, entry in enumerate(entries):
            if not self.show_hidden and entry.startswith('.'):
                continue

            full = os.path.join(path, entry)
            is_last = (i == len(entries) - 1)
            connector = "└── " if is_last else "├── "
            next_prefix = "    " if is_last else "│   "

            if os.path.isdir(full):
                lines += f"{prefix}{connector}{entry}/\n"
                lines += self.build_tree(full, prefix + next_prefix, depth + 1)
            elif os.path.isfile(full) and not self.dirs_only:
                size = os.path.getsize(full)
                if size < 1024:
                    size_str = f"{size} B"
                elif size < 1024 * 1024:
                    size_str = f"{size / 1024:.1f} KB"
                else:
                    size_str = f"{size / (1024 * 1024):.1f} MB"
                lines += f"{prefix}{connector}{entry}  ({size_str})\n"

        return lines

    def execute(self, context):
        directory = get_filebrowser_directory(context)
        folder_name = os.path.basename(directory.rstrip(os.sep))

        tree = f"{folder_name}/\n"
        tree += self.build_tree(directory)

        line_count = tree.count('\n')
        tree += f"\n{'─' * 40}\n共 {line_count} 行"

        tmp_path = os.path.join(tempfile.gettempdir(), "better_experie_file_tree.txt")
        with open(tmp_path, 'w', encoding='utf-8') as f:
            f.write(tree)

        bpy.ops.better_experie.show_manual(file_path=tmp_path, data=f"文件树 - {folder_name}")
        return {'FINISHED'}


classes = (
    BetterExperie_OT_BatchRename,
    BetterExperie_OT_GenerateFileTree,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
