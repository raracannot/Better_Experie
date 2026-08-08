# VSE 片段工具函数

import re
import bpy


def strip_group_key(strip):
    name = strip.name
    name = re.sub(r'\.\d{3}$', '', name)
    name = re.sub(r'\.(mp4|mov|avi|mkv|wav|mp3|flac|ogg|png|jpg|exr)$', '', name, flags=re.IGNORECASE)
    return name


def get_selected_strip_groups(context):
    sed = context.scene.sequence_editor
    groups = {}
    for s in sed.strips:
        if s.select:
            key = strip_group_key(s)
            groups.setdefault(key, []).append(s)
    return sorted(groups.values(), key=lambda g: min(s.frame_start for s in g))
