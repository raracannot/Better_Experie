# 文本处理工具箱

import re
import bpy
import datetime 

# 辅助函数：获取当前活动的文本数据块
def get_active_text(context):
    """
    获取当前Blender上下文中活动的文本数据块。
    仅当当前区域是文本编辑器且有文本数据块时返回。
    """
    if context.area.type == 'TEXT_EDITOR' and context.area.spaces.active and context.area.spaces.active.text:
        return context.area.spaces.active.text
    return None

def get_global_cursor_index(text_data, lines_list):
    """
    计算当前光标的全局字符索引。
    text_data: 当前活动的文本数据块。
    lines_list: 文本按行分割的列表 (使用 keepends=True)。
    """
    global_idx = 0
    for i in range(text_data.current_line_index):
        if i < len(lines_list):
            global_idx += len(lines_list[i])
    global_idx += text_data.current_character
    return global_idx

# 辅助函数：将全局字符索引转换为行索引和行内字符索引
def global_index_to_line_char(global_idx, lines_list):
    """
    将一个全局字符索引转换为 (line_index, character_index)。
    global_idx: 从文本开头算起的字符索引。
    lines_list: 文本按行分割的列表 (使用 keepends=True)。
    """
    current_idx = 0
    for line_idx, line in enumerate(lines_list):
        if global_idx <= current_idx + len(line):
            return line_idx, global_idx - current_idx
        current_idx += len(line)

    # 如果 global_idx 超出文本末尾，则返回文本的最后位置
    if len(lines_list) == 0:
        return 0, 0
    return len(lines_list) - 1, len(lines_list[-1])


# 辅助函数：获取文本内容和选区信息
def get_text_and_selection_info(text_data):
    """
    获取完整的文本内容，并计算选区的全局字符起始和结束索引。
    同时返回原始光标和选区结束位置的*索引*，用于恢复。
    返回：(完整文本, lines_list, 选区起始全局索引, 选区结束全局索引, 是否有选区, 原始光标行索引, 原始光标字符, 原始选区结束行索引, 原始选区结束字符)
    """
    full_text = text_data.as_string()

    # 保存原始光标和选区结束位置的索引
    original_cursor_line_idx = text_data.current_line_index
    original_cursor_char = text_data.current_character
    original_select_end_line_idx = text_data.select_end_line_index
    original_select_end_char = text_data.select_end_character

    # 判断是否存在实际的选区
    is_selected = not (original_cursor_line_idx == original_select_end_line_idx and original_cursor_char == original_select_end_char)

    lines = full_text.splitlines(keepends=True) # 保留换行符以便正确计算每行的长度

    # Helper to convert line/char to global index
    def _get_global_index_from_line_char(line_idx, char_idx, lines_list):
        global_idx = 0
        for i in range(line_idx):
            if i < len(lines_list):
                global_idx += len(lines_list[i])
        global_idx += char_idx
        return global_idx

    if not is_selected:
        return full_text, lines, 0, len(full_text), False, \
               original_cursor_line_idx, original_cursor_char, \
               original_select_end_line_idx, original_select_end_char

    cursor_global_index = _get_global_index_from_line_char(original_cursor_line_idx, original_cursor_char, lines)
    select_end_global_index = _get_global_index_from_line_char(original_select_end_line_idx, original_select_end_char, lines)

    actual_start_index = min(cursor_global_index, select_end_global_index)
    actual_end_index = max(cursor_global_index, select_end_global_index)

    return full_text, lines, actual_start_index, actual_end_index, True, \
           original_cursor_line_idx, original_cursor_char, \
           original_select_end_line_idx, original_select_end_char


####################################################################################################
####################################################################################################
class BetterExperie_OT_TextRemoveTrailingSpace(bpy.types.Operator):
    bl_idname = "better_experie.text_remove_trailing_space"
    bl_label = "去除行尾空白"
    bl_description = "移除当前文本中所有行的行尾空白字符"

    @classmethod
    def poll(cls, context):
        return get_active_text(context) is not None

    def execute(self, context):
        text_data = get_active_text(context)
        if not text_data:
            self.report({'WARNING'}, "没有活动的文本数据块")
            return {'CANCELLED'}

        full_text, original_lines_list, start_global_idx, end_global_idx, is_selected, \
            original_cursor_line_idx, original_cursor_char, \
            original_select_end_line_idx, original_select_end_char = get_text_and_selection_info(text_data)

        new_text = ""
        new_cursor_line_idx = original_cursor_line_idx
        new_cursor_char = original_cursor_char
        new_select_end_line_idx = original_select_end_line_idx
        new_select_end_char = original_select_end_char

        if is_selected:
            # 只处理选中的部分
            before_selection = full_text[:start_global_idx]
            selected_text = full_text[start_global_idx:end_global_idx]
            after_selection = full_text[end_global_idx:]

            selected_lines = selected_text.splitlines(keepends=True)
            modified_selected_lines = []
            for line in selected_lines:
                if line.endswith('\n'):
                    modified_selected_lines.append(line.rstrip() + '\n')
                else:
                    modified_selected_lines.append(line.rstrip())
            processed_selected_text = "".join(modified_selected_lines)

            new_text = before_selection + processed_selected_text + after_selection

            # 计算新选区的全局结束索引
            length_diff = len(processed_selected_text) - len(selected_text)
            new_end_global_idx_for_selection = start_global_idx + len(processed_selected_text)

            # 将新的全局索引转换回行/字符索引
            new_full_lines = new_text.splitlines(keepends=True)

            new_selection_start_line_idx, new_selection_start_char = global_index_to_line_char(start_global_idx, new_full_lines)
            new_selection_end_line_idx, new_selection_end_char = global_index_to_line_char(new_end_global_idx_for_selection, new_full_lines)

            # 设置光标到新选区的末尾，并选中整个新选区
            new_cursor_line_idx = new_selection_end_line_idx
            new_cursor_char = new_selection_end_char
            new_select_end_line_idx = new_selection_start_line_idx # 选区锚点在开始
            new_select_end_char = new_selection_start_char

        else:
            # 处理整个文本
            lines = full_text.splitlines(keepends=True)
            modified_lines = []
            for line in lines:
                if line.endswith('\n'):
                    modified_lines.append(line.rstrip() + '\n')
                else:
                    modified_lines.append(line.rstrip())
            new_text = "".join(modified_lines)

            # 如果没有选区，光标和选区锚点恢复到原始位置
            new_cursor_line_idx = original_cursor_line_idx
            new_cursor_char = original_cursor_char
            new_select_end_line_idx = original_select_end_line_idx
            new_select_end_char = original_select_end_char


        text_data.clear() # 清空当前文本
        text_data.write(new_text) # 写入新文本

        # 恢复光标和选区位置
        text_data.cursor_set(line=new_cursor_line_idx, character=new_cursor_char)
        text_data.select_set(line_start=new_cursor_line_idx, char_start=new_cursor_char,
                             line_end=new_select_end_line_idx, char_end=new_select_end_char)

        self.report({'INFO'}, "已去除行尾空白")
        return {'FINISHED'}


class BetterExperie_OT_TextRemoveEmptyLines(bpy.types.Operator):
    bl_idname = "better_experie.text_remove_empty_lines"
    bl_label = "移除空白行"
    bl_description = "移除当前文本中所有空白行（包括只包含空格或制表符的行）"

    @classmethod
    def poll(cls, context):
        return get_active_text(context) is not None

    def execute(self, context):
        text_data = get_active_text(context)
        if not text_data:
            self.report({'WARNING'}, "没有活动的文本数据块")
            return {'CANCELLED'}

        full_text, original_lines_list, start_global_idx, end_global_idx, is_selected, \
            original_cursor_line_idx, original_cursor_char, \
            original_select_end_line_idx, original_select_end_char = get_text_and_selection_info(text_data)

        new_text = ""
        new_cursor_line_idx = original_cursor_line_idx
        new_cursor_char = original_cursor_char
        new_select_end_line_idx = original_select_end_line_idx
        new_select_end_char = original_select_end_char

        if is_selected:
            # 只处理选中的部分
            before_selection = full_text[:start_global_idx]
            selected_text = full_text[start_global_idx:end_global_idx]
            after_selection = full_text[end_global_idx:]

            selected_lines = selected_text.splitlines(keepends=True)
            modified_selected_lines = []
            for line in selected_lines:
                if line.strip(): # 如果行在去除空白后不为空，则保留
                    modified_selected_lines.append(line)
            processed_selected_text = "".join(modified_selected_lines)

            new_text = before_selection + processed_selected_text + after_selection

            # 计算新选区的全局结束索引
            length_diff = len(processed_selected_text) - len(selected_text)
            new_end_global_idx_for_selection = start_global_idx + len(processed_selected_text)

            # 将新的全局索引转换回行/字符索引
            new_full_lines = new_text.splitlines(keepends=True)

            new_selection_start_line_idx, new_selection_start_char = global_index_to_line_char(start_global_idx, new_full_lines)
            new_selection_end_line_idx, new_selection_end_char = global_index_to_line_char(new_end_global_idx_for_selection, new_full_lines)

            # 设置光标到新选区的末尾，并选中整个新选区
            new_cursor_line_idx = new_selection_end_line_idx
            new_cursor_char = new_selection_end_char
            new_select_end_line_idx = new_selection_start_line_idx
            new_select_end_char = new_selection_start_char

        else:
            # 处理整个文本
            lines = full_text.splitlines(keepends=True)
            modified_lines = []
            for line in lines:
                if line.strip():
                    modified_lines.append(line)
            new_text = "".join(modified_lines)

            # 如果没有选区，光标和选区锚点恢复到原始位置
            new_cursor_line_idx = original_cursor_line_idx
            new_cursor_char = original_cursor_char
            new_select_end_line_idx = original_select_end_line_idx
            new_select_end_char = original_select_end_char


        text_data.clear()
        text_data.write(new_text)

        # 恢复光标和选区位置
        text_data.cursor_set(line=new_cursor_line_idx, character=new_cursor_char)
        text_data.select_set(line_start=new_cursor_line_idx, char_start=new_cursor_char,
                             line_end=new_select_end_line_idx, char_end=new_select_end_char)

        self.report({'INFO'}, "已移除空白行")
        return {'FINISHED'}


class BetterExperie_OT_TextSortSelectedLines(bpy.types.Operator):
    bl_idname = "better_experie.text_sort_selected_lines"
    bl_label = "选区内行排序"
    bl_description = "对选中的行进行字母顺序排序（升序）。如果没有选区，则对整个文本进行排序。"

    @classmethod
    def poll(cls, context):
        return get_active_text(context) is not None

    def execute(self, context):
        text_data = get_active_text(context)
        if not text_data:
            self.report({'WARNING'}, "没有活动的文本数据块")
            return {'CANCELLED'}

        full_text, original_lines_list, start_global_idx, end_global_idx, is_selected, \
            original_cursor_line_idx, original_cursor_char, \
            original_select_end_line_idx, original_select_end_char = get_text_and_selection_info(text_data)

        new_text = ""
        if is_selected:
            # 获取选区的起始和结束行索引
            start_line_idx, _ = global_index_to_line_char(start_global_idx, original_lines_list)
            end_line_idx, end_char_in_line = global_index_to_line_char(end_global_idx, original_lines_list)

            # 如果选区结束在某行的开头，那么这一行不应该被包含在选区内
            # 除非它是选区的唯一一行或者选区只包含这一行的一部分
            # 这里简化处理：如果选区结束字符是0且不是选区开始行，则结束行索引减1
            if end_char_in_line == 0 and end_line_idx > start_line_idx:
                end_line_idx -= 1

            # 确保end_line_idx不会超出列表范围
            end_line_idx = min(end_line_idx, len(original_lines_list) - 1)

            before_selection_lines = original_lines_list[:start_line_idx]
            selected_lines_raw = original_lines_list[start_line_idx : end_line_idx + 1]
            after_selection_lines = original_lines_list[end_line_idx + 1:]

            # 对选中的行进行排序
            sorted_selected_lines = sorted(selected_lines_raw)

            new_full_lines = before_selection_lines + sorted_selected_lines + after_selection_lines
            new_text = "".join(new_full_lines)

            # 恢复选区：将整个排序后的区域重新选中
            # 计算新的全局索引
            new_start_global_idx = sum(len(line) for line in before_selection_lines)
            new_end_global_idx = new_start_global_idx + sum(len(line) for line in sorted_selected_lines)

            new_cursor_line_idx, new_cursor_char = global_index_to_line_char(new_end_global_idx, new_full_lines)
            new_select_end_line_idx, new_select_end_char = global_index_to_line_char(new_start_global_idx, new_full_lines)

        else:
            # 如果没有选区，对整个文本进行排序
            lines = full_text.splitlines(keepends=True)
            sorted_lines = sorted(lines)
            new_text = "".join(sorted_lines)

            # 没有选区时，光标和选区锚点恢复到原始位置
            new_cursor_line_idx = original_cursor_line_idx
            new_cursor_char = original_cursor_char
            new_select_end_line_idx = original_select_end_line_idx
            new_select_end_char = original_select_end_char

        text_data.clear()
        text_data.write(new_text)

        text_data.cursor_set(line=new_cursor_line_idx, character=new_cursor_char)
        text_data.select_set(line_start=new_cursor_line_idx, char_start=new_cursor_char,
                             line_end=new_select_end_line_idx, char_end=new_select_end_char)

        self.report({'INFO'}, "已对选区内的行进行排序")
        return {'FINISHED'}


####################################################################################################
####################################################################################################
class BetterExperie_OT_TextCapitalizationEditor(bpy.types.Operator):
    bl_idname = "better_experie.text_capitalization_editor"
    bl_label = "大小写转换"
    bl_description = "将选中的文本（或整个文本）进行大小写转换"

    text_capitalization: bpy.props.EnumProperty(
        items=[
            ('UPPER', "转换为大写", "将选中的文本（或整个文本）转换为大写"),
            ('LOWER', "转换为小写", "将选中的文本（或整个文本）转换为小写"),
            ('TITLE', "首字母大写", "将选中的文本（或整个文本）中每个单词的首字母转换为大写，其余字母转换为小写"),
            ('SWAPCASE', "大小写反转", "将选中的文本（或整个文本）中的大写字母转为小写，小写字母转为大写"),
        ],name="大小写转换模式",default='UPPER')

    @classmethod
    def poll(cls, context):
        return get_active_text(context) is not None

    def capitalization(self, edit_text):
        if self.text_capitalization == "UPPER":
            new_text = edit_text.upper()
        elif self.text_capitalization == "LOWER":
            new_text = edit_text.lower()
        elif self.text_capitalization == "TITLE":
            new_text = edit_text.title()
        elif self.text_capitalization == "SWAPCASE":
            new_text = edit_text.swapcase()
        else:
            new_text = edit_text.upper()
        return new_text

    def execute(self, context):
        text_data = get_active_text(context)
        if not text_data:
            self.report({'WARNING'}, "没有活动的文本数据块")
            return {'CANCELLED'}

        # 调用辅助函数获取信息，它会返回原始光标和选区结束位置的索引
        full_text, original_lines_list, start_index, end_index, is_selected, \
            original_cursor_line_idx, original_cursor_char, \
            original_select_end_line_idx, original_select_end_char = get_text_and_selection_info(text_data)

        if is_selected:
            # 如果有选区，只转换选中的部分
            selected_text = full_text[start_index:end_index]
            modified_selected_text = self.capitalization(selected_text)
            new_text = full_text[:start_index] + modified_selected_text + full_text[end_index:]
        else:
            # 如果没有选区，转换整个文本
            new_text = self.capitalization(full_text)

        text_data.clear()
        text_data.write(new_text)

        # 恢复光标和选区位置
        text_data.cursor_set(line=original_cursor_line_idx, character=original_cursor_char)
        text_data.select_set(line_start=original_cursor_line_idx, char_start=original_cursor_char,
                             line_end=original_select_end_line_idx, char_end=original_select_end_char)

        if self.text_capitalization == "UPPER":
            self.report({'INFO'}, "已将所选文本转换为大写")
        elif self.text_capitalization == "LOWER":
            self.report({'INFO'}, "已将所选文本转换为小写")
        elif self.text_capitalization == "TITLE":
            self.report({'INFO'}, "已将所选文本转换为首字母大写")
        elif self.text_capitalization == "SWAPCASE":
            self.report({'INFO'}, "已将所选文本转换为大小写反转")
        else:
            self.report({'INFO'}, "已将所选文本转换为大写")
        return {'FINISHED'}


class BetterExperie_OT_TextInsertDateTime(bpy.types.Operator):
    bl_idname = "better_experie.text_insert_datetime"
    bl_label = "插入日期/时间"
    bl_description = "在光标位置插入当前日期和时间"

    format_string: bpy.props.StringProperty(
        name="日期时间格式",
        description="用于格式化日期时间的字符串",
        default="%Y-%m-%d %H:%M:%S")

    @classmethod
    def poll(cls, context):
        return get_active_text(context) is not None

    def execute(self, context):
        text_data = get_active_text(context)
        if not text_data:
            self.report({'WARNING'}, "没有活动的文本数据块")
            return {'CANCELLED'}

        now = datetime.datetime.now()
        text_to_insert = now.strftime(self.format_string)

        full_text, original_lines_list, start_global_idx, end_global_idx, is_selected, \
            original_cursor_line_idx, original_cursor_char, \
            original_select_end_line_idx, original_select_end_char = get_text_and_selection_info(text_data)

        new_text = ""
        new_cursor_global_idx = 0

        if is_selected:
            new_text = full_text[:start_global_idx] + text_to_insert + full_text[end_global_idx:]
            new_cursor_global_idx = start_global_idx + len(text_to_insert)
        else:
            cursor_global_index = get_global_cursor_index(text_data, original_lines_list)
            new_text = full_text[:cursor_global_index] + text_to_insert + full_text[cursor_global_index:]
            new_cursor_global_idx = cursor_global_index + len(text_to_insert)

        text_data.clear()
        text_data.write(new_text)

        new_full_lines = new_text.splitlines(keepends=True)
        new_cursor_line_idx, new_cursor_char = global_index_to_line_char(new_cursor_global_idx, new_full_lines)

        text_data.cursor_set(line=new_cursor_line_idx, character=new_cursor_char)
        text_data.select_set(line_start=new_cursor_line_idx, char_start=new_cursor_char,
                             line_end=new_cursor_line_idx, char_end=new_cursor_char) # 清除选区

        self.report({'INFO'}, f"已插入日期/时间: {text_to_insert}")
        return {'FINISHED'}


class BetterExperie_OT_TextMultiLanguageInput(bpy.types.Operator):
    bl_idname = "better_experie.text_multi_language_input"
    bl_label = "多语言输入"
    bl_description = "打开一个输入框，支持多语言输入，并将文本插入到文本编辑器中"

    # 用于在弹窗中接收用户输入的属性
    input_text: bpy.props.StringProperty(name="输入文本",description="在此处输入您想要的文本（支持多语言）",default="")

    @classmethod
    def poll(cls, context):
        return get_active_text(context) is not None

    def invoke(self, context, event):
        """
        当操作被调用时，显示一个属性对话框。
        如果存在选区，则将选中的文本预填充到输入框中。
        """
        text_data = get_active_text(context)
        if text_data:
            full_text, original_lines_list, start_index, end_index, is_selected, \
                original_cursor_line_idx, original_cursor_char, \
                original_select_end_line_idx, original_select_end_char = get_text_and_selection_info(text_data)

            if is_selected:
                # 如果有选区，将选中的文本预填充到 input_text
                self.input_text = full_text[start_index:end_index]
            else:
                # 如果没有选区，清空 input_text
                self.input_text = ""
        else:
            self.input_text = "" # 如果没有活动的文本数据块，也清空

        wm = context.window_manager
        return wm.invoke_props_dialog(self, width=1200)

    def execute(self, context):
        text_data = get_active_text(context)
        if not text_data:
            self.report({'WARNING'}, "没有活动的文本数据块")
            return {'CANCELLED'}

        text_to_insert = self.input_text

        if not text_to_insert:
            self.report({'INFO'}, "未输入任何文本")
            return {'CANCELLED'}

        full_text, original_lines_list, start_global_idx, end_global_idx, is_selected, \
            original_cursor_line_idx, original_cursor_char, \
            original_select_end_line_idx, original_select_end_char = get_text_and_selection_info(text_data)

        new_text = ""
        new_cursor_line_idx = original_cursor_line_idx
        new_cursor_char = original_cursor_char
        new_select_end_line_idx = original_select_end_line_idx
        new_select_end_char = original_select_end_char

        if is_selected:
            # 如果有选区，替换选中的文本
            new_text = full_text[:start_global_idx] + text_to_insert + full_text[end_global_idx:]
            # 光标和选区锚点设置在插入文本的末尾
            new_cursor_global_idx = start_global_idx + len(text_to_insert)
        else:
            # 如果没有选区，在当前光标位置插入文本
            cursor_global_index = get_global_cursor_index(text_data, original_lines_list)
            new_text = full_text[:cursor_global_index] + text_to_insert + full_text[cursor_global_index:]
            # 光标和选区锚点设置在插入文本的末尾
            new_cursor_global_idx = cursor_global_index + len(text_to_insert)

        # 更新文本数据块
        text_data.clear()
        text_data.write(new_text)

        # 计算新的光标和选区位置
        new_full_lines = new_text.splitlines(keepends=True)
        new_cursor_line_idx, new_cursor_char = global_index_to_line_char(new_cursor_global_idx, new_full_lines)
        new_select_end_line_idx = new_cursor_line_idx # 选区锚点与光标重合，即无选区
        new_select_end_char = new_cursor_char

        # 恢复光标和选区位置
        text_data.cursor_set(line=new_cursor_line_idx, character=new_cursor_char)
        text_data.select_set(line_start=new_cursor_line_idx, char_start=new_cursor_char,
                             line_end=new_select_end_line_idx, char_end=new_select_end_char)

        self.report({'INFO'}, f"已插入文本: '{text_to_insert}'")
        return {'FINISHED'}

    def draw(self, context):
        layout = self.layout
        layout.label(text="请在此输入文本，支持多语言：")
        layout.prop(self, "input_text", text="")


class BetterExperie_OT_TextWordCount(bpy.types.Operator):
    bl_idname = "better_experie.text_word_count"
    bl_label = "字数统计"
    bl_description = "统计当前文本或选中区域的字符数、行数等信息"

    @classmethod
    def poll(cls, context):
        return get_active_text(context) is not None

    def execute(self, context):
        text_data = get_active_text(context)
        if not text_data:
            self.report({'WARNING'}, "没有活动的文本数据块")
            return {'CANCELLED'}

        full_text, original_lines_list, start_global_idx, end_global_idx, is_selected, \
            original_cursor_line_idx, original_cursor_char, \
            original_select_end_line_idx, original_select_end_char = get_text_and_selection_info(text_data)

        # --- 全文统计 ---
        all_chars = len(full_text)
        all_spaces = full_text.count(' ') + full_text.count('\t')
        all_non_spaces = all_chars - all_spaces
        all_lines = len(original_lines_list)
        if all_lines == 0 and all_chars > 0: # 针对单行无换行符的文本
             all_lines = 1
        elif all_lines == 0 and all_chars == 0: # 针对空文本
             all_lines = 0

        message = ""

        if is_selected:
            selected_text = full_text[start_global_idx:end_global_idx]
            selected_chars = len(selected_text)
            selected_spaces = selected_text.count(' ') + selected_text.count('\t')
            selected_non_spaces = selected_chars - selected_spaces

            selected_lines = 0
            if selected_text:
                # 统计选中区域的行数
                selected_lines = selected_text.count('\n') + (1 if selected_text and not selected_text.endswith('\n') else 0)
                if selected_text.strip() == "" and selected_text.count('\n') == 0: # 选中区域只有空格/制表符且无换行符
                    selected_lines = 1
                elif selected_text == "": # 空选区
                    selected_lines = 0

            message += f"-当前文本字符数量： {selected_chars}/{all_chars}\n"
            message += f"-空格字符数量： {selected_spaces}/{all_spaces}\n"
            message += f"-非空格字符数量： {selected_non_spaces}/{all_non_spaces}\n"
            message += f"-当前行数量： {selected_lines}/{all_lines}"
        else:
            message += f"-当前文本字符数量： {all_chars}\n"
            message += f"-空格字符数量： {all_spaces}\n"
            message += f"-非空格字符数量： {all_non_spaces}\n"
            message += f"-当前行数量： {all_lines}"

        self.report({'INFO'}, message)
        return {'FINISHED'}


# 注册和注销函数
classes = (
    BetterExperie_OT_TextRemoveTrailingSpace,
    BetterExperie_OT_TextRemoveEmptyLines,
    BetterExperie_OT_TextSortSelectedLines,

    BetterExperie_OT_TextCapitalizationEditor,
    BetterExperie_OT_TextInsertDateTime,

    BetterExperie_OT_TextMultiLanguageInput,
    BetterExperie_OT_TextWordCount,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes): # 注销时通常按相反顺序
        bpy.utils.unregister_class(cls)

