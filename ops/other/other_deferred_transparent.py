# 延迟透明

import bpy
from bpy.app.handlers import persistent

_original_transparent_states = {}


@persistent
def pre_render_transparent_handler(scene):
    if scene.better_experie_deferred_transparent:
        _original_transparent_states[scene.name] = scene.render.film_transparent
        scene.render.film_transparent = True


@persistent
def post_render_transparent_handler(scene):
    if scene.better_experie_deferred_transparent and scene.name in _original_transparent_states:
        scene.render.film_transparent = _original_transparent_states[scene.name]
        del _original_transparent_states[scene.name]


def draw_deferred_transparent(self, context):
    layout = self.layout
    layout.prop(context.scene, "better_experie_deferred_transparent", text="延迟透明")


TARGET_PANELS = [
    "CYCLES_RENDER_PT_film",
    "RENDER_PT_eevee_film",
    "RENDER_PT_opengl_film",
]


def register():
    bpy.types.Scene.better_experie_deferred_transparent = bpy.props.BoolProperty(
        name="延迟透明",
        description="启用后，仅在渲染期间自动开启背景透明，渲染结束后自动恢复",
        default=False)

    for panel_name in TARGET_PANELS:
        if hasattr(bpy.types, panel_name):
            getattr(bpy.types, panel_name).append(draw_deferred_transparent)

    if pre_render_transparent_handler not in bpy.app.handlers.render_pre:
        bpy.app.handlers.render_pre.append(pre_render_transparent_handler)

    if post_render_transparent_handler not in bpy.app.handlers.render_post:
        bpy.app.handlers.render_post.append(post_render_transparent_handler)

    if post_render_transparent_handler not in bpy.app.handlers.render_cancel:
        bpy.app.handlers.render_cancel.append(post_render_transparent_handler)


def unregister():
    if pre_render_transparent_handler in bpy.app.handlers.render_pre:
        bpy.app.handlers.render_pre.remove(pre_render_transparent_handler)

    if post_render_transparent_handler in bpy.app.handlers.render_post:
        bpy.app.handlers.render_post.remove(post_render_transparent_handler)

    if post_render_transparent_handler in bpy.app.handlers.render_cancel:
        bpy.app.handlers.render_cancel.remove(post_render_transparent_handler)

    for panel_name in TARGET_PANELS:
        if hasattr(bpy.types, panel_name):
            getattr(bpy.types, panel_name).remove(draw_deferred_transparent)

    del bpy.types.Scene.better_experie_deferred_transparent
