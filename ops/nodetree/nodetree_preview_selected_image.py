#快速预览所选图像
#https://docs.blender.org/api/current/gpu.types.html#gpu.types.GPUTexture
#https://developer.blender.org/docs/features/gpu/glsl_cross_compilation/
#尝试重构为使用glsl

import bpy 
import gpu 
from gpu_extras.batch import batch_for_shader 

class BetterExperie_OT_PreviewImageModal(bpy.types.Operator):
    bl_idname = "better_experie.preview_image_modal"
    bl_label = "预览图像节点（ESC 退出）"
    bl_description = "在节点编辑器中全屏预览选中的图像节点"
    bl_options = {'REGISTER', 'UNDO', 'BLOCKING'}

    # 所有状态变量直接作为类的实例属性
    draw_handle = None
    draw_running = False
    view_scale = 1.0
    view_offset = [0.0, 0.0]
    region_width = 0
    region_height = 0
    mouse_x_screen = 0
    mouse_y_screen = 0
    is_panning = False
    mouse_in_image_uv = (0, 0)
    preview_image = None

    def get_image_screen_rect(self):
        #计算图像在屏幕上的显示矩形区域
        if not self.preview_image:
            return None
            
        image_width, image_height = self.preview_image.size
        if image_width == 0 or image_height == 0:
            return None
            
        # 计算初始缩放比例，使图像适应区域的 90%
        base_scale_x = (self.region_width * 0.9) / image_width if image_width > 0 else 1.0
        base_scale_y = (self.region_height * 0.9) / image_height if image_height > 0 else 1.0
        base_scale = min(base_scale_x, base_scale_y)
         
        # 应用当前视图缩放
        scale = base_scale * self.view_scale

        width = image_width * scale
        height = image_height * scale

        # 计算图像在屏幕上的起始位置 (居中 + 偏移)
        x = (self.region_width - width) * 0.5 + self.view_offset[0]
        y = (self.region_height - height) * 0.5 + self.view_offset[1]
        return x, y, width, height

    def update_uv_and_mouse_site(self):
        #更新鼠标位置和UV坐标信息
        rect = self.get_image_screen_rect()
        if not rect:
            return
        # self.image_screen_rect = rect
        x, y, w, h = rect
        mx = self.mouse_x_screen
        my = self.mouse_y_screen
        
        # 检查鼠标是否在图像显示区域内
        # self.is_mouse_over_image = (x <= mx <= x + w and y <= my <= y + h)
        
        # 计算UV坐标
        # if self.is_mouse_over_image:
        u = (mx - x) / w
        v = (my - y) / h
        self.mouse_in_image_uv = (u, v)


    def draw_image_callback(self):
        #GPU绘制回调函数
        if not self.draw_running or not self.preview_image:
            return

        # 获取图像显示区域
        rect = self.get_image_screen_rect()
        if not rect:
            return
        x, y, w, h = rect

        # 绘制图像
        shader = gpu.shader.from_builtin('IMAGE_SCENE_LINEAR_TO_REC709_SRGB')
        texture = gpu.texture.from_image(self.preview_image)
        
        # 定义顶点和UV坐标
        coords = [(x, y), (x + w, y), (x, y + h), (x + w, y + h)]
        uvs = [(0, 0), (1, 0), (0, 1), (1, 1)]

        # 创建并绘制批次
        batch = batch_for_shader(shader, "TRI_STRIP", {"pos": coords, "texCoord": uvs})
        gpu.state.blend_set("ALPHA")
        gpu.state.depth_test_set('NONE')

        shader.bind()
        shader.uniform_sampler("image", texture)
        batch.draw(shader)

    def start_preview(self, context):
        # 注册绘制句柄
        self.draw_handle = bpy.types.SpaceNodeEditor.draw_handler_add(
            self.draw_image_callback,
            (),
            "WINDOW",
            "POST_PIXEL",
        )
        self.draw_running = True
        context.area.tag_redraw()

    def stop_preview(self):
        #停止图像预览
        if self.draw_handle:
            bpy.types.SpaceNodeEditor.draw_handler_remove(self.draw_handle, "WINDOW")
            self.draw_handle = None
        self.draw_running = False

    def invoke(self, context, event):
        try:
            # 重置所有状态
            self.draw_handle = None
            self.draw_running = False
            self.view_scale = 1.0
            self.view_offset = [0.0, 0.0]

            # 检查是否在节点编辑器中
            if context.area.type != 'NODE_EDITOR':
                self.report({'WARNING'}, "请在节点编辑器中运行此操作符。")
                return {'CANCELLED'}

            # 获取活动节点和图像
            node = context.active_node
            node_tree = context.space_data.node_tree 
            
            if not node:
                self.report({"WARNING"}, "请选择一个图像节点。")
                return {"CANCELLED"}

            # 获取区域尺寸
            region = context.region
            self.region_width = region.width
            self.region_height = region.height

            # 获取节点中的图像
            image = None
            if hasattr(node, "image") and node.image:
                image = node.image
            else:
                self.report({"WARNING"}, "节点上未找到图像数据。")
                return {"CANCELLED"}

            if not image:
                self.report({"WARNING"}, "所选节点不包含有效图像。")
                return {"CANCELLED"}
            # 存储关键数据
            self.preview_image = image

            # 启动预览
            self.start_preview(context)
            context.window_manager.modal_handler_add(self)
            context.workspace.status_text_set(
                "图像预览 | 中键拖拽平移 | 滚轮缩放 | 右键/ESC退出")
            return {"RUNNING_MODAL"}
        except Exception:
            import traceback
            traceback.print_exc()
            self.stop_preview()
            try:
                if context and context.workspace:
                    context.workspace.status_text_set(None)
            except Exception:
                pass
            return {"CANCELLED"}

    def modal(self, context, event):
        #模态事件处理
        try:
            # 更新区域和鼠标信息
            region = context.region
            if region:
                self.region_width = region.width
                self.region_height = region.height
            self.mouse_x_screen = event.mouse_region_x
            self.mouse_y_screen = event.mouse_region_y
            self.update_uv_and_mouse_site()

            # --- ESC 键: 退出预览 ---
            if event.type in {"ESC","RIGHTMOUSE"}:
                self.report({'INFO'}, "图像预览结束")
                self.stop_preview()
                if context and context.workspace:
                    context.workspace.status_text_set(None)
                context.area.tag_redraw()
                return {"FINISHED"}

            # --- 中键拖移 (平移) ---
            if event.type == "MIDDLEMOUSE":
                if event.value == "PRESS":
                    self.is_panning = True
                    self.last_mouse = (event.mouse_region_x, event.mouse_region_y)
                    return {"RUNNING_MODAL"}
                elif event.value == "RELEASE":
                    self.is_panning = False
                    return {"RUNNING_MODAL"}

            # --- 鼠标移动事件 ---
            if event.type == "MOUSEMOVE":
                # 处理平移
                if self.is_panning:
                    mx, my = event.mouse_region_x, event.mouse_region_y
                    lx, ly = self.last_mouse
                    # 计算偏移量
                    dx = mx - lx
                    dy = my - ly
                    self.view_offset = [self.view_offset[0] + dx, self.view_offset[1] + dy]
                    self.last_mouse = (mx, my)

                    context.area.tag_redraw()
                return {"RUNNING_MODAL"}

            # --- 滚轮缩放 ---
            if event.type in {"WHEELUPMOUSE", "WHEELDOWNMOUSE"} and not (event.shift or event.ctrl):
                factor = 1.1 if event.type == "WHEELUPMOUSE" else 1 / 1.1

                rect = self.get_image_screen_rect()
                if not rect:
                    return {"RUNNING_MODAL"}
                # self.image_screen_rect = rect
                x, y, w, h = rect
                mx = self.mouse_x_screen
                my = self.mouse_y_screen

                # 计算UV坐标
                u = (mx - x) / w
                v = (my - y) / h

                #设置视图缩放比例（以鼠标为中心）
                x0, y0, w0, h0 = self.get_image_screen_rect()

                # 限制缩放范围
                MAX_SCALE = 50.0
                MIN_SCALE = 0.05
                new_scale = max(MIN_SCALE, min(self.view_scale * factor, MAX_SCALE))

                # 先更新缩放比例
                self.view_scale = new_scale

                # 计算缩放后的位置
                x1, y1, w1, h1 = self.get_image_screen_rect()

                # 保持鼠标下的像素位置不变
                if x0 and x1:
                    px_before = x0 + u * w0
                    py_before = y0 + v * h0
                    px_after = x1 + u * w1
                    py_after = y1 + v * h1

                    self.view_offset[0] += px_before - px_after
                    self.view_offset[1] += py_before - py_after

                context.area.tag_redraw()
                return {"RUNNING_MODAL"}

            # --- Home 键：视图复位 ---
            if event.type == 'HOME' and event.value == 'PRESS':
                self.view_scale = 1.0
                self.view_offset = [0.0, 0.0]
                context.area.tag_redraw()
                return {'RUNNING_MODAL'}

            return {"RUNNING_MODAL"}
        except Exception:
            import traceback
            traceback.print_exc()
            self.stop_preview()
            try:
                if context and context.workspace:
                    context.workspace.status_text_set(None)
            except Exception:
                pass
            return {"CANCELLED"}


classes = (
    BetterExperie_OT_PreviewImageModal,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
