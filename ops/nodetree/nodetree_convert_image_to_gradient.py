# 图片转颜色渐变条

import bpy 
import gpu 
import blf
from gpu_extras.batch import batch_for_shader 

import random
import math
import numpy as np

TEMP_MATERIAL = "TEMP_MATERIAL"
IS_RUNNING = False

####################################################################################################
# 读取剪贴板为图像
def import_image_from_clipboard() -> bpy.types.Image | None:
    """
    从系统剪贴板导入图像到Blender（无界面干扰版）
    临时切换到图像编辑器执行剪贴板粘贴操作，粘贴完成后自动恢复原始界面状态，
    返回:
        bpy.types.Image | None: 成功返回新创建的Blender图像对象，失败返回None
    """
    # 保存当前界面状态（核心：避免修改用户的界面布局）
    area = bpy.context.area
    if not area:
        raise ValueError("错误：无可用的界面区域")
        
    old_ui_type = area.ui_type
    area.ui_type = 'IMAGE_EDITOR'
    # 保存图像编辑器的原始图像状态
    space = area.spaces.active
    old_image = space.image  
    
    try: # 核心操作：粘贴剪贴板图像
        bpy.ops.image.clipboard_paste()
    except: # 粘贴失败：恢复所有原始状态并返回None
        space.image = old_image  
        area.ui_type = old_ui_type  
        return None
        
    # 粘贴成功：获取新创建的剪贴板图像
    clipboard_image = space.image  # 粘贴后，编辑器显示的就是新图像
    clipboard_image.pack()  # 将图像数据嵌入Blender文件（避免外部依赖）
    # 恢复原始界面状态（不干扰用户操作）
    space.image = old_image  # 切回编辑器原本的图像
    area.ui_type = old_ui_type  # 切回原本的界面类型
    # 返回新创建的剪贴板图像对象
    return clipboard_image    
    
####################################################################################################
# 通用工具函数：Blender图像 ↔ Numpy数组
def blimg_2_npimg(blender_image: bpy.types.Image) -> np.ndarray:
    if not isinstance(blender_image, bpy.types.Image):
        raise TypeError("输入必须是Blender图像对象（bpy.types.Image）")
    img_w, img_h = blender_image.size
    pixel_flat = np.empty(img_w * img_h * 4, dtype=np.float32)
    blender_image.pixels.foreach_get(pixel_flat)
    np_image = pixel_flat.reshape((img_h, img_w, 4))
    return np_image

def npimg_2_blimg(np_image: np.ndarray, image_name: str, overwrite: bool = True) -> bpy.types.Image:
    if np_image.dtype != np.float32:
        np_image = np_image.astype(np.float32)
    if np_image.shape[-1] != 4:
        raise ValueError(f"仅支持RGBA四通道！当前通道数：{np_image.shape[-1]}（要求：4）")
    h, w = np_image.shape[:2]
    np_image = np.clip(np_image, 0.0, 1.0)
    if overwrite and image_name in bpy.data.images:
        old_image = bpy.data.images[image_name]
        old_image.user_clear()
        bpy.data.images.remove(old_image)
    bl_image = bpy.data.images.new(name=image_name, width=w, height=h, alpha=True)
    bl_image.pixels.foreach_set(np_image.ravel())
    bl_image.update()
    bl_image.pack()
    return bl_image

# 智能缩放函数
def np_resize_img(img_data, target_w, target_h) -> np.ndarray:
    if img_data.ndim != 3 or img_data.shape[-1] != 4:
        raise ValueError(f"仅支持RGBA四通道数组！当前形状：{img_data.shape}（要求：(H,W,4)）")
    if img_data.dtype != np.float32:
        img_data = img_data.astype(np.float32)

    h_ori, w_ori = img_data.shape[:2]
    target_h = int(round(target_h))
    target_w = int(round(target_w))

    y_target = np.linspace(0, h_ori - 1, target_h, dtype=np.float32)
    x_target = np.linspace(0, w_ori - 1, target_w, dtype=np.float32)
    x_grid, y_grid = np.meshgrid(x_target, y_target)

    x0 = np.floor(x_grid).astype(np.int32)
    x1 = np.minimum(x0 + 1, w_ori - 1)
    y0 = np.floor(y_grid).astype(np.int32)
    y1 = np.minimum(y0 + 1, h_ori - 1)

    dx = x_grid - x0
    dy = y_grid - y0

    val00 = img_data[y0, x0, :]
    val01 = img_data[y0, x1, :]
    val10 = img_data[y1, x0, :]
    val11 = img_data[y1, x1, :]

    val_x0 = val00 * (1 - dx[..., np.newaxis]) + val01 * dx[..., np.newaxis]
    val_x1 = val10 * (1 - dx[..., np.newaxis]) + val11 * dx[..., np.newaxis]
    resized = val_x0 * (1 - dy[..., np.newaxis]) + val_x1 * dy[..., np.newaxis]

    resized = resized.astype(np.float32)
    resized = np.clip(resized, 0.0, 1.0)
    return resized

def np_clamp_image_size(np_image: np.ndarray, max_side: float | int = 1024) -> np.ndarray:
    if np_image.ndim != 3 or np_image.shape[-1] != 4:
        raise ValueError(f"仅支持RGBA四通道数组！当前形状：{np_image.shape}（要求：(H,W,4)）")
    if np_image.dtype != np.float32:
        np_image = np_image.astype(np.float32)

    max_side = max(int(round(max_side)), 1)
    h_ori, w_ori = np_image.shape[:2]
    current_max_side = max(h_ori, w_ori)

    if current_max_side <= max_side:
        return np_image.copy()

    scale_ratio = max_side / current_max_side
    target_w = int(round(w_ori * scale_ratio))
    target_h = int(round(h_ori * scale_ratio))
    resized_image = np_resize_img(np_image, target_w, target_h)
    return resized_image

def clear_ramp(ramp):
    if not ramp or not hasattr(ramp, "elements"):
        return
    while len(ramp.elements) > 1:
        ramp.elements.remove(ramp.elements[1])

def get_selected_ramps(context):
    ramps = []
    # 全版本兼容：获取材质节点树
    if TEMP_MATERIAL in bpy.data.materials:
        mat = bpy.data.materials[TEMP_MATERIAL]
        if mat.node_tree:
            for node in mat.node_tree.nodes:
                if hasattr(node, "color_ramp"):
                    ramps.append(node.color_ramp)
        return ramps

    if context.space_data.type != 'NODE_EDITOR':
        return ramps
        
    for node in context.selected_nodes:
        if hasattr(node, "color_ramp"):
            ramps.append(node.color_ramp)
    return ramps

def apply_ramp(ramp, new_ramp):
    if not isinstance(new_ramp, list) or len(new_ramp) == 0:
        return
    
    cleaned = []
    for item in new_ramp:
        try:
            pos, col = item
            pos = max(0.0, min(1.0, float(pos)))
            r = max(0.0, min(1.0, float(col[0])))
            g = max(0.0, min(1.0, float(col[1])))
            b = max(0.0, min(1.0, float(col[2])))
            a = max(0.0, min(1.0, float(col[3])))
            cleaned.append((pos, (r, g, b, a)))
        except:
            continue
    if len(cleaned) == 0:
        return
        
    cleaned = cleaned[:32]        
    
    clear_ramp(ramp)
    first_pos, first_col = cleaned[0]
    ramp.elements[0].position = first_pos
    ramp.elements[0].color = first_col
    for pos, col in cleaned[1:]:
        elem = ramp.elements.new(pos)
        elem.color = col

def copy_color_ramp_node_to_node(source_node, target_node):
    if not hasattr(source_node, 'color_ramp') or not hasattr(target_node, 'color_ramp'):
        return
    
    src_ramp = source_node.color_ramp
    dst_ramp = target_node.color_ramp
    
    dst_ramp.color_mode = src_ramp.color_mode
    dst_ramp.interpolation = src_ramp.interpolation
    dst_ramp.hue_interpolation = src_ramp.hue_interpolation
    
    data = [(e.position, e.color) for e in src_ramp.elements]
    apply_ramp(dst_ramp, data)


# ======================
# RDP 道格拉斯普克算法（纯numpy）
# ======================
def rdp_simplify_curve(data, target_points=8):
    indices = [0, len(data)-1]
    points = data.copy()

    def distance(p, a, b):
        # 带颜色权重的垂直距离（视觉更准确）
        dx = b[0] - a[0]
        dy = b[1:] - a[1:]
        dpx = p[0] - a[0]
        dpy = p[1:] - a[1:]
        
        if dx < 1e-8:
            return np.sum(np.abs(dpy))
        
        t = dpx / dx
        proj = a + t * np.concatenate([[dx], dy])
        return np.sqrt(np.sum((p - proj)**2))

    # 迭代精简直到达到目标数量
    while len(indices) < target_points and len(indices) < len(points):
        max_dist = -1
        best_idx = -1

        for i in range(len(indices)-1):
            start = indices[i]
            end = indices[i+1]
            if end - start <= 1:
                continue
            
            segment = points[start:end+1]
            a = points[start]
            b = points[end]
            
            # 计算最大误差
            for j in range(1, len(segment)-1):
                p = segment[j]
                d = distance(p, a, b)
                if d > max_dist:
                    max_dist = d
                    best_idx = start + j

        if best_idx == -1:
            break
        indices.append(best_idx)
        indices = sorted(indices)

    return points[indices]
    
def calc_radius_by_distance(dist, min_dist, max_dist, base_radius, min_scale, max_scale):
    if dist < min_dist:
        return base_radius * max_scale
    if dist > max_dist:
        return base_radius * min_scale
    factor = 1.0 - (dist - min_dist) / (max_dist - min_dist)
    factor = max(0.0, min(1.0, factor))
    scale = min_scale + (max_scale - min_scale) * factor
    return base_radius * scale

def bottom_status_bar(self, context):
    layout = self.layout
    row = layout.row(align=True)
    
    row.label(text="" ,icon="EVENT_SHIFT")
    row.label(text="控制控制点" ,icon="MOUSE_LMB")
    row.label(text="添加控制点/采样点" ,icon="MOUSE_LMB")
    row.label(text="删除采样点" ,icon="MOUSE_RMB")
    row.label(text="调整画布" ,icon="MOUSE_MMB")
    row.label(text="生成渐变" ,icon="EVENT_RETURN")
    row.label(text="退出操作" ,icon="EVENT_ESC")
    
    row.separator(type="LINE")
    row.label(text="" ,icon="EVENT_ONEKEY")
    row.label(text="" ,icon="EVENT_TWOKEY")
    row.label(text="" ,icon="EVENT_THREEKEY")
    row.label(text="快速生成" ,icon="EVENT_FOURKEY")
    row.label(text="自动采样生成" ,icon="EVENT_A")
    row.label(text="锁定控制点" ,icon="EVENT_L")    
    row.label(text="均匀分布" ,icon="EVENT_F")
    row.label(text="删除点" ,icon="EVENT_X")
    row.label(text="显示提示" ,icon="EVENT_H")


####################################################################################################
# 优化完成版：图像采样生成渐变
class BetterExperie_ImageToGradient_BASE(bpy.types.Operator):
    # bl_idname = "cr.preview_image_modal"
    # bl_label = "依据图像生成渐变基类"

    # 基础状态
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
    control_locked = False  # 添加这一行
    show_hints = True  # 显示提示
    
    new_node_location = None
    preview_image = None
    np_thumbnail = None # 128*128缩略图numpy数据

    # 采样控制核心数据
    control_points = []       # 控制点 [uv1, uv2] 最多2个
    sample_points = []        # 采样点 [0~1 采样线系数]
    drag_target = None        # 拖动目标：control / sample
    drag_index = -1

    def get_image_screen_rect(self):
        if not self.preview_image:
            return None
        image_width, image_height = self.preview_image.size
        if image_width == 0 or image_height == 0:
            return None
            
        base_scale_x = (self.region_width * 0.9) / image_width
        base_scale_y = (self.region_height * 0.9) / image_height
        base_scale = min(base_scale_x, base_scale_y)
        scale = base_scale * self.view_scale

        width = image_width * scale
        height = image_height * scale
        x = (self.region_width - width) * 0.5 + self.view_offset[0]
        y = (self.region_height - height) * 0.5 + self.view_offset[1]
        return x, y, width, height

    def update_uv_and_mouse_site(self):
        rect = self.get_image_screen_rect()
        if not rect:
            return
        x, y, w, h = rect
        mx, my = self.mouse_x_screen, self.mouse_y_screen
        u = max(0, min(1, (mx - x) / w))
        v = max(0, min(1, (my - y) / h))
        self.mouse_in_image_uv = (u, v)

    def uv_to_screen(self, uv):
        rect = self.get_image_screen_rect()
        if not rect:
            return (0,0)
        x, y, w, h = rect
        sx = x + uv[0] * w
        sy = y + uv[1] * h
        return (sx, sy)

    def get_sample_line_points(self):
        if len(self.control_points) < 2:
            return []
        p0 = self.control_points[0]
        p1 = self.control_points[1]
        return p0, p1

    def get_closest_control_point(self, uv, threshold=0.02):
        closest = -1
        min_dist = 999
        for i, p in enumerate(self.control_points):
            dist = math.hypot(uv[0]-p[0], uv[1]-p[1])
            if dist < min_dist and dist < threshold:
                min_dist = dist
                closest = i
        return closest

    def get_closest_sample_point(self, t, threshold=0.03):
        closest = -1
        min_dist = 999
        for i, pt in enumerate(self.sample_points):
            dist = abs(pt - t)
            if dist < min_dist and dist < threshold:
                min_dist = dist
                closest = i
        return closest

    def uv_to_sample_t(self, uv):
        line = self.get_sample_line_points()
        if not line:
            return 0
        p0, p1 = line
        dx = p1[0] - p0[0]
        dy = p1[1] - p0[1]
        if abs(dx) < 0.0001 and abs(dy) < 0.0001:
            return 0.5
        t = ((uv[0]-p0[0])*dx + (uv[1]-p0[1])*dy) / (dx**2 + dy**2)
        return max(0, min(1, t))

    def t_to_uv(self, t):
        line = self.get_sample_line_points()
        if not line:
            return (0.5,0.5)
        p0, p1 = line
        u = p0[0] + t*(p1[0]-p0[0])
        v = p0[1] + t*(p1[1]-p0[1])
        return (u, v)

    def sample_color_from_thumbnail(self, uv):
        if self.np_thumbnail is None:
            return (1,1,1,1)
        h, w = self.np_thumbnail.shape[:2]
        x = int(uv[0] * (w-1))
        # 修复：上下翻转，解决颜色颠倒问题
        y = int(uv[1] * (h-1))
        x = max(0, min(w-1, x))
        y = max(0, min(h-1, y))
        return tuple(self.np_thumbnail[y, x].tolist())

    def draw_callback(self):
        if not self.draw_running or not self.preview_image:
            return
        # 绘制背景图像
        rect = self.get_image_screen_rect()
        if not rect:
            return
        x, y, w, h = rect
        shader = gpu.shader.from_builtin('IMAGE_SCENE_LINEAR_TO_REC709_SRGB')
        texture = gpu.texture.from_image(self.preview_image)
        coords = [(x, y), (x+w, y), (x, y+h), (x+w, y+h)]
        uvs = [(0,0), (1,0), (0,1), (1,1)]
        batch = batch_for_shader(shader, "TRI_STRIP", {"pos": coords, "texCoord": uvs})
        gpu.state.blend_set("ALPHA")
        gpu.state.depth_test_set('NONE')
        shader.bind()
        shader.uniform_sampler("image", texture)
        batch.draw(shader)

        # 2D着色器（绘制图形）
        shader_2d = gpu.shader.from_builtin('UNIFORM_COLOR')
        
        mx, my = self.mouse_x_screen, self.mouse_y_screen
        
        # 绘制采样线
        if len(self.control_points) == 2:
            p0 = self.uv_to_screen(self.control_points[0])
            p1 = self.uv_to_screen(self.control_points[1])
            coords = [p0, p1]
            batch = batch_for_shader(shader_2d, 'LINES', {"pos": coords})
            shader_2d.bind()
            if self.control_locked:
                shader_2d.uniform_float("color", (0.4, 0.4, 0.4, 0.8))
            else:
                shader_2d.uniform_float("color", (0, 0.6, 1, 0.8))
            gpu.state.line_width_set(2)
            batch.draw(shader_2d)
            
        # 绘制控制点（蓝色大圆点 + 中心 L/R 标记）
        for idx, p in enumerate(self.control_points):
            sx, sy = self.uv_to_screen(p)
            dist = math.hypot(sx - mx, sy - my)
            r = calc_radius_by_distance(
                dist=dist, min_dist=10, max_dist=20,
                base_radius=10, min_scale=1.0, max_scale=1.5)
            seg = 20
            verts = []
            for i in range(seg):
                a = math.pi * 2 * i / seg
                nx = sx + r * math.cos(a)
                ny = sy + r * math.sin(a)
                verts.append((nx, ny))
            batch = batch_for_shader(shader_2d, 'TRI_FAN', {"pos": verts})
            if self.control_locked:
                shader_2d.uniform_float("color", (0.3, 0.3, 0.3, 1))
            else:
                shader_2d.uniform_float("color", (0, 0.6, 1, 1))
            batch.draw(shader_2d)

            # ====================== 中心绘制 L / R 字母 ======================
            font_id = 0
            blf.size(font_id, 12)
            blf.color(font_id, 1, 1, 1, 1)
            text = "L" if idx == 0 else "R"
            text_w, text_h = blf.dimensions(font_id, text)
            blf.position(font_id, sx - text_w / 2, sy - text_h / 2, 0)
            blf.draw(font_id, text)

        # 绘制采样点（带白色外框 + 鼠标距离动态缩放）
        for t in self.sample_points:
            uv = self.t_to_uv(t)
            sx, sy = self.uv_to_screen(uv)
            dist = math.hypot(sx - mx, sy - my)
            r = calc_radius_by_distance(
                dist=dist,min_dist=6,max_dist=15,
                base_radius=6,min_scale=1.0,max_scale=1.5)
            seg = 16

            # 绘制白色外框
            outline_verts = []
            for i in range(seg + 1):
                a = math.pi * 2 * i / seg
                nx = sx + (r + 1) * math.cos(a)
                ny = sy + (r + 1) * math.sin(a)
                outline_verts.append((nx, ny))
            batch = batch_for_shader(shader_2d, 'LINE_LOOP', {"pos": outline_verts})
            shader_2d.uniform_float("color", (1, 1, 1, 1))
            batch.draw(shader_2d)

            # 绘制内部采样颜色
            inner_verts = [(sx + r*math.cos(math.pi*2*i/seg), sy + r*math.sin(math.pi*2*i/seg)) for i in range(seg)]
            batch = batch_for_shader(shader_2d, 'TRI_FAN', {"pos": inner_verts})
            color = self.sample_color_from_thumbnail(uv)
            shader_2d.uniform_float("color", color)
            batch.draw(shader_2d)
    
        if self.show_hints:
            font_id = 0
            blf.size(font_id, 14)
            blf.color(font_id, 1, 1, 1, 1)
            pad = 20

            # 第一行为控制点或采样点提示
            if len(self.control_points) < 2:
                blf.position(font_id, pad, pad, 0)
                blf.draw(font_id, "当前控制点小于2个，请点击左键，创建控制点")
            elif len(self.sample_points) < 1:
                blf.position(font_id, pad, pad, 0)
                blf.draw(font_id, "当前暂无采样点，请点击左键，创建采样点")
            elif len(self.sample_points) == 32:
                blf.position(font_id, pad, pad, 0)
                blf.draw(font_id, "当前累计32个采样点，已达系统最高上限")
            else:
                blf.position(font_id, pad, pad, 0)
                blf.draw(font_id, f"当前累计{len(self.sample_points)}个颜色采样点")
            
            # 实时鼠标颜色（直接在 draw 内计算，不依赖外部变量）
            ix, iy, iw, ih = rect
            if ix <= self.mouse_x_screen <= ix + iw and iy <= self.mouse_y_screen <= iy + ih:
                # 实时计算 UV → 实时取色
                u = (self.mouse_x_screen - ix) / iw
                v = (self.mouse_y_screen - iy) / ih
                u = max(0.0, min(1.0, u))
                v = max(0.0, min(1.0, v))
                r, g, b, a = self.sample_color_from_thumbnail((u, v))
                txt = f"颜色 R:{r:.3f}  G:{g:.3f}  B:{b:.3f}"
                blf.position(font_id, pad, pad + 20, 0)
                blf.draw(font_id, txt)

    def start_preview(self, context):
        self.draw_handle = bpy.types.SpaceNodeEditor.draw_handler_add(
            self.draw_callback, (), "WINDOW", "POST_PIXEL"
        )
        self.draw_running = True
        context.area.tag_redraw()

    def stop_preview(self):
        if self.draw_handle:
            bpy.types.SpaceNodeEditor.draw_handler_remove(self.draw_handle, "WINDOW")
            self.draw_handle = None
        self.draw_running = False
    
    def auto_sample_line(self, target_points=8):
        # 必须有两个控制点
        if len(self.control_points) != 2 or self.np_thumbnail is None:
            return False

        # 清空旧采样点
        self.sample_points.clear()
        p0, p1 = self.control_points[0], self.control_points[1]

        # 采样线上所有像素点（高密度）
        samples = []
        steps = 100
        for i in range(steps + 1):
            t = i / steps
            u = p0[0] + t * (p1[0] - p0[0])
            v = p0[1] + t * (p1[1] - p0[1])
            col = np.array(self.sample_color_from_thumbnail((u, v)))
            samples.append([t, *col])

        # RDP 精简到 8 个点
        samples = np.array(samples, dtype=np.float32)
        simplified = rdp_simplify_curve(samples, target_points)

        # 应用精简后的点
        for point in simplified:
            t = point[0]
            self.sample_points.append(float(t))

        self.sample_points.sort()
        return True

    def create_color_ramp(self, context):
        if len(self.sample_points) == 0:
            self.report({'INFO'}, "未采样任何点")
            return

        node_tree = context.space_data.node_tree
        if not node_tree:
            self.report({'WARNING'}, "未找到节点树")
            return

        # 生成渐变数据
        ramp_data = []
        self.sample_points.sort()
        for t in self.sample_points:
            uv = self.t_to_uv(t)
            color = self.sample_color_from_thumbnail(uv)
            # sRGB 转线性空间，匹配 Blender ColorGradient
            r = pow(color[0], 2.2)
            g = pow(color[1], 2.2)
            b = pow(color[2], 2.2)
            a = color[3]
            corrected_color = (r, g, b, a)
            ramp_data.append((t, corrected_color))

        selected_ramps = get_selected_ramps(context)

        if selected_ramps:
            # ✅ 有选中 → 直接覆盖
            for ramp in selected_ramps:
                apply_ramp(ramp, ramp_data)
            self.report({'INFO'}, f"已更新 {len(selected_ramps)} 个选中渐变，共{len(ramp_data)}色标")
        else:
            # ✅ 无选中 → 新建在视口中心
            ramp_node = node_tree.nodes.new(type='ShaderNodeValToRGB')
            ramp_node.label = "剪贴板渐变"
            ramp_node.location = self.new_node_location
            apply_ramp(ramp_node.color_ramp, ramp_data)
            self.report({'INFO'}, f"已新建渐变，共{len(ramp_data)}色标")

    def initialize_image(self, context):
        #可任意替换，但必须初始化 preview_image 和 new_node_location
        node = context.active_node
        if not node or not hasattr(node, "image") or not node.image:
            self.report({"WARNING"}, "请选择带图像的节点")
        # 初始化图像数据
        self.preview_image = node.image
        self.new_node_location = (node.location.x + 200, node.location.y)
        #图像相关初始化完成

    def final_work(self):
        #可任意替换
        return       

    def invoke(self, context, event):
        global IS_RUNNING
        if IS_RUNNING:
            self.report({'INFO'}, f"插件正在运行，跳过重复执行")
            return {'CANCELLED'}
        IS_RUNNING = True
        # 重置状态
        self.draw_handle = None
        self.draw_running = False
        self.view_scale = 1.0
        self.view_offset = [0.0, 0.0]
        self.control_points.clear()
        self.sample_points.clear()
        self.drag_target = None
        self.drag_index = -1
        # 环境检查
        if context.area.type != 'NODE_EDITOR':
            self.report({'WARNING'}, "请在节点编辑器中运行")
            return {'CANCELLED'}
        # 初始化图像数据
        self.initialize_image(context)
        if self.preview_image == None or self.new_node_location == None:
            #说明initialize_image失败了,initialize_image必须初始化preview_image和new_node_location
            self.report({'WARNING'}, "插件初始化失败，请向开发者反馈")
            return {"CANCELLED"}

        np_original = blimg_2_npimg(self.preview_image)
        self.np_thumbnail = np_resize_img(np_original, 128, 128)
        # 启动预览
        self.region_width = context.region.width
        self.region_height = context.region.height
        self.start_preview(context)
        bpy.context.workspace.status_text_set(bottom_status_bar)
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}
    
    def esc_modal(self, context):
        self.stop_preview()
        bpy.context.workspace.status_text_set(None)
        context.area.tag_redraw()
        self.final_work()
        global IS_RUNNING
        IS_RUNNING = False

    def modal(self, context, event):
        if not IS_RUNNING:
            self.report({'INFO'}, f"插件已在其它地方被执行退出")
            self.esc_modal(context)
            return {'CANCELLED'}
        
        try:
            # 更新基础信息
            self.region_width = context.region.width
            self.region_height = context.region.height
            self.mouse_x_screen = event.mouse_region_x
            self.mouse_y_screen = event.mouse_region_y
            self.update_uv_and_mouse_site()
            uv = self.mouse_in_image_uv
            
            # 退出操作
            if event.type == "ESC" and event.value == "PRESS":
                self.esc_modal(context)
                return {"FINISHED"}

            # A：自动采样（清空 → 采样 → RDP精简8点）
            if event.type == "A" and event.value == "PRESS":
                if event.shift:
                    target_points = 16
                elif event.ctrl:
                    target_points = 4
                else:
                    target_points = 8
                    
                if self.auto_sample_line(target_points):
                    self.report({'INFO'}, "✅ 自动采样完成：精简为8个采样点")
                else:
                    self.report({'WARNING'}, "⚠️ 请先设置两个控制点")
                context.area.tag_redraw()
                return {"RUNNING_MODAL"}

            # L：锁定控制点
            if event.type == 'L' and event.value == 'PRESS':
                self.control_locked = not self.control_locked
                self.report({'INFO'}, "控制点已锁定" if self.control_locked else "控制点已解锁")
                context.area.tag_redraw()
                return {"RUNNING_MODAL"}

            # F：均匀分布采样点
            if event.type == 'F' and event.value == 'PRESS':
                n = len(self.sample_points)
                if n >= 1:
                    self.sample_points = [i/(n-1) for i in range(n)]
                    self.report({'INFO'}, "✅ 采样点已均匀分布")
                    context.area.tag_redraw()
                return {"RUNNING_MODAL"}

            # X：删除鼠标附近采样点
            if event.type == 'X' and event.value == 'PRESS':
                if len(self.control_points) == 2 and len(self.sample_points) > 0:
                    t = self.uv_to_sample_t(uv)
                    s_idx = self.get_closest_sample_point(t)
                    if s_idx != -1:
                        del self.sample_points[s_idx]
                        self.report({'INFO'}, "已删除采样点")
                        context.area.tag_redraw()
                return {"RUNNING_MODAL"}
            # 1 = 4点
            if event.type in {'ONE','NUMPAD_1'} and event.value == 'PRESS':
                if len(self.control_points) == 2:
                    self.sample_points = [i/3.0 for i in range(4)]
                    self.report({'INFO'}, "✅ 已生成 4 个均匀采样点")
                    context.area.tag_redraw()
                return {"RUNNING_MODAL"}
            # 2 = 8点
            if event.type in {'TWO','NUMPAD_2'} and event.value == 'PRESS':
                if len(self.control_points) == 2:
                    self.sample_points = [i/7.0 for i in range(8)]
                    self.report({'INFO'}, "✅ 已生成 8 个均匀采样点")
                    context.area.tag_redraw()
                return {"RUNNING_MODAL"}
            # 3 = 16点
            if event.type in {'THREE','NUMPAD_3'} and event.value == 'PRESS':
                if len(self.control_points) == 2:
                    self.sample_points = [i/15.0 for i in range(16)]
                    self.report({'INFO'}, "✅ 已生成 16 个均匀采样点")
                    context.area.tag_redraw()
                return {"RUNNING_MODAL"}
            # 4 = 32点（上限拉满）
            if event.type in {'FOUR','NUMPAD_4'} and event.value == 'PRESS':
                if len(self.control_points) == 2:
                    self.sample_points = [i/31.0 for i in range(32)]
                    self.report({'INFO'}, "✅ 已生成 32 个均匀采样点（上限）")
                    context.area.tag_redraw()
                return {"RUNNING_MODAL"}
                
            # H = 显示/隐藏提示
            if event.type == 'H' and event.value == 'PRESS':
                self.show_hints = not self.show_hints
                self.report({'INFO'}, "提示已显示" if self.show_hints else "提示已隐藏")
                context.area.tag_redraw()
                return {"RUNNING_MODAL"}
                
            # 回车：生成渐变
            if event.type == "RET" and event.value == "PRESS":
                self.create_color_ramp(context)
                self.esc_modal(context)
                return {"FINISHED"}

            # 平移视图
            if event.type == "MIDDLEMOUSE":
                if event.value == "PRESS":
                    self.is_panning = True
                    self.last_mouse = (event.mouse_region_x, event.mouse_region_y)
                elif event.value == "RELEASE":
                    self.is_panning = False
                return {"RUNNING_MODAL"}

            # 鼠标移动
            if event.type == "MOUSEMOVE":
                if self.is_panning:
                    dx = event.mouse_region_x - self.last_mouse[0]
                    dy = event.mouse_region_y - self.last_mouse[1]
                    self.view_offset[0] += dx
                    self.view_offset[1] += dy
                    self.last_mouse = (event.mouse_region_x, event.mouse_region_y)
                    # context.area.tag_redraw()

                # 拖动控制点
                if self.drag_target == "control" and self.drag_index >=0 and not self.control_locked:
                    if 0 <= self.drag_index < len(self.control_points):
                        self.control_points[self.drag_index] = uv
                        # context.area.tag_redraw()

                # 拖动采样点
                if self.drag_target == "sample" and self.drag_index >=0:
                    if 0 <= self.drag_index < len(self.sample_points):
                        t = self.uv_to_sample_t(uv)
                        self.sample_points[self.drag_index] = t
                        # context.area.tag_redraw()
                context.area.tag_redraw()
                return {"RUNNING_MODAL"}

            # 缩放
            if event.type in {"WHEELUPMOUSE", "WHEELDOWNMOUSE"} and not (event.ctrl or event.shift):
                factor = 1.1 if event.type == "WHEELUPMOUSE" else 0.9
                self.view_scale = max(0.05, min(50, self.view_scale * factor))
                context.area.tag_redraw()
                return {"RUNNING_MODAL"}

            # 复位视图
            if event.type == "HOME" and event.value == "PRESS":
                self.view_scale = 1.0
                self.view_offset = [0,0]
                context.area.tag_redraw()
                return {"RUNNING_MODAL"}

            # 左键：添加控制点 / 添加采样点 → 立即拖动
            if event.type == "LEFTMOUSE" and event.value == "PRESS":
                mx = self.mouse_x_screen
                my = self.mouse_y_screen
                hit_point = False
                # ====================== 修饰逻辑 ======================
                # SHIFT 强制：只拖动控制点
                if event.shift or event.ctrl:
                    if self.control_locked:
                        self.report({'WARNING'}, "控制点已锁定，无法拖动")
                        context.area.tag_redraw()
                        return {"RUNNING_MODAL"}
                    c_idx = self.get_closest_control_point(uv)
                    if c_idx != -1:
                        cx, cy = self.uv_to_screen(self.control_points[c_idx])
                        if math.hypot(mx - cx, my - cy) <= 30:# 30像素选择范围
                            self.drag_target = "control"
                            self.drag_index = c_idx
                            hit_point = True
                            return {"RUNNING_MODAL"}
                    else: #按住 Shift 没点到控制点 → 禁止任何拖动
                        self.drag_target = None
                        self.drag_index = -1
                        return {"RUNNING_MODAL"}
                                                        
                # ====================== 正常逻辑 ======================
                # 优先检查采样点（10像素内）
                if len(self.control_points) == 2:
                    t = self.uv_to_sample_t(uv)
                    s_idx = self.get_closest_sample_point(t)
                    if s_idx != -1:
                        suv = self.t_to_uv(self.sample_points[s_idx])
                        sx, sy = self.uv_to_screen(suv)
                        if math.hypot(mx - sx, my - sy) <= 10:# 10像素选择范围
                            self.drag_target = "sample"
                            self.drag_index = s_idx
                            hit_point = True
                            return {"RUNNING_MODAL"}

                # 规则2：检查控制点（15像素内）
                c_idx = self.get_closest_control_point(uv)
                if c_idx != -1:
                    cx, cy = self.uv_to_screen(self.control_points[c_idx])
                    if math.hypot(mx - cx, my - cy) <= 15:# 15像素选择范围
                        self.drag_target = "control"
                        self.drag_index = c_idx
                        hit_point = True
                        return {"RUNNING_MODAL"}

                # 规则3：没点到点
                if len(self.control_points) == 2 and not hit_point:
                    # 数量限制
                    if len(self.sample_points) >= 32:
                        self.report({'WARNING'}, "⚠️ 采样点已达上限32个")
                        context.area.tag_redraw()
                        return {"RUNNING_MODAL"}
                    
                    t = self.uv_to_sample_t(uv)
                    self.sample_points.append(t)
                    self.drag_target = "sample"
                    self.drag_index = len(self.sample_points) - 1
                    context.area.tag_redraw()
                    return {"RUNNING_MODAL"}

                # 空白处 → 只允许加控制点
                if len(self.control_points) < 2:
                    self.control_points.append(uv)
                    self.drag_target = "control"
                    self.drag_index = len(self.control_points) - 1
                    context.area.tag_redraw()
                    return {"RUNNING_MODAL"}

                # 空白处 → 什么都不做
                return {"RUNNING_MODAL"}

            # 左键释放
            if event.type == "LEFTMOUSE" and event.value == "RELEASE":
                # 拖动结束 → 自动合并靠近的采样点
                if self.drag_target == "sample" and self.drag_index >= 0:
                    if 0 <= self.drag_index < len(self.sample_points):
                        val = self.sample_points[self.drag_index]
                        new_list = []
                        merged = False
                        threshold = 0.002  # 距离 < 这个值就合并
                        
                        for i, p in enumerate(self.sample_points):
                            if i == self.drag_index:
                                continue
                            if abs(p - val) < threshold:
                                merged = True
                        if not merged:
                            new_list.append(val)
                        
                        final = []
                        temp = new_list + [x for i, x in enumerate(self.sample_points) if i != self.drag_index]
                        for p in temp:
                            keep = True
                            for q in final:
                                if abs(p - q) < threshold:
                                    keep = False
                                    break
                            if keep:
                                final.append(p)
                        self.sample_points = final

                self.drag_target = None
                self.drag_index = -1
                context.area.tag_redraw()
                return {"RUNNING_MODAL"}

            # 右键：删除采样点
            if event.type == "RIGHTMOUSE" and event.value == "PRESS" and len(self.control_points)==2:
                t = self.uv_to_sample_t(uv)
                s_idx = self.get_closest_sample_point(t)
                if s_idx != -1 and len(self.sample_points) > 1:
                    del self.sample_points[s_idx]
                    context.area.tag_redraw()
                return {"RUNNING_MODAL"}

            return {"RUNNING_MODAL"}
        
        except Exception:
            self.esc_modal(context)
            self.report({'INFO'}, "出现了BUG，已安全退出")
            return {'CANCELLED'}
            
            

class BetterExperie_OT_ConvertImageToGradient(BetterExperie_ImageToGradient_BASE):
    bl_idname = "better_experie.convert_image_to_gradient"
    bl_label = "依据图像生成渐变"
    bl_description = "根据选中节点的图像生成颜色渐变条"
    bl_options = {'REGISTER', 'UNDO'}
    # pass
    def initialize_image(self, context):
        #可任意替换，但必须初始化 preview_image 和 new_node_location
        node = context.active_node
        if not node or not hasattr(node, "image") or not node.image:
            self.report({"WARNING"}, "请选择带图像的节点")
        # 初始化图像数据
        self.preview_image = node.image
        self.new_node_location = (node.location.x + 200, node.location.y)
        #图像相关初始化完成

    def final_work(self):
        #可任意替换
        return       
        
class BetterExperie_OT_ImportClipboardToGradient(BetterExperie_ImageToGradient_BASE):
    bl_idname = "better_experie.import_clipboard_to_gradient"
    bl_label = "从剪贴板图像生成渐变"
    bl_description = "从系统剪贴板导入图像并生成颜色渐变条"
    bl_options = {'REGISTER', 'UNDO'}

    def initialize_image(self, context):
        # 导入剪贴板
        self.preview_image = import_image_from_clipboard()
        if not self.preview_image:
            self.report({"ERROR"}, "剪贴板无图像")
            return False

        region = context.region
        rv2d = context.region.view2d

        # 视口中心像素坐标
        x = region.width / 2.0
        y = region.height / 2.0

        # 转为节点坐标
        view_x, view_y = rv2d.region_to_view(x, y)
        
        # UI 缩放修正
        ui_scale = context.preferences.system.ui_scale
        self.new_node_location = (view_x / ui_scale, view_y / ui_scale)
        return True
        
    def final_work(self):
        # 结束后：恢复原图 + 删除临时图像
        if self.preview_image:
            try:
                bpy.data.images.remove(self.preview_image)
            except:
                pass

####################################################################################################
# 注册类
classes = (
    BetterExperie_OT_ConvertImageToGradient,
    BetterExperie_OT_ImportClipboardToGradient,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    global IS_RUNNING
    IS_RUNNING = False
    for cls in classes:
        bpy.utils.unregister_class(cls)
    
