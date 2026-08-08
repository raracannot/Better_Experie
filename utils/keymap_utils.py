# 快捷键注册/注销/偏好设置绘制（供 addon_prefs 面板及注册入口调用）

import bpy

# ============================== 快捷键配置 ==============================
# 每个配置描述一条待注册的快捷键，keymap 使用 Blender 内置名称（如 Mesh），
# 默认仅注册不启用（active=False），用户可在偏好设置中手动开启/编辑。
HOTKEY_CONFIGS = (
    {
        "label": "复制选中网格",
        "idname": "better_experie.copy_elements",
        "km": "Mesh",
        "type": "C",
        "value": "PRESS",
        "ctrl": True,
    },
    {
        "label": "粘贴选中网格",
        "idname": "better_experie.paste_elements",
        "km": "Mesh",
        "type": "V",
        "value": "PRESS",
        "ctrl": True,
    },
)

# 记录 addon keyconfig 中已注册的 (keymap, keymap_item)，用于注销时精确清理
addon_keymaps = []


def register_keymap():
    """向 addon keyconfig 注册快捷键，默认 active=False（仅注册不启用）"""
    kc = bpy.context.window_manager.keyconfigs.addon
    if not kc:
        return
    for cfg in HOTKEY_CONFIGS:
        try:
            km = kc.keymaps.get(cfg["km"])
            if not km:
                km = kc.keymaps.new(cfg["km"], space_type='EMPTY')
            kmi = km.keymap_items.new(
                cfg["idname"],
                cfg["type"],
                cfg["value"],
                ctrl=cfg.get("ctrl", False),
                shift=cfg.get("shift", False),
                alt=cfg.get("alt", False),
            )
            kmi.active = False  # 默认仅注册不启用
            addon_keymaps.append((km, kmi))
        except Exception as e:
            print(f"[keymap_utils] 注册快捷键 {cfg['idname']} 失败: {e}")


def unregister_keymap():
    """移除 addon keyconfig 中本插件注册的快捷键"""
    for km, kmi in addon_keymaps:
        try:
            km.keymap_items.remove(kmi)
        except Exception:
            pass
    addon_keymaps.clear()


def _draw_kmi_item(name, kc, km, kmi, layout):
    """在偏好设置中绘制单个快捷键项（基于 Blender rna_keymap_ui 实现）"""
    map_type = kmi.map_type
    row = layout.row(align=True)
    col = row.column(align=True)
    row = col.row()
    row.prop(kmi, "active", text="", emboss=False)
    row.label(text=name)
    if not kmi.active:
        row.label(text="（当前未启用）")
    else:
        row.prop(kmi, "show_expanded", text="", emboss=False)
        row.active = kmi.active
        row.prop(kmi, "map_type", text="")
        if kmi.show_expanded:
            row = layout.row()
            if map_type in {'KEYBOARD', 'MOUSE'}:
                box = row.box()
                sub = box.row()
                row = sub.row(align=True)
                if map_type == 'KEYBOARD':
                    row.prop(kmi, "type", text="", event=True)
                    row.prop(kmi, "value", text="")
                    subrow_repeat = row.row(align=True)
                    subrow_repeat.active = kmi.value in {'ANY', 'PRESS'}
                    subrow_repeat.prop(kmi, "repeat", text="")
                elif map_type in {'MOUSE', 'NDOF'}:
                    row.prop(kmi, "type", text="")
                    row.prop(kmi, "value", text="")
                if map_type in {'KEYBOARD', 'MOUSE'} and kmi.value == 'CLICK_DRAG':
                    row = sub.row()
                    row.prop(kmi, "direction")
                sub = box.row()
                row = sub.row()
                row.prop(kmi, "any", toggle=True)
                row.prop(kmi, "shift_ui", toggle=True)
                row.prop(kmi, "ctrl_ui", toggle=True)
                row.prop(kmi, "alt_ui", toggle=True)
                row.prop(kmi, "oskey_ui", text="Cmd", toggle=True)
            else:
                row.label(text="暂不支持")
        else:
            if map_type in {'KEYBOARD', 'MOUSE'}:
                row.prop(kmi, "type", text="", full_event=True)
            else:
                row.label(text="暂不支持")


def draw_hotkey_panel(layout, context):
    """在偏好设置中绘制快捷键设置区（含恢复默认按钮）"""
    box = layout.box()
    kc = context.window_manager.keyconfigs.user
    for cfg in HOTKEY_CONFIGS:
        km = kc.keymaps.get(cfg["km"]) if kc else None
        kmi_found = None
        draw_kc, draw_km = kc, km
        if km:
            for kmi in km.keymap_items:
                if kmi.idname == cfg["idname"]:
                    kmi_found = kmi
                    break
        if kmi_found is None:
            # 兜底：从 addon keyconfig 中查找（用户 keyconfig 可能未合并 inactive 项）
            kc_addon = context.window_manager.keyconfigs.addon
            km_addon = kc_addon.keymaps.get(cfg["km"]) if kc_addon else None
            if km_addon:
                for kmi in km_addon.keymap_items:
                    if kmi.idname == cfg["idname"]:
                        kmi_found = kmi
                        draw_kc, draw_km = kc_addon, km_addon
                        break
        if kmi_found is not None:
            _draw_kmi_item(cfg["label"], draw_kc, draw_km, kmi_found, box)
        else:
            row = box.row()
            row.label(text=f"{cfg['label']}：未检测到快捷键", icon='ERROR')
    box.operator("better_experie.restore_hotkey", text="恢复默认快捷键", icon='FILE_REFRESH')


class BetterExperie_OT_RestoreHotkey(bpy.types.Operator):
    bl_idname = "better_experie.restore_hotkey"
    bl_label = "恢复默认快捷键"
    bl_description = "移除本插件所有快捷键并重新注册为默认状态（默认未启用）"
    bl_options = {'REGISTER'}

    def execute(self, context):
        kc_addon = context.window_manager.keyconfigs.addon
        if kc_addon:
            for cfg in HOTKEY_CONFIGS:
                km = kc_addon.keymaps.get(cfg["km"])
                if not km:
                    continue
                for kmi in list(km.keymap_items):
                    if kmi.idname == cfg["idname"]:
                        try:
                            km.keymap_items.remove(kmi)
                        except Exception:
                            pass
        kc_user = context.window_manager.keyconfigs.user
        if kc_user:
            for cfg in HOTKEY_CONFIGS:
                km = kc_user.keymaps.get(cfg["km"])
                if not km:
                    continue
                for kmi in list(km.keymap_items):
                    if kmi.idname == cfg["idname"]:
                        try:
                            km.keymap_items.remove(kmi)
                        except Exception:
                            pass
        addon_keymaps.clear()
        register_keymap()
        self.report({'INFO'}, "快捷键已恢复默认（默认未启用）")
        return {'FINISHED'}


def register():
    try:
        bpy.utils.unregister_class(BetterExperie_OT_RestoreHotkey)
    except Exception:
        pass
    bpy.utils.register_class(BetterExperie_OT_RestoreHotkey)
    unregister_keymap()
    register_keymap()


def unregister():
    unregister_keymap()
    try:
        bpy.utils.unregister_class(BetterExperie_OT_RestoreHotkey)
    except Exception:
        pass
