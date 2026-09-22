# 视口快照：截取当前三维视口为快照图，绘制可拖动/翻转的中线做前后对比

import os
import tempfile
import bpy
import gpu
import blf
from gpu_extras.batch import batch_for_shader

from ...utils import get_pref

_snapshot_running = False


def _get_running():
    return _snapshot_running


def _set_running(status=True):
    global _snapshot_running
    _snapshot_running = status
    return status


def _snapshot_path():
    return os.path.join(tempfile.gettempdir(), "better_experie_viewport_snapshot.png")


def _draw_rect(shader, color, x0, y0, x1, y1):
    verts = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    batch = batch_for_shader(shader, 'TRI_FAN', {"pos": verts})
    shader.bind()
    shader.uniform_float("color", color)
    batch.draw(shader)


class BetterExperie_OT_ViewportSnapshot(bpy.types.Operator):
    bl_idname = "better_experie.viewport_snapshot"
    bl_label = "视口快照"
    bl_options = {'REGISTER', 'UNDO'}
    bl_description = "拖动中线可滑动快照，点击中线可交换快照左右方向\nCtrl滚轮靠近中线可调整分割线宽度\nESC退出，F5刷新快照"

    _handle = None
    _current_image = None
    _cross_line_x = None
    _cross_flip = False
    _target_area_id = None
    _line_pressing = False
    _line_dragging = False
    _line_press_x = 0

    @classmethod
    def poll(cls, context):
        return bool(context.area and context.area.type == 'VIEW_3D')

    def _get_line_color(self):
        prefs = get_pref()
        return getattr(prefs, "compare_line_color", (1.0, 1.0, 1.0, 1.0))

    def _get_cross_width(self):
        prefs = get_pref()
        return getattr(prefs, "compare_line_width", 20)

    def capture_snapshot(self, context):
        try:
            img = bpy.data.images.get(".viewport_snapshot")
            if img:
                img.user_clear()
                bpy.data.images.remove(img)

            path = _snapshot_path()
            area = context.area
            old_type = area.type
            area.type = 'VIEW_3D'
            bpy.ops.screen.screenshot_area(filepath=path, check_existing=False)
            area.type = old_type

            self._current_image = bpy.data.images.load(path, check_existing=False)
            self._current_image.name = ".viewport_snapshot"
        except Exception as e:
            self.report({'ERROR'}, f"截图失败: {str(e)}")

    def clear_snapshot(self, context):
        if self._current_image:
            try:
                bpy.data.images.remove(self._current_image)
            except Exception:
                pass
        self._current_image = None
        path = _snapshot_path()
        if os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                pass

    def jump_to_view_tab(self, context):
        space = context.space_data
        if space is not None and hasattr(space, "show_region_ui") and not space.show_region_ui:
            space.show_region_ui = True
        for region in context.area.regions:
            if region.type == 'UI':
                try:
                    region.active_panel_category = "View"
                except Exception:
                    pass
                break

    def invoke(self, context, event):
        if _get_running():
            _set_running(False)
            self.report({'INFO'}, "退出视口快照")
            return {'CANCELLED'}
        _set_running(True)

        window_region = next((r for r in context.area.regions if r.type == 'WINDOW'), None)
        if window_region is None:
            _set_running(False)
            self.report({'ERROR'}, "无法获取视口绘制区域")
            return {'CANCELLED'}

        self._target_area_id = context.area.as_pointer()
        self._cross_line_x = window_region.width // 2
        self._cross_flip = False
        self._line_pressing = False
        self._line_dragging = False

        self.capture_snapshot(context)

        try:
            self._handle = bpy.types.SpaceView3D.draw_handler_add(
                self.draw_callback_px, (context,), 'WINDOW', 'POST_PIXEL')
        except Exception as e:
            self.report({'ERROR'}, f"注册绘制回调失败: {str(e)}")
            self.clear_snapshot(context)
            _set_running(False)
            return {'CANCELLED'}

        context.window_manager.modal_handler_add(self)
        self.jump_to_view_tab(context)
        context.area.tag_redraw()
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        try:
            if not _get_running():
                self.cancel(context)
                return {'FINISHED'}

            region = context.region
            if region is None:
                return {'PASS_THROUGH'}
            line_width = self._get_cross_width()
            cross_x = self._cross_line_x

            # 基础按键
            if event.type == 'F5' and event.value == 'PRESS':
                self.capture_snapshot(context)
                return {'RUNNING_MODAL'}

            if event.type == 'ESC':
                self.cancel(context)
                return {'FINISHED'}

            prefs = get_pref()

            # --- Ctrl + 滚轮修改分割线宽 ---
            if event.ctrl and event.type in {'WHEELUPMOUSE', 'WHEELDOWNMOUSE'}:
                delta = 1 if event.type == 'WHEELUPMOUSE' else -1
                mx = event.mouse_region_x

                if abs(mx - cross_x) < max(20, line_width / 2 + 5):
                    if prefs is not None:
                        prefs.compare_line_width = max(0, min(50, prefs.compare_line_width + delta))
                    context.area.tag_redraw()
                    return {'RUNNING_MODAL'}

            # 鼠标交互逻辑 (点击切换/拖拽)
            line_drag_radius = max(15, line_width + 10)
            if event.type == 'LEFTMOUSE':
                if event.value == 'PRESS':
                    if abs(event.mouse_region_x - cross_x) < line_drag_radius:
                        self._line_pressing, self._line_dragging, self._line_press_x = True, False, event.mouse_region_x
                        return {'RUNNING_MODAL'}

                elif event.value == 'RELEASE' and self._line_pressing:
                    if not self._line_dragging:
                        self._cross_flip = not self._cross_flip
                    self._line_pressing = False
                    self._line_dragging = False
                    context.area.tag_redraw()
                    return {'RUNNING_MODAL'}

            if event.type == 'MOUSEMOVE' and self._line_pressing:
                if abs(event.mouse_region_x - self._line_press_x) > 5:
                    self._line_dragging = True

                if self._line_dragging:
                    self._cross_line_x = max(10, min(region.width - 10, event.mouse_region_x))
                    context.area.tag_redraw()
                    return {'RUNNING_MODAL'}

            return {'PASS_THROUGH'}
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.report({'ERROR'}, f"运行出错: {str(e)}")
            self.cancel(context)
            return {'CANCELLED'}

    def cancel(self, context):
        if self._handle is not None:
            try:
                bpy.types.SpaceView3D.draw_handler_remove(self._handle, 'WINDOW')
            except Exception:
                pass
            self._handle = None
        self.clear_snapshot(context)
        _set_running(False)
        if context.area:
            context.area.tag_redraw()

    def draw_callback_px(self, context):
        try:
            if not context.area or context.area.as_pointer() != self._target_area_id:
                return
            line_color = self._get_line_color()
            line_width = self._get_cross_width()
            edge_w = line_width // 4
            region, area = context.region, context.area
            img = self._current_image
            cross_x = int(self._cross_line_x)

            # 计算 3D 视图区块相对于整个 Area 的偏移
            rel_x = region.x - area.x
            rel_y = region.y - area.y
            total_w, total_h = area.width, area.height

            # 计算当前视图在截图中的 UV 边界 (只采样 3D 视图部分，剔除 N 面板)
            u_min = rel_x / total_w
            u_max = (rel_x + region.width) / total_w
            v_min = rel_y / total_h
            v_max = (rel_y + region.height) / total_h
            u_split = (rel_x + cross_x) / total_w

            if img and img.as_pointer() != 0:
                try:
                    shader_img = gpu.shader.from_builtin('IMAGE_SCENE_LINEAR_TO_REC709_SRGB')
                    if not self._cross_flip:
                        vertices = ((cross_x, 0), (region.width, 0), (cross_x, region.height), (region.width, region.height))
                        texcoord = ((u_split, v_min), (u_max, v_min), (u_split, v_max), (u_max, v_max))
                    else:
                        vertices = ((0, 0), (cross_x, 0), (0, region.height), (cross_x, region.height))
                        texcoord = ((u_min, v_min), (u_split, v_min), (u_min, v_max), (u_split, v_max))

                    batch_img = batch_for_shader(shader_img, 'TRIS', {"pos": vertices, "texCoord": texcoord}, indices=((0, 1, 2), (2, 1, 3)))
                    shader_img.bind()
                    tex = gpu.texture.from_image(img)
                    shader_img.uniform_sampler("image", tex)
                    batch_img.draw(shader_img)
                except Exception:
                    pass

            # 绘制边框和线
            shader = gpu.shader.from_builtin('UNIFORM_COLOR')
            if not self._cross_flip:
                _draw_rect(shader, line_color, region.width - edge_w, 0, region.width, region.height)
                _draw_rect(shader, line_color, cross_x, region.height - edge_w, region.width, region.height)
                _draw_rect(shader, line_color, cross_x, 0, region.width, edge_w)
            else:
                _draw_rect(shader, line_color, 0, 0, edge_w, region.height)
                _draw_rect(shader, line_color, 0, region.height - edge_w, cross_x, region.height)
                _draw_rect(shader, line_color, 0, 0, cross_x, edge_w)

            if line_width > 0:
                lx0, lx1 = cross_x - line_width // 2, cross_x + (line_width + 1) // 2
                _draw_rect(shader, line_color, lx0, 0, lx1, region.height)

            # 绘制文本
            font_id = 0
            blf.size(font_id, 14)
            blf.color(font_id, 1.0, 1.0, 1.0, 1.0)
            desc = "【快照对比】拖动中线滑动，点击中线切换方向，ESC退出，F5刷新"
            margin = 10
            if not self._cross_flip:
                text_x = cross_x + ((line_width + 1) // 2) + margin
            else:
                text_x = edge_w + margin
            text_y = edge_w + margin
            blf.position(font_id, text_x, text_y, 0)
            blf.draw(font_id, desc)
        except ReferenceError:
            pass
        except Exception:
            import traceback
            traceback.print_exc()


class BETTER_EXPERIE_PT_viewport_snapshot(bpy.types.Panel):
    bl_label = "视口快照"
    bl_idname = "BETTER_EXPERIE_PT_viewport_snapshot"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "View"

    def draw(self, context):
        layout = self.layout
        prefs = get_pref()
        is_running = _get_running()

        if not is_running:
            layout.operator("better_experie.viewport_snapshot", text="运行快照", icon='PLAY')
        else:
            layout.operator("better_experie.viewport_snapshot", text="停止快照", icon='CANCEL')

        if prefs is not None:
            row = layout.row()
            row.prop(prefs, "compare_line_color", text="")
            row.prop(prefs, "compare_line_width")


def _view3d_ht_header_snapshot_draw(self, context):
    prefs = get_pref()
    if not getattr(prefs, "show_view3d_screenshot_button", False):
        return
    self.layout.operator(
        "better_experie.viewport_snapshot",
        text="", icon="QUIT" if _get_running() else "SPLIT_VERTICAL")


classes = (
    BetterExperie_OT_ViewportSnapshot,
    BETTER_EXPERIE_PT_viewport_snapshot,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    try:
        bpy.types.VIEW3D_HT_header.append(_view3d_ht_header_snapshot_draw)
    except (ValueError, AttributeError):
        pass


def unregister():
    try:
        bpy.types.VIEW3D_HT_header.remove(_view3d_ht_header_snapshot_draw)
    except (ValueError, AttributeError):
        pass
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
