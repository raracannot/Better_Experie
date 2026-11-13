
import bpy
from . import __package__ as base_package
from .utils.keymap_utils import draw_hotkey_panel


def _force_update_ui():
    """懒加载强制更新模块，返回按钮文案与状态行（模块未就绪时返回 None）。"""
    try:
        from .ops.other import other_force_update
        return other_force_update.get_ui_state()
    except Exception:
        return None


def _tag_preferences_redraw(context):
    """偏好设置变化后刷新全部编辑器，让注入的按钮立刻出现/消失"""
    window_manager = getattr(context, "window_manager", None)
    windows = window_manager.windows if window_manager is not None else []
    for window in windows:
        for area in window.screen.areas:
            area.tag_redraw()


def preference_enabled(attribute, default=True):
    """读取插件偏好里的布尔开关；读不到时返回 default（宁可显示）"""
    try:
        addons = bpy.context.preferences.addons
        entry = addons.get(base_package)
        if entry is None:
            short = base_package.split(".")[-1]
            for key, item in addons.items():
                if key == short or key.endswith("." + short):
                    entry = item
                    break
        if entry is None:
            return default
        return bool(getattr(entry.preferences, attribute, default))
    except Exception:
        return default


def quick_group_tools_enabled():
    """顶点组/边组列表里的选取与保存按钮是否显示（默认开）"""
    return preference_enabled("show_quick_group_tools", True)


def draw_description_panel(layout, context):
    box=layout.box()
    col = box.column(align=True)
    col.label(text="本插件无主要面板，插件设计思路为：")
    col.label(text="")
    col.separator(type="LINE")
    col.label(text="“一切功能服务于对原生功能的【体验优化】及【功能延展】”")
    col.label(text="“一切按钮只出现的原生面板上它该出现的地方”")
    col.separator(type="LINE")
    col.label(text="")
    col.label(text="主要功能包括不限于：")
    col.label(icon="REC",text="文件浏览器界面，自动识别已打开的系统文件夹并显示跳转按钮至标题栏")
    col.label(icon="REC",text="节点编辑器界面，新增【图像】【渐变】【曲线】相关节点工具至标题栏")
    col.label(icon="REC",text="三维视口界面，新增更多程序化几何体至 ShiftA新建菜单")
    col.label(icon="REC",text="三维视口界面，新增更多融并工具至 编辑模式 M融并菜单")
    col.label(icon="REC",text="三维视口界面，新增更多选择工具至 物体/编辑模式 选择菜单")

    if context.preferences.view.show_developer_ui:
        col.label(icon="REC",text="偏好设置界面，新增更多开发工具至底部 开发者工具 界面")

    col.label(text="")
    col.label(text="插件内置累计数百项对【原生功能】的【体验优化】及【功能延展】")
    col.label(text="详情功能介绍，请点击下方【功能介绍】按钮")
    # col.separator(type="LINE")
    row = col.row(align=True)
    row.operator("wm.url_open", text="功能介绍", icon="HELP").url = "https://www.bilibili.com/video/BV13wWo6rEJZ"
    # row.operator("wm.url_open", text="更新链接", icon="FILE_REFRESH").url = "https://pan.baidu.com/s/1aOYSzA_FobChbegOAWHACg?pwd=RARA"
    row.operator("better_experie.check_update", text="配置插件仓库", icon="FILE_REFRESH")

    # 强制更新：下载 GitHub 发布包并完整覆盖当前插件目录
    force_ui = _force_update_ui() or {}
    row.operator("better_experie.force_update",text=force_ui.get("label", "强制更新"), icon=force_ui.get("icon", "IMPORT"))
    if force_ui.get("status"):
        col.label(text=force_ui["status"], icon="INFO")

    row.separator()
    row.operator("wm.url_open", text="哔哩哔哩", icon="USER").url = "https://space.bilibili.com/27284213"
    row.operator("wm.url_open", text="官方库", icon="BLENDER").url = "https://extensions.blender.org/author/58486/"
    row.operator("wm.url_open", text="Github", icon="FILE_SCRIPT").url = "https://github.com/raracannot/Better_Experie"



def draw_thanks_panel(layout, context):
    box=layout.box()
    col = box.column(align=True)
    col.label(text="用户致谢",icon="FUND")
    col.separator(type="LINE")
    # col.label(text="感谢使用本插件")

    col.label(text="飞尘增山，雾霭盈海，非常感谢您使用本插件")
    col.label(text="每一位用户，都令这个免费插件计划拥有更多意义")
    col.label(text="感谢每一位向RARA提出过意见的朋友们")
    col.label(text="")

    col.label(text="本插件开源免费、致力于尽可能的提升您的blender使用体验")
    col.label(text="很多功能受到了【Blender超级技术交流社】成员的启发或协助得以实现")
    col.label(text="")

    col.label(text="社群招新",icon="FUND")
    col.separator(type="LINE")
    col.label(text="如果你对开发blender插件及脚本开发感兴趣、或者在开发途中遇到了棘手的问题")
    col.label(text="欢迎加入【blender超级技术交流社】！！这里有着数百位blender插件中文开发者！")
    col.label(text="共享开发指南、性能优化方案及已知常见 Bug 库")
    col.label(text="别把生命浪费在已知问题上，让我们聚焦真正的功能创新")
    col.label(text="")

    col.label(text="我们相信【提问本身就是贡献】，每一个被解答的问题，都能帮到所有后来者")
    col.label(text="群里没有【大佬/萌新】的身份标签，只有代码和逻辑说话")
    col.label(text="无论你的经验是 10 年还是 10 天，好问题值得被认真回答，好方案值得被热烈讨论")
    col.label(text="")

    col.label(text="开源世界的每一位行者，都不需要孤独行走，欢迎与我们汇聚，化为翻涌的江河！！")
    op = col.operator("wm.url_open", text="与我们汇聚", icon="INTERNET")
    op.url = "https://www.bilibili.com/video/BV12F5m6UEkG/"
    col.label(text="")

    # box_up = col.box()
    col.label(text="帮助致谢（按名称首字母排序）",icon="FUND")
    col.separator(type="LINE")
    up_list = [
        ("摘星陈的插件仓库", "HEART", "https://space.bilibili.com/289597239/"), #关键功能代码片段
        ("只剩一瓶辣椒酱", "BLENDER", "https://extensions.blender.org/author/445/"), #开发知识援助
        ("一尘不染月当天", "BLENDER", "https://extensions.blender.org/author/30/"), #开发知识援助
        ("亮锅不服lao", "HEART", "https://space.bilibili.com/429605217/"), #开发知识援助
        ("whatwhyhow", "HEART", "https://space.bilibili.com/3824431/"), #重要改进意见
        ("漓舒s", "HEART", "https://space.bilibili.com/500957923/"), #关键功能代码片段
        ("olpha", "INTERNET", "https://olpha.cn/"), #关键功能代码片段
        ("睡梦", "BLENDER", "https://extensions.blender.org/author/3361/"), #开发知识援助
        ("浪里浇花", "HEART", "https://space.bilibili.com/382662799/"), #重要改进意见
        ("wittyming", "HEART", "https://space.bilibili.com/263206115/"), #关键功能代码片段
        ("61+", "HEART", "https://space.bilibili.com/3846664/"), #关键功能代码片段
    ]
    up_list.sort(key=lambda item: item[0])
    row = None
    max_col = 5
    remain = len(up_list) % max_col
    # 拼接占位元素：原有UP数据 + 需要补齐的None占位项
    render_items = up_list + [None]*(0 if remain == 0 else max_col - remain)

    for idx, item in enumerate(render_items):
        if idx % max_col == 0:
            row = col.row(align=True)
        if item is not None:
            # 正常UP按钮绘制
            up_name, up_icon, up_url = item
            op = row.operator("wm.url_open", text=up_name, icon=up_icon)
            op.url = up_url
        else:
            # 占位空白label
            row.label(text="")

    col.separator(type="LINE")
    col.label(text="2026.08.08")
    # col.label(text="")
            
            

# 偏好设置属性及面板
class BetterExperie_Preferences(bpy.types.AddonPreferences):
    # bl_idname = __name__
    bl_idname = base_package

    show_debug : bpy.props.BoolProperty(
        name="显示debug功能",description="显示debug功能",default=True)

    filebrowser_auto_update: bpy.props.BoolProperty(
        name="自动更新", description="是否自动刷新 Explorer 路径缓存", default=True)
    filebrowser_show_explorer_heder: bpy.props.BoolProperty(
        name="文件管理器标题栏显示", description="是否显示插件在文件管理器标题栏", default=True)

    show_node_minimap: bpy.props.BoolProperty(
        name="节点预览图",
        description="在节点编辑器左下角显示节点树小地图预览",
        default=False)

    console_multilang_fix: bpy.props.BoolProperty(
        name="控制台多语言修复 (Windows)",
        description="加载时执行 chcp 65001 切换控制台编码为 UTF-8，避免中文日志乱码（仅 Windows）",
        default=True)

    compare_line_color: bpy.props.FloatVectorProperty(
        name="对比分割线颜色",
        description="对比工具（槽位对比/视口快照）的分割线颜色",
        subtype='COLOR', size=4, min=0.0, max=1.0, default=(1.0, 1.0, 1.0, 1.0))
    compare_line_width: bpy.props.IntProperty(
        name="对比分割线宽度",
        description="对比工具（槽位对比/视口快照）的分割线宽度",
        min=0, max=50, default=20)
    show_slot_compare_header: bpy.props.BoolProperty(
        name="图像编辑器标题栏-渲染槽位对比 快捷入口",
        description="在图像编辑器标题栏显示槽位对比快捷入口",
        default=False)
    show_view3d_screenshot_button: bpy.props.BoolProperty(
        name="三维编辑器标题栏-视口快照对比 快捷入口",
        description="在三维视口右上角，显示视口快照的按钮",
        default=False)

    show_quick_group_tools: bpy.props.BoolProperty(
        name="属性视口 显示顶点组/边组的选取优化及存储优化工具",
        description="在顶点组/边组列表每行显示选取与保存按钮（单击=加入，Shift=覆盖，Ctrl=移除）",
        default=True,update=lambda self, context: _tag_preferences_redraw(context))

    show_camera_dropdown: bpy.props.BoolProperty(
        name="blender整体视口右上角的相机下拉栏",
        description="在顶栏右侧显示活动相机下拉栏与左右切换按钮",
        default=True,update=lambda self, context: _tag_preferences_redraw(context))

    show_more_meshes: bpy.props.BoolProperty(
        name="三维视口右键菜单的更多网格",
        description="在 添加 → 网格 菜单里显示「更多网格」子菜单",
        default=True,update=lambda self, context: _tag_preferences_redraw(context))

    show_outliner_quick_add: bpy.props.BoolProperty(
        name="大纲视图左上角的快速添加锁定及空物体",
        description="在大纲视图标题栏显示「切换变换锁定」与「添加空物体」按钮",
        default=True,update=lambda self, context: _tag_preferences_redraw(context))

    show_edit_quick_tools: bpy.props.BoolProperty(
        name="三维视口左上角网格编辑模式快捷复制及顶点组工具箱",
        description="在三维视口标题栏显示复制/粘贴元素与新建顶点组按钮（编辑模式）",
        default=True,update=lambda self, context: _tag_preferences_redraw(context))

    output_path: bpy.props.StringProperty(
            name="打包工具输出路径",
            description="打包后文件保存的位置（自动记录，下次打开无需重复设置）",
            default="",subtype='DIR_PATH')

    preferences_panel_selection: bpy.props.EnumProperty(
        items=[
            ('SETTING', "设置项", "显示设置详细项目", "MODIFIER", 0),
            ('HOTKEYS', "快捷键", "显示快捷键设置面板", "KEY_COMMAND", 1),
            ('DESCRIPTION', "插件说明", "显示插件说明", "HELP", 2),
            ('THANKS', "致谢", "显示插件致谢词", "FUND", 3),
        ],name="面板选择",default='SETTING')

    def draw(self, context):
        layout = self.layout
        row = layout.row()
        row.prop(self, "preferences_panel_selection",text="Cross Select", expand=True)
        if self.preferences_panel_selection == 'SETTING':
            box = layout.box()
            box.label(text="界面元素显示", icon='PREFERENCES')
            column = box.column(align=True)
            column.prop(self, "show_camera_dropdown")
            column.prop(self, "show_quick_group_tools")
            column.prop(self, "show_outliner_quick_add")
            column.prop(self, "show_more_meshes")
            column.prop(self, "show_edit_quick_tools")

            column.separator()
            column.prop(self, "show_slot_compare_header")
            column.prop(self, "show_view3d_screenshot_button")
            
            if context.preferences.view.show_developer_ui:
                column.separator()
                column.prop(self, "show_debug",text="显示debug功能") #内部debug
                if self.show_debug:
                    column.operator("better_experie.reload_addon", text="刷新插件")
                column.prop(self, "console_multilang_fix") #修复多语言
            
        elif self.preferences_panel_selection == 'HOTKEYS':
            draw_hotkey_panel(layout, context)

        elif self.preferences_panel_selection == 'DESCRIPTION':
            draw_description_panel(layout, context)

        elif self.preferences_panel_selection == 'THANKS':
            draw_thanks_panel(layout, context)
        
        layout.separator()


def register():
    # 防止热重载中途异常导致重复注册
    try:
        bpy.utils.unregister_class(BetterExperie_Preferences)
    except Exception:
        pass
    bpy.utils.register_class(BetterExperie_Preferences)


def unregister():
    try:
        bpy.utils.unregister_class(BetterExperie_Preferences)
    except Exception:
        pass
