# 文本编辑器字符高亮：选中单行文本后，高亮所有相同词

import bpy
import gpu
from gpu_extras.batch import batch_for_shader

_STATE = {
    "draw_handler": None,
    "shader": None,
}


def _get_selected_text(space):
    # 获取当前 Text Editor 中被选择的单行文本。
    text = space.text
    if text is None:
        return None
    lines = list(text.lines)
    if not lines:
        return None
    try:
        current_line_index = lines.index(text.current_line)
        end_line_index = lines.index(text.select_end_line)
    except ValueError:
        return None

    current_char = text.current_character
    end_char = text.select_end_character

    start = (current_line_index, current_char)
    end = (end_line_index, end_char)
    # Blender 中 current 与 select_end 的先后并不固定，统一排序。
    if start > end:
        start, end = end, start

    start_line, start_char = start
    end_line, end_char = end
    # 第一版仅支持单行关键字。
    if start_line != end_line:
        return None

    selected = lines[start_line].body[start_char:end_char]
    # 防止空选择、仅空白选择，以及异常长文本造成频繁匹配。
    if not selected or selected.isspace() or len(selected) > 128:
        return None
    return selected


def _add_rect(vertices, x0, y0, x1, y1):
    # 向顶点数组加入一个矩形，使用两个三角形绘制。
    vertices.extend([
        (x0, y0), (x1, y0), (x1, y1),
        (x0, y0), (x1, y1), (x0, y1),
    ])


def _draw_highlights():
    try:
        window_manager = bpy.context.window_manager
        if not window_manager.better_experie_text_selection_highlight_enabled:
            return
        space = bpy.context.space_data
        if not isinstance(space, bpy.types.SpaceTextEditor):
            return
        text = space.text
        if text is None:
            return
        needle = _get_selected_text(space)
        if needle is None:
            return
        # Text Editor 的字体尺寸，用于近似估算行高。
        line_height = max(12.0, float(space.font_size))
        vertices = []

        for line_index, line in enumerate(text.lines):
            body = line.body
            search_start = 0
            match_ranges = []
            # 第一步：找出全部匹配位置，允许重叠匹配。
            while True:
                column_start = body.find(needle, search_start)
                if column_start == -1:
                    break
                column_end = column_start + len(needle)
                match_ranges.append((column_start, column_end))
                # +1 保留重叠匹配，用于后续区间合并。
                search_start = column_start + 1

            # 第二步：合并彼此重叠的匹配区间。
            merged_ranges = []
            for start, end in match_ranges:
                if merged_ranges and start < merged_ranges[-1][1]:
                    previous_start, previous_end = merged_ranges[-1]
                    merged_ranges[-1] = (previous_start, max(previous_end, end))
                else:
                    merged_ranges.append((start, end))

            # 第三步：每个合并后的连续区域只绘制一个框。
            for column_start, column_end in merged_ranges:
                try:
                    start_pos = space.region_location_from_cursor(line_index, column_start)
                    end_pos = space.region_location_from_cursor(line_index, column_end)
                except RuntimeError:
                    continue

                if start_pos is None or end_pos is None:
                    continue

                x0, y0 = start_pos
                x1, y1 = end_pos

                if abs(y1 - y0) < line_height * 0.5 and x1 > x0:
                    rect_y0 = y0
                    rect_y1 = y0 + 2 * line_height
                    _add_rect(vertices, x0, rect_y0, x1, rect_y1)

        if not vertices:
            return

        if _STATE["shader"] is None:
            _STATE["shader"] = gpu.shader.from_builtin("UNIFORM_COLOR")

        shader = _STATE["shader"]
        batch = batch_for_shader(shader, "TRIS", {"pos": vertices})

        gpu.state.blend_set("ALPHA")
        shader.bind()
        shader.uniform_float("color", (1.0, 0.78, 0.05, 0.28))
        batch.draw(shader)
    except ReferenceError:
        pass
    except Exception:
        import traceback
        traceback.print_exc()
    finally:
        try:
            gpu.state.blend_set("NONE")
        except Exception:
            pass


def _text_mt_view_draw(self, context):
    layout = self.layout
    layout.prop(context.window_manager, "better_experie_text_selection_highlight_enabled", text="字符高亮")
    layout.separator()


def _text_ht_header_draw(self, context):
    layout = self.layout
    layout.prop(context.window_manager, "better_experie_text_selection_highlight_enabled", text="", icon="SEQ_STRIP_DUPLICATE")


def register():
    bpy.types.WindowManager.better_experie_text_selection_highlight_enabled = bpy.props.BoolProperty(
        name="启用高亮显示",
        description="高亮显示所有和所选词相同的词组",
        default=False,
    )
    _STATE["draw_handler"] = bpy.types.SpaceTextEditor.draw_handler_add(_draw_highlights, (), "WINDOW", "POST_PIXEL")
    try:
        bpy.types.TEXT_HT_header.append(_text_ht_header_draw)
    except (ValueError, AttributeError):
        pass
    try:
        bpy.types.TEXT_MT_view.prepend(_text_mt_view_draw)
    except (ValueError, AttributeError):
        pass


def unregister():
    try:
        bpy.types.TEXT_HT_header.remove(_text_ht_header_draw)
    except (ValueError, AttributeError):
        pass
    try:
        bpy.types.TEXT_MT_view.remove(_text_mt_view_draw)
    except (ValueError, AttributeError):
        pass
    if _STATE["draw_handler"] is not None:
        try:
            bpy.types.SpaceTextEditor.draw_handler_remove(_STATE["draw_handler"], "WINDOW")
        except ValueError:
            pass
        _STATE["draw_handler"] = None
    _STATE["shader"] = None
    if hasattr(bpy.types.WindowManager, "better_experie_text_selection_highlight_enabled"):
        del bpy.types.WindowManager.better_experie_text_selection_highlight_enabled
