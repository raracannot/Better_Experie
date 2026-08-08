
# blender-5.0.0-windows-x64\5.0\scripts\addons_core\node_wrangler\utils

bl_info = {
    "name": "[test]Compositor Node Baker",
    "author": "RARA",
    "version": (1, 6),
    "blender": (3, 0, 0),
    "location": "Node Editor > Sidebar > 测试",
    "description": "在合成器中烘焙当前活动节点为图像或导出到硬盘",
    "category": "Compositing",
}

import bpy
import os
import time
import numpy as np
from bpy.props import StringProperty, EnumProperty

def get_viewer_image():
    img = bpy.data.images.get('Viewer Node')
    if img and img.source == 'VIEWER' and sum(img.size) > 0:
        return img
    for img in bpy.data.images:
        if img.source == 'VIEWER' and len(img.render_slots) == 0 and sum(img.size) > 0:
            return img
    return None

def get_image_pixels_np(img):
    if not img or img.size[0] == 0 or img.size[1] == 0:
        return None
    total_pixels = img.size[0] * img.size[1] * 4
    pixels_array = np.zeros(total_pixels, dtype=np.float32)
    img.pixels.foreach_get(pixels_array)
    return pixels_array

class BetterExperie_OT_CompositorBakeNode(bpy.types.Operator):
    bl_idname = "better_experie.compositor_bake_node"
    bl_label = "处理节点"
    bl_description = "烘焙合成器节点到内存或导出为图像文件"
    bl_options = {'REGISTER', 'UNDO'}

    # 用于区分当前点击的是哪个按钮
    action_type: EnumProperty(
        items=[
            ('BAKE', "烘焙到内存", ""),
            ('EXPORT', "导出到硬盘", "")
        ],
        default='BAKE'
    )

    # 导出相关属性
    filepath: StringProperty(subtype="FILE_PATH")
    filename_ext: EnumProperty(
        name="Format",
        description="选择要保存的文件格式",
        items=(
            ('.bmp', "BMP", ""), ('.rgb', 'IRIS', ""), ('.png', 'PNG', ""),
            ('.jpg', 'JPEG', ""), ('.jp2', 'JPEG2000', ""), ('.tga', 'TARGA', ""),
            ('.cin', 'CINEON', ""), ('.dpx', 'DPX', ""), ('.exr', 'OPEN_EXR', ""),
            ('.hdr', 'HDR', ""), ('.tif', 'TIFF', ""), ('.webp', 'WEBP', ""),
        ),
        default='.png',
    )

    FORMAT_MAP = {
        '.bmp': 'BMP', '.rgb': 'IRIS', '.png': 'PNG', '.jpg': 'JPEG',
        '.jp2': 'JPEG2000', '.tga': 'TARGA', '.cin': 'CINEON', '.dpx': 'DPX',
        '.exr': 'OPEN_EXR', '.hdr': 'HDR', '.tif': 'TIFF', '.webp': 'WEBP'
    }

    _timer = None
    _start_time = 0
    _state = 'WAITING'
    _old_pixels_subset = None
    _last_pixels_subset = None
    _stable_start_time = 0
    _stable_duration = 0.8
    _timeout = 10.0

    @classmethod
    def poll(cls, context):
        space = context.space_data
        return space.type == 'NODE_EDITOR' and space.tree_type == 'CompositorNodeTree'

    def draw(self, context):
        # 只有在导出模式下（文件浏览器中）才绘制格式选择
        if self.action_type == 'EXPORT':
            layout = self.layout
            layout.use_property_split = True
            layout.use_property_decorate = False
            
            # 这里只画 filename_ext，不画 action_type
            layout.prop(self, "filename_ext", text="图片格式")

    def invoke(self, context, event):
        self.tree = context.space_data.edit_tree
        if not self.tree:
            return {'CANCELLED'}
        self.original_active_node = self.tree.nodes.active
        if not self.original_active_node or not self.original_active_node.outputs:
            self.report({'WARNING'}, "请选择一个带有输出端口的活动节点")
            return {'CANCELLED'}

        # 根据 action_type 决定是否弹窗
        if self.action_type == 'EXPORT':
            self.filepath = f"baked_{self.original_active_node.name}{self.filename_ext}"
            context.window_manager.fileselect_add(self)
            return {'RUNNING_MODAL'}
        else:
            self.setup_viewer_and_timer(context)
            return {'RUNNING_MODAL'}

    def execute(self, context):
        # 只有在弹窗点击“确认”后才会触发 execute
        if self.action_type == 'EXPORT':
            if not self.filepath.lower().endswith(self.filename_ext):
                self.filepath += self.filename_ext
            self.setup_viewer_and_timer(context)
            return {'RUNNING_MODAL'}
        return {'FINISHED'}

    def setup_viewer_and_timer(self, context):
        self.viewer_img = get_viewer_image()
        old_pixels = get_image_pixels_np(self.viewer_img)
        self._old_pixels_subset = old_pixels[::1000] if old_pixels is not None else None

        self._state = 'WAITING'
        self._last_pixels_subset = self._old_pixels_subset
        self._stable_start_time = 0

        self.new_viewer = self.tree.nodes.new(type='CompositorNodeViewer')
        self.new_viewer.location = (self.original_active_node.location.x + 200, self.original_active_node.location.y)
        
        output_socket = next((out for out in self.original_active_node.outputs if out.enabled and not out.hide), self.original_active_node.outputs[0])
        self.tree.links.new(output_socket, self.new_viewer.inputs[0])

        self.tree.nodes.active = self.new_viewer
        bpy.ops.node.activate_viewer()

        self._start_time = time.time()
        self._timer = context.window_manager.event_timer_add(0.3, window=context.window)
        context.window_manager.modal_handler_add(self)
        context.window.cursor_modal_set('WAIT')

    def modal(self, context, event):
        try:
            if event.type == 'TIMER':
                is_ready = False
                current_time = time.time()
                current_pixels = get_image_pixels_np(self.viewer_img)
                
                if current_pixels is not None:
                    current_pixels_subset = current_pixels[::1000]
                    if self._state == 'WAITING':
                        if self._old_pixels_subset is None or len(current_pixels_subset) != len(self._old_pixels_subset) or not np.array_equal(current_pixels_subset, self._old_pixels_subset):
                            self._state = 'RENDERING'
                            self._last_pixels_subset = current_pixels_subset
                            self._stable_start_time = current_time
                            self.report({'INFO'}, "等待生成")
                        else:
                            if (current_time - self._start_time) >= self._stable_duration:
                                self.report({'INFO'}, "画面无变化或已秒出，直接固化")
                                is_ready = True
                    elif self._state == 'RENDERING':
                        self.report({'INFO'}, "快速生成中")
                        if len(current_pixels_subset) != len(self._last_pixels_subset) or not np.array_equal(current_pixels_subset, self._last_pixels_subset):
                            self._last_pixels_subset = current_pixels_subset
                            self._stable_start_time = current_time
                        else:
                            if (current_time - self._stable_start_time) >= self._stable_duration:
                                is_ready = True
                else:
                    self.viewer_img = get_viewer_image()
                    if self.viewer_img:
                        self._state = 'RENDERING'
                        self._stable_start_time = current_time

                if is_ready or (current_time - self._start_time > self._timeout):
                    elapsed_time = current_time - self._start_time
                    self.save_and_cleanup(context, elapsed_time)
                    context.window_manager.event_timer_remove(self._timer)
                    context.window.cursor_modal_restore()
                    return {'FINISHED'}

            return {'PASS_THROUGH'}
        except Exception:
            import traceback
            traceback.print_exc()
            # 异常时跳过保存、只做清理，避免写出残缺文件
            try:
                if self._timer:
                    context.window_manager.event_timer_remove(self._timer)
            except Exception:
                pass
            try:
                context.window.cursor_modal_restore()
            except Exception:
                pass
            try:
                if getattr(self, 'new_viewer', None):
                    self.tree.nodes.remove(self.new_viewer)
            except Exception:
                pass
            try:
                if getattr(self, 'tree', None) and getattr(self, 'original_active_node', None):
                    self.tree.nodes.active = self.original_active_node
            except Exception:
                pass
            return {'CANCELLED'}

    def save_and_cleanup(self, context, elapsed_time=0.0):
        if not self.viewer_img:
            self.tree.nodes.remove(self.new_viewer)
            return

        # ---------------- 分支 1：内存烘焙 ----------------
        if self.action_type == 'BAKE':
            width, height = self.viewer_img.size
            if width == 0 or height == 0:
                self.tree.nodes.remove(self.new_viewer)
                return

            baked_name = f"Baked_{self.original_active_node.name}"
            new_img = bpy.data.images.new(name=baked_name, width=width, height=height, alpha=True, float_buffer=True)
            
            total_pixels = width * height * 4
            pixels_array = np.zeros(total_pixels, dtype=np.float32)
            self.viewer_img.pixels.foreach_get(pixels_array)
            new_img.pixels.foreach_set(pixels_array)
            new_img.update()
            new_img.pack()

            image_node = self.tree.nodes.new(type='CompositorNodeImage')
            image_node.image = new_img
            image_node.name = baked_name
            image_node.label = baked_name
            self.report({'INFO'}, f"已烘焙到内存 (耗时: {elapsed_time:.2f}秒)")

        # ---------------- 分支 2：硬盘导出 ----------------
        elif self.action_type == 'EXPORT':
            image_settings = context.scene.render.image_settings
            old_media_type = image_settings.media_type
            old_file_format = image_settings.file_format
            view_settings = context.scene.view_settings
            old_view_transform = view_settings.view_transform
            # bpy.context.scene.render.image_settings.color_mode = 'RGBA'

            image_settings.media_type = 'IMAGE'
            image_settings.file_format = self.FORMAT_MAP.get(self.filename_ext, 'PNG')
            view_settings.view_transform = 'Standard'
            
            try:
                self.viewer_img.save_render(self.filepath)
                self.report({'INFO'}, f"已导出到硬盘 (耗时: {elapsed_time:.2f}秒): {self.filepath}")
            except RuntimeError as e:
                self.report({'ERROR'}, f"无法写入图像: {e}")
            finally:
                image_settings.media_type = old_media_type
                image_settings.file_format = old_file_format
                view_settings.view_transform = old_view_transform

            loaded_img = bpy.data.images.load(self.filepath)
            image_node = self.tree.nodes.new(type='CompositorNodeImage')
            image_node.image = loaded_img
            image_node.name = f"Exported_{self.original_active_node.name}"
            image_node.label = f"Exported {self.original_active_node.name}"

        # ---------------- 共同清理逻辑 ----------------
        image_node.location = (self.original_active_node.location.x + 200, self.original_active_node.location.y)
        self.tree.nodes.remove(self.new_viewer)
        self.tree.nodes.active = self.original_active_node


classes = (
    BetterExperie_OT_CompositorBakeNode,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

if __name__ == "__main__":
    register()
