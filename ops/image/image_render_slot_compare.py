# 渲染槽位 AB 对比：在图像编辑器中对当前渲染结果与指定渲染槽位进行擦除式对比

import os
import uuid
import tempfile
import bpy
import gpu
import blf
from gpu_extras.batch import batch_for_shader

from ...utils import get_pref

_active_compare_operator = None


def _get_active_operator():
    return _active_compare_operator


def _set_active_operator(operator):
    global _active_compare_operator
    _active_compare_operator = operator


def _update_compare_slot(self, context):
    active_op = _get_active_operator()
    if active_op is not None:
        active_op.reload_target_slot(context)


def _draw_rect(shader, color, x0, y0, x1, y1):
    batch = batch_for_shader(
        shader,
        'TRI_FAN',
        {"pos": ((x0, y0), (x1, y0), (x1, y1), (x0, y1))},
    )
    shader.bind()
    shader.uniform_float("color", color)
    batch.draw(shader)


class BetterExperie_ImageCompareSettings(bpy.types.PropertyGroup):
    target_slot_index: bpy.props.IntProperty(
        name="对比槽位索引",
        description="当前用于对比的渲染槽位索引",
        min=0, default=0, update=_update_compare_slot,
    )


class BetterExperie_OT_RenderSlotABCompare(bpy.types.Operator):
    bl_idname = "better_experie.render_slot_ab_compare"
    bl_label = "运行槽位对比"
    bl_description = "拖动中线移动擦除位置，单击中线切换左右方向，Ctrl滚轮靠近中线调整分割线宽度，ESC 退出"
    bl_options = {'REGISTER'}

    _draw_handle = None
    _temp_image = None
    _area_ptr = None
    _region_ptr = None
    _window_region = None
    _source_image = None
    _source_width = 0
    _source_height = 0
    _split_x = 0
    _flip = False
    _line_pressed = False
    _line_dragging = False
    _line_press_x = 0
    _stop_requested = False

    @classmethod
    def poll(cls, context):
        if not context.area or context.area.type != 'IMAGE_EDITOR':
            return False
        space = context.area.spaces.active
        return bool(space and space.image)

    def _get_line_color(self):
        prefs = get_pref()
        return getattr(prefs, "compare_line_color", (1.0, 1.0, 1.0, 1.0))

    def _get_line_width(self):
        prefs = get_pref()
        return getattr(prefs, "compare_line_width", 20)

    def get_window_region(self, area):
        for region in area.regions:
            if region.type == 'WINDOW':
                return region
        return None

    def get_target_slot_index(self, context):
        return context.scene.better_experie_image_compare.target_slot_index

    def tag_redraw(self):
        for window in bpy.context.window_manager.windows:
            if not window.screen:
                continue
            for area in window.screen.areas:
                if area.as_pointer() == self._area_ptr:
                    area.tag_redraw()
                    return

    def remove_temp_image(self, image):
        if image is None:
            return
        try:
            bpy.data.images.remove(image, do_unlink=True)
        except Exception as exc:
            print(f"[槽位对比] 临时图像移除失败: {exc}")

    def request_stop(self):
        self._stop_requested = True
        self.cleanup()

    def extract_render_slot(self, context):
        image = self._source_image
        if not image:
            self.report({'ERROR'}, "未找到当前渲染结果")
            return None
        if image.type != 'RENDER_RESULT':
            self.report({'ERROR'}, "当前图像不是渲染结果")
            return None

        target_index = self.get_target_slot_index(context)
        slots = image.render_slots
        if target_index < 0 or target_index >= len(slots):
            self.report({'ERROR'}, "所选槽位不存在")
            return None

        original_index = image.render_slots.active_index
        temp_path = os.path.join(tempfile.gettempdir(), f"better_experie_slot_compare_{uuid.uuid4().hex}.exr")
        loaded_image = None

        try:
            image.render_slots.active_index = target_index
            image.save_render(temp_path, scene=context.scene)
            loaded_image = bpy.data.images.load(temp_path, check_existing=False)
            loaded_image.name = f".slot_compare_{uuid.uuid4().hex}"
            loaded_image.pack()
            return loaded_image
        except Exception as exc:
            self.report({'ERROR'}, f"读取槽位失败：{exc}")

            if loaded_image:
                self.remove_temp_image(loaded_image)
            return None

        finally:
            try:
                image.render_slots.active_index = original_index
            except Exception:
                pass
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass

    def reload_target_slot(self, context):
        if self._stop_requested:
            return
        new_temp_image = self.extract_render_slot(context)
        if new_temp_image is None:
            self.report({'WARNING'}, "切换槽位失败，已保留原对比图")
            return
        old_temp_image = self._temp_image
        self._temp_image = new_temp_image
        self.remove_temp_image(old_temp_image)
        self.tag_redraw()
        self.report({'INFO'}, f"已切换至槽位 {self.get_target_slot_index(context) + 1}")

    def jump_to_image_tab(self, context):
        area = context.area
        if not area or area.type != 'IMAGE_EDITOR':
            return False
        space = area.spaces.active
        if not space.show_region_ui:
            space.show_region_ui = True
        ui_region = next((region for region in area.regions if region.type == 'UI'), None)
        if not ui_region:
            return False
        # 跳转到 Image 分类标签
        ui_region.active_panel_category = "Image"
        area.tag_redraw()
        return True

    def invoke(self, context, event):
        active_op = _get_active_operator()
        if active_op is not None:
            active_op.request_stop()
            return {'FINISHED'}

        area = context.area
        space = area.spaces.active
        source_image = space.image
        window_region = self.get_window_region(area)

        if not source_image:
            self.report({'ERROR'}, "请先在图像编辑器中打开渲染结果")
            return {'CANCELLED'}
        if source_image.type != 'RENDER_RESULT':
            self.report({'ERROR'}, "请在图像编辑器中选择“渲染结果”后再运行")
            return {'CANCELLED'}
        if not source_image.render_slots:
            self.report({'ERROR'}, "当前渲染结果没有可用的渲染槽位")
            return {'CANCELLED'}
        if not window_region:
            self.report({'ERROR'}, "无法获取图像编辑器的绘制区域")
            return {'CANCELLED'}

        self._area_ptr = area.as_pointer()
        self._region_ptr = window_region.as_pointer()
        self._window_region = window_region
        self._source_image = source_image
        self._source_width = max(1, source_image.size[0])
        self._source_height = max(1, source_image.size[1])
        self._split_x = window_region.width // 2
        self._flip = False
        self._stop_requested = False
        self._line_pressed = False
        self._line_dragging = False

        temp_image = self.extract_render_slot(context)
        if temp_image is None:
            return {'CANCELLED'}
        self._temp_image = temp_image

        try:
            self._draw_handle = bpy.types.SpaceImageEditor.draw_handler_add(
                self.draw_callback_px, (), 'WINDOW', 'POST_PIXEL')
        except Exception as exc:
            self.report({'ERROR'}, f"注册绘制回调失败：{exc}")
            self.cleanup()
            return {'CANCELLED'}

        _set_active_operator(self)
        context.window_manager.modal_handler_add(self)
        self.jump_to_image_tab(context)
        self.tag_redraw()
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        try:
            if self._stop_requested:
                self.cleanup()
                return {'FINISHED'}
            if event.type == 'ESC':
                self.cleanup()
                return {'FINISHED'}

            region = self._window_region
            if region is None:
                self.cleanup()
                return {'CANCELLED'}

            mouse_x = event.mouse_x - region.x
            mouse_y = event.mouse_y - region.y
            mouse_in_region = 0 <= mouse_x <= region.width and 0 <= mouse_y <= region.height
            hit_radius = max(14, self._get_line_width() * 3)

            # Ctrl + 滚轮调整分割线宽度
            if event.ctrl and event.type in {'WHEELUPMOUSE', 'WHEELDOWNMOUSE'}:
                delta = 1 if event.type == 'WHEELUPMOUSE' else -1
                if mouse_in_region and abs(mouse_x - self._split_x) < max(20, self._get_line_width() / 2 + 5):
                    prefs = get_pref()
                    if prefs is not None:
                        prefs.compare_line_width = max(0, min(50, prefs.compare_line_width + delta))
                    self.tag_redraw()
                    return {'RUNNING_MODAL'}

            if event.type == 'LEFTMOUSE':
                if event.value == 'PRESS':
                    if mouse_in_region and abs(mouse_x - self._split_x) <= hit_radius:
                        self._line_pressed = True
                        self._line_dragging = False
                        self._line_press_x = mouse_x
                        return {'RUNNING_MODAL'}
                elif event.value == 'RELEASE' and self._line_pressed:
                    if not self._line_dragging:
                        self._flip = not self._flip
                    self._line_pressed = False
                    self._line_dragging = False
                    self.tag_redraw()
                    return {'RUNNING_MODAL'}

            if event.type == 'MOUSEMOVE' and self._line_pressed:
                if abs(mouse_x - self._line_press_x) > 4:
                    self._line_dragging = True
                if self._line_dragging:
                    self._split_x = max(0, min(region.width, mouse_x))
                    self.tag_redraw()
                    return {'RUNNING_MODAL'}

            return {'PASS_THROUGH'}
        except Exception as error:
            import traceback
            traceback.print_exc()
            self.report({'ERROR'}, str(error))
            self.cleanup()
            return {'CANCELLED'}

    def draw_callback_px(self):
        try:
            if self._temp_image is None or self._window_region is None:
                return

            region = self._window_region
            if region.as_pointer() != self._region_ptr:
                return

            temp_texture = gpu.texture.from_image(self._temp_image)
            if temp_texture is None:
                return

            line_color = self._get_line_color()
            line_width = self._get_line_width()
            props = bpy.context.scene.better_experie_image_compare

            x0, y0 = region.view2d.view_to_region(0.0, 0.0, clip=False)
            x1, y1 = region.view2d.view_to_region(
                float(self._source_width),
                float(self._source_height),
                clip=False,
            )

            image_left = min(x0, x1)
            image_right = max(x0, x1)
            image_bottom = min(y0, y1)
            image_top = max(y0, y1)
            image_width = image_right - image_left

            if image_width <= 0:
                return

            split_x = max(0, min(region.width, self._split_x))

            if self._flip:
                draw_left = image_left
                draw_right = min(float(split_x), image_right)
                uv_left = 0.0
                uv_right = max(0.0, min(1.0, (draw_right - image_left) / image_width))
            else:
                draw_left = max(float(split_x), image_left)
                draw_right = image_right
                uv_left = max(0.0, min(1.0, (draw_left - image_left) / image_width))
                uv_right = 1.0

            if draw_right > draw_left:
                vertices = (
                    (draw_left, image_bottom),
                    (draw_right, image_bottom),
                    (draw_left, image_top),
                    (draw_right, image_top),
                )
                texcoords = (
                    (uv_left, 0.0),
                    (uv_right, 0.0),
                    (uv_left, 1.0),
                    (uv_right, 1.0),
                )
                indices = ((0, 1, 2), (2, 1, 3))

                shader = gpu.shader.from_builtin('IMAGE_SCENE_LINEAR_TO_REC709_SRGB')
                batch = batch_for_shader(shader, 'TRIS', {"pos": vertices, "texCoord": texcoords}, indices=indices)
                gpu.state.blend_set('ALPHA')
                shader.bind()
                shader.uniform_sampler("image", temp_texture)
                batch.draw(shader)
                gpu.state.blend_set('NONE')

            line_shader = gpu.shader.from_builtin('UNIFORM_COLOR')
            half_width = line_width * 0.5
            _draw_rect(line_shader, line_color, split_x - half_width, 0, split_x + half_width, region.height)

            slot_number = props.target_slot_index + 1

            font_id = 0
            blf.size(font_id, 13)
            blf.color(font_id, 1.0, 1.0, 1.0, 0.95)
            blf.position(font_id, 12, 12, 0)
            blf.draw(font_id, f"槽位 {slot_number} 对比｜拖动中线移动｜单击中线切换方向｜ESC 退出")
        except ReferenceError:
            pass
        except Exception:
            import traceback
            traceback.print_exc()
        finally:
            try:
                gpu.state.blend_set('NONE')
            except Exception:
                pass

    def cleanup(self):
        if self._draw_handle is not None:
            try:
                bpy.types.SpaceImageEditor.draw_handler_remove(self._draw_handle, 'WINDOW')
            except Exception:
                pass
            self._draw_handle = None
        if self._temp_image is not None:
            self.remove_temp_image(self._temp_image)
            self._temp_image = None
        if _get_active_operator() is self:
            _set_active_operator(None)
        self.tag_redraw()

    def cancel(self, context):
        self.cleanup()


class BETTER_EXPERIE_PT_render_slot_ab_compare(bpy.types.Panel):
    bl_label = "槽位对比"
    bl_idname = "BETTER_EXPERIE_PT_render_slot_ab_compare"
    bl_space_type = 'IMAGE_EDITOR'
    bl_region_type = 'UI'
    bl_category = "Image"

    @classmethod
    def poll(cls, context):
        if not context.area or context.area.type != 'IMAGE_EDITOR':
            return False
        space = context.area.spaces.active
        image = space.image if space else None
        return bool(image and image.type == 'RENDER_RESULT')

    def draw(self, context):
        layout = self.layout
        props = context.scene.better_experie_image_compare
        prefs = get_pref()
        is_running = _get_active_operator() is not None

        space = context.space_data
        image = space.image

        if not is_running:
            layout.operator("better_experie.render_slot_ab_compare", text="运行对比", icon='PLAY')
        else:
            layout.operator("better_experie.render_slot_ab_compare", text="停止对比", icon='CANCEL')
        col = layout.column()
        col.active = is_running
        col.template_list(
            "IMAGE_UL_render_slots",  # 复用官方的
            "compare_render_slots",
            image,
            "render_slots",
            props,
            "target_slot_index",
            rows=4,
        )
        col.separator()
        row = col.row()
        if prefs is not None:
            row.prop(prefs, "compare_line_color", text="")
            row.prop(prefs, "compare_line_width")


def _image_ht_header_compare_draw(self, context):
    prefs = get_pref()
    if not getattr(prefs, "show_slot_compare_header", False):
        return
    space = context.area.spaces.active
    image = space.image if space else None
    if bool(image and image.type == 'RENDER_RESULT'):
        active_op = _get_active_operator()
        if active_op is not None:
            self.layout.operator("better_experie.render_slot_ab_compare", text="", icon="QUIT")
        else:
            self.layout.operator("better_experie.render_slot_ab_compare", text="", icon="SPLIT_VERTICAL")


classes = (
    BetterExperie_ImageCompareSettings,
    BetterExperie_OT_RenderSlotABCompare,
    BETTER_EXPERIE_PT_render_slot_ab_compare,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.better_experie_image_compare = bpy.props.PointerProperty(type=BetterExperie_ImageCompareSettings)
    try:
        bpy.types.IMAGE_HT_header.append(_image_ht_header_compare_draw)
    except (ValueError, AttributeError):
        pass


def unregister():
    active_op = _get_active_operator()
    if active_op is not None:
        try:
            active_op.cleanup()
        except Exception:
            pass
    if hasattr(bpy.types.Scene, "better_experie_image_compare"):
        del bpy.types.Scene.better_experie_image_compare
    try:
        bpy.types.IMAGE_HT_header.remove(_image_ht_header_compare_draw)
    except (ValueError, AttributeError):
        pass

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
