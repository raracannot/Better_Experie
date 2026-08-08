# 模态算子统一视口白色边框绘制工具
# 模态持续期间在视口边缘绘制 10px 白色边框，提示用户处于特殊模式

import bpy
import gpu
import traceback
from gpu_extras.batch import batch_for_shader


def _draw_border(self, context):
    try:
        shader = gpu.shader.from_builtin('UNIFORM_COLOR')
        region = context.region
        w, h = region.width, region.height
        m = 2
        coords = [
            (m, m), (w - m, m),
            (w - m, m), (w - m, h - m),
            (w - m, h - m), (m, h - m),
            (m, h - m), (m, m),
        ]
        try:
            gpu.state.line_width_set(10.0)
            gpu.state.blend_set('ALPHA')
            batch = batch_for_shader(shader, 'LINES', {"pos": coords})
            shader.bind()
            shader.uniform_float("color", (1.0, 1.0, 1.0, 1.0))
            batch.draw(shader)
        finally:
            gpu.state.blend_set('NONE')
            gpu.state.line_width_set(1.0)
    except ReferenceError:
        pass
    except Exception:
        traceback.print_exc()


def add_modal_border(owner, context):
    """注册视口白色边框绘制，返回 handler。
    owner 需具备 _modal_border_handle 属性（建议在 __init__ 初始化为 None）。
    """
    handle = bpy.types.SpaceView3D.draw_handler_add(
        _draw_border, (owner, context), 'WINDOW', 'POST_PIXEL')
    owner._modal_border_handle = handle
    return handle


def remove_modal_border(owner):
    """安全移除视口边框 handler"""
    handle = getattr(owner, '_modal_border_handle', None)
    if handle:
        try:
            bpy.types.SpaceView3D.draw_handler_remove(handle, 'WINDOW')
        except Exception:
            pass
        owner._modal_border_handle = None
