# 着色器编辑器 → 区域光 GPU 预览
# 原脚本：智小荣《区域光 GPU 预览》v2.1.0
# 入口迁移：原 N 面板已移除，改为着色器编辑器标题栏三个按钮
# 仅当所选物体包含区域光时显示；临时预览为 3 秒停留 + 1 秒渐隐

import hashlib
import math
import tempfile
import time
import traceback
from pathlib import Path

import bpy
import gpu
import numpy as np
from bpy.app.handlers import persistent
from gpu_extras.batch import batch_for_shader
from mathutils import Vector

try:
    import OpenImageIO as oiio
except Exception:
    oiio = None


PREVIEW_SIZE = 256
DRAW_OFFSET = 0.002
TEMP_DIR = Path(tempfile.gettempdir()) / "better_experie_light_preview"
TEMP_HOLD_SECONDS = 3.0
TEMP_FADE_SECONDS = 1.0
TIMER_INTERVAL = 0.03

# 常驻显示的灯光物体（仅记录 object.name，避免持有失效引用）
_persistent_objects = set()
# 临时预览：object.name -> 开始显示的时间戳
_temp_entries = {}
_draw_handler = None
_shader = None


def ensure_temp_dir():
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    return TEMP_DIR


def safe_filename(name):
    """将灯光数据块名称转换为固定长度的 SHA1 文件名。"""
    return hashlib.sha1(str(name).encode("utf-8")).hexdigest().upper()


def get_preview_path(light_data):
    return TEMP_DIR / f"{safe_filename(light_data.name)}.bmp"


def get_selected_area_lights(context):
    return [
        obj for obj in context.selected_objects
        if obj.type == "LIGHT" and obj.data and obj.data.type == "AREA"
    ]


def _tag_redraw_all_3dviews():
    for window in bpy.context.window_manager.windows:
        if not window.screen:
            continue
        for area in window.screen.areas:
            if area.type == "VIEW_3D":
                area.tag_redraw()


class TexturePool:
    TEXTURE_MAP = {}

    @classmethod
    def read_image_to_tex(cls, file_path):
        if oiio is None:
            print("[Area Light Preview] 缺少 OpenImageIO，无法读取预览图")
            return None

        file_path = Path(file_path)
        if not file_path.exists():
            return None

        image_buf = oiio.ImageBuf(file_path.as_posix())
        if image_buf.has_error:
            print(f"[Area Light Preview] 图片读取失败: {image_buf.geterror()}")
            return None

        spec = image_buf.spec()
        if spec.width <= 0 or spec.height <= 0:
            print(f"[Area Light Preview] 图片尺寸无效: {file_path}")
            return None

        # 直接读取为 8 位无符号整数，避免 FLOAT 数据与 RGBA32F 显存占用。
        pixels = image_buf.get_pixels(oiio.UINT8)
        if pixels is None:
            print(f"[Area Light Preview] 无法读取像素: {file_path}")
            return None

        pixels = np.asarray(pixels, dtype=np.uint8)
        pixels = pixels.reshape((spec.height, spec.width, spec.nchannels))
        # GPUTexture 没有 RGB8，统一补全到 RGBA8。
        if spec.nchannels == 1:
            rgb = np.repeat(pixels[:, :, 0:1], 3, axis=2)
            alpha = np.full((spec.height, spec.width, 1), 255, dtype=np.uint8)
            pixels = np.concatenate((rgb, alpha), axis=2)
        elif spec.nchannels == 2:
            rgb = np.repeat(pixels[:, :, 0:1], 3, axis=2)
            alpha = pixels[:, :, 1:2]
            pixels = np.concatenate((rgb, alpha), axis=2)
        elif spec.nchannels == 3:
            alpha = np.full((spec.height, spec.width, 1), 255, dtype=np.uint8)
            pixels = np.concatenate((pixels, alpha), axis=2)
        else:
            pixels = pixels[:, :, :4]

        pixels = pixels.astype(np.float32) / 255.0
        pixels = np.ascontiguousarray(pixels, dtype=np.float32)
        gpu_buffer = gpu.types.Buffer("FLOAT", (spec.width, spec.height, 4), pixels.ravel())
        return gpu.types.GPUTexture((spec.width, spec.height), format="RGBA8", data=gpu_buffer)

    @classmethod
    def get_texture(cls, file_path):
        key = str(Path(file_path).resolve())
        if key not in cls.TEXTURE_MAP:
            texture = cls.read_image_to_tex(file_path)
            if texture:
                cls.TEXTURE_MAP[key] = texture
        return cls.TEXTURE_MAP.get(key)

    @classmethod
    def invalidate(cls, file_path):
        key = str(Path(file_path).resolve())
        cls.TEXTURE_MAP.pop(key, None)

    @classmethod
    def clear(cls):
        cls.TEXTURE_MAP.clear()


class PreviewRenderSession:
    """复用同一个临时 Scene、Camera、Area Light 完成一批预览渲染。"""

    def __init__(self):
        self.scene = None
        self.light_data = None
        self.light_obj = None
        self.cam_data = None
        self.cam_obj = None

        try:
            self.scene = bpy.data.scenes.new("BetterExperie_LightPreviewScene")
            self.light_data = bpy.data.lights.new("BetterExperie_TempAreaLightData", "AREA")
            self.light_obj = bpy.data.objects.new("BetterExperie_TempAreaLight", self.light_data)
            self.scene.collection.objects.link(self.light_obj)

            self.cam_data = bpy.data.cameras.new("BetterExperie_TempCameraData")
            self.cam_obj = bpy.data.objects.new("BetterExperie_TempCamera", self.cam_data)
            self.scene.collection.objects.link(self.cam_obj)
            self.scene.camera = self.cam_obj

            try:
                self.scene.render.engine = "CYCLES"
                self.scene.cycles.device = "CPU"

                self.scene.cycles.samples = 1
                self.scene.cycles.use_denoising = False
                self.scene.cycles.use_adaptive_sampling = False

                self.scene.cycles.max_bounces = 0
                self.scene.cycles.diffuse_bounces = 0
                self.scene.cycles.glossy_bounces = 0
                self.scene.cycles.transmission_bounces = 0
                self.scene.cycles.volume_bounces = 0
                self.scene.cycles.transparent_max_bounces = 0
            except Exception as exc:
                raise RuntimeError("当前 Blender 未启用 Cycles，无法生成区域光预览") from exc

            self.scene.render.resolution_x = PREVIEW_SIZE
            self.scene.render.resolution_y = PREVIEW_SIZE
            self.scene.render.resolution_percentage = 100

            self.scene.render.image_settings.file_format = "BMP"
            self.scene.render.image_settings.color_mode = "RGB"
            self.scene.render.image_settings.color_depth = "8"

            self.cam_obj.location = (0.0, 0.0, 1.0)
            self.cam_data.type = "ORTHO"
            self.cam_data.ortho_scale = 1.0
            self.cam_data.clip_start = 0.1
            self.cam_data.clip_end = 2.0

            self.light_obj.location = (0.0, 0.0, 0.5)
            self.light_obj.rotation_euler = (math.radians(180.0), 0.0, 0.0)
            self.light_obj.scale = (1.0, -1.0, 1.0)
            if hasattr(self.light_obj, "visible_camera"):
                self.light_obj.visible_camera = True
        except Exception:
            self.close()
            raise

    def apply_light_data(self, source_light_data):
        old_light_data = self.light_obj.data
        new_light_data = source_light_data.copy()
        new_light_data.name = "BetterExperie_TempAreaLightData"

        self.light_obj.data = new_light_data
        self.light_data = new_light_data

        # 当前 Object 已指向新数据，可删除上一盏灯的数据副本。
        if old_light_data and old_light_data.users == 0:
            bpy.data.lights.remove(old_light_data, do_unlink=True)

        self.light_obj.rotation_euler = (math.radians(180.0), 0.0, 0.0)
        self.light_obj.location = (0.0, 0.0, 0.5)
        self.light_obj.scale = (1.0, -1.0, 1.0)
        if hasattr(self.light_obj, "visible_camera"):
            self.light_obj.visible_camera = True
        if hasattr(new_light_data, "spread"):
            new_light_data.spread = math.radians(180.0)
        new_light_data.size = 1.0
        if hasattr(new_light_data, "size_y"):
            new_light_data.size_y = 1.0

    def render(self, area_light):
        preview_path = get_preview_path(area_light.data)
        try:
            self.apply_light_data(area_light.data)
            self.scene.render.filepath = str(preview_path)

            start_time = time.time()
            # 不切换 window.scene，避免着色器编辑器在渲染时闪断。
            bpy.ops.render.render(write_still=True, scene=self.scene.name)
            elapsed_ms = (time.time() - start_time) * 1000

            if not preview_path.exists():
                return False, f"预览图片未生成: {preview_path.name}"

            # 新图片已写入磁盘，删除同路径的旧 GPU 纹理缓存。
            TexturePool.invalidate(preview_path)
            print(f"[Area Light Preview] 已生成: {preview_path.name}, 耗时: {elapsed_ms:.2f} ms")
            return True, preview_path
        except Exception as exc:
            return False, str(exc)

    def close(self):
        for obj in (self.light_obj, self.cam_obj):
            if obj is None:
                continue
            try:
                bpy.data.objects.remove(obj, do_unlink=True)
            except Exception:
                pass

        for data, collection in (
            (self.light_data, bpy.data.lights),
            (self.cam_data, bpy.data.cameras),
        ):
            if data is None:
                continue
            try:
                if data.users == 0:
                    collection.remove(data, do_unlink=True)
            except Exception:
                pass

        if self.scene is not None:
            try:
                bpy.data.scenes.remove(self.scene, do_unlink=True)
            except Exception:
                pass

        self.scene = None
        self.light_obj = None
        self.light_data = None
        self.cam_obj = None
        self.cam_data = None


def _build_previews(context, light_objects):
    """按灯光数据去重后渲染，返回 (成功路径集合, 失败描述列表)。"""
    unique_lights = {}
    for obj in light_objects:
        unique_lights[obj.data.as_pointer()] = obj
    light_list = list(unique_lights.values())

    success_paths = set()
    failed_items = []
    render_session = None
    progress_started = False

    try:
        render_session = PreviewRenderSession()
        context.window_manager.progress_begin(0, len(light_list))
        progress_started = True
        for index, light_obj in enumerate(light_list, start=1):
            context.window_manager.progress_update(index)
            success, result = render_session.render(light_obj)
            if success:
                success_paths.add(str(Path(result).resolve()))
            else:
                failed_items.append(f"{light_obj.name}: {result}")
    finally:
        if progress_started:
            try:
                context.window_manager.progress_end()
            except Exception:
                pass
        if render_session is not None:
            render_session.close()

    return success_paths, failed_items


def _temp_alpha(start_time, now):
    elapsed = now - start_time
    if elapsed <= TEMP_HOLD_SECONDS:
        return 1.0
    fade_elapsed = elapsed - TEMP_HOLD_SECONDS
    if fade_elapsed >= TEMP_FADE_SECONDS:
        return 0.0
    return 1.0 - fade_elapsed / TEMP_FADE_SECONDS


def _get_area_light(name):
    obj = bpy.data.objects.get(name)
    if obj is None or obj.type != "LIGHT" or not obj.data or obj.data.type != "AREA":
        return None
    return obj


def _is_light_visible(context, obj):
    try:
        view_layer = context.view_layer
        if view_layer.objects.get(obj.name) is None:
            return False
        return obj.visible_get(view_layer=view_layer)
    except Exception:
        return False


def _get_texture_for(obj):
    try:
        preview_path = get_preview_path(obj.data)
        if not preview_path.exists():
            return None
        return TexturePool.get_texture(preview_path)
    except Exception:
        return None


def _get_shader():
    global _shader
    if _shader is None:
        # IMAGE_COLOR 支持 color 均匀量，用于临时预览的透明度渐隐。
        try:
            _shader = gpu.shader.from_builtin("IMAGE_COLOR")
        except Exception:
            _shader = gpu.shader.from_builtin("IMAGE")
    return _shader


def _draw_preview_plane(shader, obj, texture, alpha):
    light_data = obj.data
    width = max(light_data.size, 0.0001)
    if light_data.shape in {"SQUARE", "DISK"}:
        height = width
    else:
        height = max(getattr(light_data, "size_y", width), 0.0001)

    half_width = width * 0.5
    half_height = height * 0.5
    local_offset = Vector((0.0, 0.0, -DRAW_OFFSET))

    # 碟形与椭圆形：以 32 段扇形绘制。
    if light_data.shape in {"DISK", "ELLIPSE"}:
        segments = 32
        local_vertices = [Vector((0.0, 0.0, 0.0)) + local_offset]
        uv_coords = [(0.5, 0.5)]

        for index in range(segments + 1):
            angle = math.tau * index / segments
            cos_value = math.cos(angle)
            sin_value = math.sin(angle)
            local_vertices.append(
                Vector((cos_value * half_width, sin_value * half_height, 0.0)) + local_offset
            )
            uv_coords.append((0.5 + cos_value * 0.5, 0.5 - sin_value * 0.5))

        world_vertices = [obj.matrix_world @ vertex for vertex in local_vertices]
        batch = batch_for_shader(
            shader, "TRI_FAN", {"pos": world_vertices, "texCoord": uv_coords}
        )

    # 方形与矩形：保持四边形绘制。
    else:
        local_vertices = [
            Vector((-half_width, -half_height, 0.0)) + local_offset,
            Vector((half_width, -half_height, 0.0)) + local_offset,
            Vector((half_width, half_height, 0.0)) + local_offset,
            Vector((-half_width, half_height, 0.0)) + local_offset,
        ]
        world_vertices = [obj.matrix_world @ vertex for vertex in local_vertices]
        batch = batch_for_shader(
            shader,
            "TRI_FAN",
            {
                "pos": world_vertices,
                "texCoord": [(0.0, 1.0), (1.0, 1.0), (1.0, 0.0), (0.0, 0.0)],
            },
        )

    shader.bind()
    shader.uniform_sampler("image", texture)
    try:
        shader.uniform_float("color", (1.0, 1.0, 1.0, alpha))
    except Exception:
        pass
    batch.draw(shader)


def _draw_callback():
    if not _persistent_objects and not _temp_entries:
        return

    try:
        shader = _get_shader()
        if shader is None:
            return

        context = bpy.context
        now = time.time()

        gpu.state.blend_set("ALPHA")
        # 预览贴片始终绘制在灯光辅助线之上，避免被灯光 gizmo 遮挡。
        gpu.state.depth_test_set("NONE")

        for name in list(_persistent_objects):
            obj = _get_area_light(name)
            if obj is None:
                _persistent_objects.discard(name)
                continue
            if not _is_light_visible(context, obj):
                continue
            texture = _get_texture_for(obj)
            if texture is not None:
                _draw_preview_plane(shader, obj, texture, 1.0)

        for name, start_time in list(_temp_entries.items()):
            obj = _get_area_light(name)
            if obj is None:
                _temp_entries.pop(name, None)
                continue
            alpha = _temp_alpha(start_time, now)
            if alpha <= 0.0 or not _is_light_visible(context, obj):
                continue
            texture = _get_texture_for(obj)
            if texture is not None:
                _draw_preview_plane(shader, obj, texture, alpha)

    except ReferenceError:
        pass
    except Exception:
        traceback.print_exc()
    finally:
        try:
            gpu.state.blend_set("NONE")
            gpu.state.depth_test_set("LESS_EQUAL")
        except Exception:
            pass


def _ensure_draw_handler():
    global _draw_handler
    if _draw_handler is not None:
        return
    try:
        _draw_handler = bpy.types.SpaceView3D.draw_handler_add(
            _draw_callback, (), "WINDOW", "POST_VIEW"
        )
    except Exception:
        traceback.print_exc()
        _draw_handler = None


def _remove_draw_handler():
    global _draw_handler
    if _draw_handler is None:
        return
    try:
        bpy.types.SpaceView3D.draw_handler_remove(_draw_handler, "WINDOW")
    except Exception:
        pass
    _draw_handler = None


def _update_temp_previews():
    try:
        now = time.time()
        total_seconds = TEMP_HOLD_SECONDS + TEMP_FADE_SECONDS
        expired = [
            name for name, start_time in _temp_entries.items()
            if now - start_time >= total_seconds
        ]
        for name in expired:
            _temp_entries.pop(name, None)

        _tag_redraw_all_3dviews()
        if _temp_entries:
            return TIMER_INTERVAL

        if not _persistent_objects:
            _remove_draw_handler()
        return None
    except Exception:
        traceback.print_exc()
        _temp_entries.clear()
        if not _persistent_objects:
            _remove_draw_handler()
        return None


def _ensure_timer():
    if not bpy.app.timers.is_registered(_update_temp_previews):
        bpy.app.timers.register(_update_temp_previews, first_interval=TIMER_INTERVAL)


def _stop_timer():
    if bpy.app.timers.is_registered(_update_temp_previews):
        try:
            bpy.app.timers.unregister(_update_temp_previews)
        except Exception:
            pass


def _reset_state():
    global _shader
    _persistent_objects.clear()
    _temp_entries.clear()
    _stop_timer()
    _remove_draw_handler()
    TexturePool.clear()
    _shader = None


@persistent
def _on_load_post(_dummy):
    _reset_state()


class BetterExperie_OT_TempPreviewAreaLight(bpy.types.Operator):
    bl_idname = "better_experie.temp_preview_area_light"
    bl_label = "临时预览"
    bl_description = "重新生成所选区域光的预览图，停留 3 秒后用 1 秒渐隐"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        return bool(get_selected_area_lights(context))

    def execute(self, context):
        selected_lights = get_selected_area_lights(context)
        if not selected_lights:
            self.report({'WARNING'}, "请先选择区域光")
            return {'CANCELLED'}

        try:
            ensure_temp_dir()
            success_paths, failed_items = _build_previews(context, selected_lights)
        except Exception as exc:
            self.report({'ERROR'}, f"预览生成失败：{exc}")
            return {'CANCELLED'}

        now = time.time()
        shown_count = 0
        for obj in selected_lights:
            preview_path = str(get_preview_path(obj.data).resolve())
            if preview_path not in success_paths:
                continue
            # 临时预览结束后不留常驻贴片，需要常驻请使用【新建/刷新】。
            _persistent_objects.discard(obj.name)
            _temp_entries[obj.name] = now
            shown_count += 1

        if shown_count:
            _ensure_draw_handler()
            if _draw_handler is None:
                self.report({'ERROR'}, "无法注册视口绘制回调")
                return {'CANCELLED'}
            _ensure_timer()
            _tag_redraw_all_3dviews()

        if failed_items:
            for item in failed_items:
                print(f"[Area Light Preview] {item}")
            self.report(
                {'WARNING'},
                f"已显示 {shown_count} 盏区域光，失败 {len(failed_items)} 盏",
            )
        else:
            self.report(
                {'INFO'},
                f"已临时预览 {shown_count} 盏区域光（停留 {TEMP_HOLD_SECONDS:g} 秒后渐隐）",
            )

        return {'FINISHED'} if shown_count else {'CANCELLED'}


class BetterExperie_OT_BuildAreaLightPreview(bpy.types.Operator):
    bl_idname = "better_experie.build_area_light_preview"
    bl_label = "新建/刷新"
    bl_description = "为所选区域光新建或刷新预览图，并在视口中常驻显示"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        return bool(get_selected_area_lights(context))

    def execute(self, context):
        selected_lights = get_selected_area_lights(context)
        if not selected_lights:
            self.report({'WARNING'}, "请先选择区域光")
            return {'CANCELLED'}

        try:
            ensure_temp_dir()
            success_paths, failed_items = _build_previews(context, selected_lights)
        except Exception as exc:
            self.report({'ERROR'}, f"预览生成失败：{exc}")
            return {'CANCELLED'}

        shown_count = 0
        for obj in selected_lights:
            preview_path = str(get_preview_path(obj.data).resolve())
            if preview_path not in success_paths:
                continue
            _temp_entries.pop(obj.name, None)
            _persistent_objects.add(obj.name)
            shown_count += 1

        if shown_count:
            _ensure_draw_handler()
            if _draw_handler is None:
                self.report({'ERROR'}, "无法注册视口绘制回调")
                return {'CANCELLED'}
            _tag_redraw_all_3dviews()

        if failed_items:
            for item in failed_items:
                print(f"[Area Light Preview] {item}")
            self.report(
                {'WARNING'},
                f"已生成/刷新 {shown_count} 张预览图，失败 {len(failed_items)} 张",
            )
        else:
            self.report({'INFO'}, f"已生成/刷新 {shown_count} 张灯光预览图")

        return {'FINISHED'} if shown_count else {'CANCELLED'}


class BetterExperie_OT_ClearAreaLightPreview(bpy.types.Operator):
    bl_idname = "better_experie.clear_area_light_preview"
    bl_label = "清理灯光"
    bl_description = "删除所选区域光的预览图与 GPU 缓存，并清理已删除灯光遗留的预览文件"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        # 即使没有选中灯光，也允许清理已删除灯光留下的无主缓存。
        return True

    def execute(self, context):
        try:
            ensure_temp_dir()
        except Exception as exc:
            self.report({'ERROR'}, f"无法访问预览缓存目录：{exc}")
            return {'CANCELLED'}

        selected_lights = get_selected_area_lights(context)
        unique_data = {}
        for obj in selected_lights:
            unique_data[obj.data.as_pointer()] = obj.data

        removed_selected_count = 0
        for light_data in unique_data.values():
            preview_path = get_preview_path(light_data)
            TexturePool.invalidate(preview_path)
            if preview_path.exists():
                try:
                    preview_path.unlink()
                    removed_selected_count += 1
                except Exception as exc:
                    print(f"[Area Light Preview] 删除失败: {preview_path}, {exc}")

        # 清理所选灯光的显示状态。
        for obj in selected_lights:
            _persistent_objects.discard(obj.name)
            _temp_entries.pop(obj.name, None)

        # 清理已删除灯光遗留的显示状态。
        for name in list(_persistent_objects):
            if bpy.data.objects.get(name) is None:
                _persistent_objects.discard(name)
        for name in list(_temp_entries):
            if bpy.data.objects.get(name) is None:
                _temp_entries.pop(name, None)

        # 建立当前仍然有效的区域光预览路径集合。
        valid_preview_paths = set()
        for obj in bpy.data.objects:
            if obj.type != "LIGHT" or not obj.data or obj.data.type != "AREA":
                continue
            valid_preview_paths.add(str(get_preview_path(obj.data).resolve()))

        # 删除临时目录内没有被任何现存区域光使用的 BMP。
        for preview_path in TEMP_DIR.glob("*.bmp"):
            resolved_path = str(preview_path.resolve())
            if resolved_path in valid_preview_paths:
                continue
            TexturePool.invalidate(preview_path)
            try:
                preview_path.unlink()
            except Exception as exc:
                print(f"[Area Light Preview] 删除无主缓存失败: {preview_path}, {exc}")

        # 清理磁盘文件已不存在、或不再有区域光对应的 GPUTexture。
        for texture_path in list(TexturePool.TEXTURE_MAP.keys()):
            file_exists = Path(texture_path).exists()
            is_valid_light_preview = texture_path in valid_preview_paths
            if file_exists and is_valid_light_preview:
                continue
            TexturePool.TEXTURE_MAP.pop(texture_path, None)

        if not _temp_entries and not _persistent_objects:
            _stop_timer()
            _remove_draw_handler()

        _tag_redraw_all_3dviews()
        self.report({'INFO'}, f"已清理所选 {removed_selected_count} 张预览图")
        return {'FINISHED'}


classes = (
    BetterExperie_OT_TempPreviewAreaLight,
    BetterExperie_OT_BuildAreaLightPreview,
    BetterExperie_OT_ClearAreaLightPreview,
)


def register():
    _reset_state()

    for cls in classes:
        bpy.utils.register_class(cls)

    if _on_load_post not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(_on_load_post)

    try:
        ensure_temp_dir()
    except Exception:
        traceback.print_exc()


def unregister():
    _reset_state()

    if _on_load_post in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_on_load_post)

    for cls in reversed(classes):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass
