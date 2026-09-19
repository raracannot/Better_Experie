# 灯光辅助线长度

import bpy


def draw_light_cutoff_distance(self, context):
    layout = self.layout
    light = context.light
    # 当前上下文不是灯光，或该灯光没有 cutoff_distance 属性时不显示。
    if light is None or not hasattr(light, "cutoff_distance"):
        return
    layout.prop(light, "cutoff_distance", text="辅助线长度")


# 引擎依赖面板：仅在对应引擎启用时才存在于 bpy.types。
TARGET_PANELS = [
    "CYCLES_LIGHT_PT_beam_shape",
]


def register():
    for panel_name in TARGET_PANELS:
        panel_cls = getattr(bpy.types, panel_name, None)
        if panel_cls is None:
            continue
        try:
            panel_cls.append(draw_light_cutoff_distance)
        except Exception:
            pass


def unregister():
    for panel_name in TARGET_PANELS:
        panel_cls = getattr(bpy.types, panel_name, None)
        if panel_cls is None:
            continue
        try:
            panel_cls.remove(draw_light_cutoff_distance)
        except Exception:
            pass
