# 面板提取器

import bpy
import inspect
import re
import sys
import os

# 存储注册的菜单和函数引用
registered_items = []
_picker_active = False

# ============================================================
# 工具函数：操作符/按钮/菜单/工具信息提取
# ============================================================

def _get_operator_class(opname):
    parts = opname.split(".")
    if len(parts) != 2:
        return None
    try:
        opmod = getattr(bpy.ops, parts[0])
        op = getattr(opmod, parts[1])
    except AttributeError:
        return None
    try:
        rna_id = op.get_rna_type().bl_rna.identifier
        return getattr(bpy.types, rna_id)
    except AttributeError:
        pass
    for cls in bpy.types.Operator.__subclasses__():
        if getattr(cls, "bl_idname", "") == opname:
            return cls
    return None

def _get_operator_module_info(opname):
    clazz = _get_operator_class(opname)
    if clazz is None:
        return "", -1
    mod_name = clazz.__module__
    try:
        line = inspect.getsourcelines(clazz)[1]
    except (IOError, TypeError):
        line = -1
    if mod_name == 'bpy.types':
        return 'C operator', -1
    if mod_name != '__main__':
        try:
            filepath = sys.modules[mod_name].__file__
        except KeyError:
            filepath = mod_name
        return filepath, line
    return mod_name, line

def _get_addon_root(filepath):
    if not filepath or filepath == 'C operator':
        return None
    norm = os.path.normpath(filepath)
    parts = norm.split(os.sep)
    if "addons" in parts:
        idx = parts.index("addons")
        if idx + 1 < len(parts):
            return parts[idx + 1], os.sep.join(parts[:idx + 2])
    if "extensions" in parts:
        idx = parts.index("extensions")
        if idx + 2 < len(parts):
            return parts[idx + 2], os.sep.join(parts[:idx + 3])
    return None

def _normalize_operator_id(raw):
    raw = raw.strip()
    if ', ' in raw and ' at ' in raw:
        match = re.search(r',\s*(\S+)\s+at\s', raw)
        if match:
            raw = match.group(1)
    match = re.match(r'^bpy\.ops\.(\w+)\.(\w+)\s*\(.*$', raw)
    if match:
        return f"{match.group(1)}.{match.group(2)}"
    match = re.match(r'^([A-Z0-9]+(?:_[A-Z0-9]+)*)_OT_(\w+)$', raw)
    if match:
        return f"{match.group(1).lower()}.{match.group(2).lower()}"
    if '.' in raw and '_OT_' not in raw.upper():
        return raw
    if '_OT_' in raw.upper():
        idx = raw.upper().find('_OT_')
        return f"{raw[:idx].lower()}.{raw[idx + 4:].lower()}"
    return raw

def _extract_operator_id_from_context(context):
    btn_op = getattr(context, "button_operator", None)
    if btn_op is None:
        return ""
    if isinstance(btn_op, str):
        return btn_op
    if hasattr(btn_op, 'bl_rna'):
        return btn_op.bl_rna.identifier
    return str(btn_op)

def _get_tool_id_from_context(context):
    btn_op = getattr(context, "button_operator", None)
    if btn_op is not None and not isinstance(btn_op, str):
        if hasattr(btn_op, "name"):
            op_id = _extract_operator_id_from_context(context)
            if op_id in ("WM_OT_tool_set_by_id", "wm.tool_set_by_id"):
                return getattr(btn_op, "name", None)
    if hasattr(context, "button_pointer") and context.button_pointer:
        if isinstance(context.button_pointer, bpy.types.WorkSpaceTool):
            return context.button_pointer.idname
    return None

def _get_tool_source(tool_id):
    for cls in bpy.types.WorkSpaceTool.__subclasses__():
        if getattr(cls, "bl_idname", "") == tool_id:
            try:
                return inspect.getfile(cls), inspect.getsourcelines(cls)[1]
            except Exception:
                return None, -1
    return None, -1

# 操作：激活面板提取器
class BetterExperie_OT_DeveloperPanelPicker(bpy.types.Operator):
    bl_idname = "better_experie.developer_panel_picker"
    bl_label = "面板提取器"
    bl_description = "在界面中显示【面板吸管按钮】"
    bl_options = {"REGISTER", "INTERNAL"}

    def execute(self, context):
        global _picker_active
        if _picker_active:
            unregister_all_panels()
            all_tag_redraw()
            self.report({'INFO'}, "面板选择模式已取消")
            return {'FINISHED'}
        register_all_panels()
        all_tag_redraw()
        self.report({'INFO'}, "面板选择模式已激活，右键菜单已注册")
        return {'FINISHED'}

# 操作：点击提取面板信息
class BetterExperie_OT_DeveloperPickPanelLocation(bpy.types.Operator):
    bl_idname = "better_experie.developer_pick_panel_location"
    bl_label = "临时吸管"
    bl_description = "点击提取此面板所在位置"
    bl_options = {"REGISTER", "INTERNAL"}

    panel_id: bpy.props.StringProperty()
    panel_type: bpy.props.StringProperty()

    def execute(self, context):
        # 获取面板信息
        panel_info = f"{self.panel_type}: {self.panel_id}"

        # 打印面板信息
        print(f"\n=== 已选择面板位置: {panel_info} ===")

        # 获取面板类
        panel_class = find_panel_class(self.panel_id)
        if panel_class:
            # 打印注册/注销代码
            print("\n在目标位置从前向后添加方式:")
            print(f"bpy.types.{panel_class.__name__}.prepend(your_function)")
            print("\n在目标位置从后向前添加方式:")
            print(f"bpy.types.{panel_class.__name__}.append(your_function)")
            print("\n注销方式:")
            print(f"bpy.types.{panel_class.__name__}.remove(your_function)")

            # 打印面板属性
            print("\n面板属性:")
            print(f"  类名: {panel_class.__name__}")
            print(f"  标识符: {getattr(panel_class, 'bl_idname', '未定义')}")
            print(f"  标签: {getattr(panel_class, 'bl_label', '未定义')}")
            print(f"  空间类型: {getattr(panel_class, 'bl_space_type', '未定义')}")
            print(f"  区域类型: {getattr(panel_class, 'bl_region_type', '未定义')}")
            print(f"  类别: {getattr(panel_class, 'bl_category', '未定义')}")
            print(f"  上下文: {getattr(panel_class, 'bl_context', '未定义')}")
            print(f"  父级: {getattr(panel_class, 'bl_parent_id', '未定义')}")
            print(f"  级别: {getattr(panel_class, 'bl_options', '未定义')}")

            # 打印所在模块
            module = inspect.getmodule(panel_class)
            print(f"  模块: {module.__name__ if module else '未知'}")

            # 检查是否为内置类
            is_builtin = module and module.__name__.startswith('bpy_types')
            print(f"  是否为内置类: {is_builtin}")

            # 显示源代码位置
            try:
                source_file = inspect.getsourcefile(panel_class)
                source_lines, line_num = inspect.getsourcelines(panel_class)
                print(f"  源代码位置参考: {source_file}, 第 {line_num} 行")
            except:
                pass

            # 显示面板布局结构
            print("\n面板布局结构:")
            if hasattr(panel_class, 'draw'):
                try:
                    draw_source = inspect.getsource(panel_class.draw)
                    print("  draw() 方法源代码:")
                    for line in draw_source.split('\n'):
                        print(f"    {line}")
                except:
                    print("  无法获取 draw() 方法源代码")

            # 显示继承结构
            bases = [base.__name__ for base in panel_class.__bases__]
            print(f"\n继承结构: {panel_class.__name__} <- { ' <- '.join(bases) }")

            # 显示面板在Blender中的位置
            space_type = getattr(panel_class, 'bl_space_type', 'UNKNOWN')
            region_type = getattr(panel_class, 'bl_region_type', 'UNKNOWN')
            print(f"\n在Blender中的位置: {space_type} 空间的 {region_type} 区域")

            # 显示面板可见性条件
            if hasattr(panel_class, 'poll'):
                print("\n面板可见性条件:")
                try:
                    poll_source = inspect.getsource(panel_class.poll)
                    print("  poll() 方法源代码:")
                    for line in poll_source.split('\n'):
                        print(f"    {line}")
                except:
                    print("  无法获取 poll() 方法源代码")

            # 提供示例代码
            print("\n示例代码:")
            print(f"""
#--------------------python--------------------

# 在 {panel_class.__name__} 面板后添加自定义内容
def custom_draw(self, context):
    layout = self.layout
    layout.label(text="这是自定义内容")

# 注册
def register():
    bpy.types.{panel_class.__name__}.append(custom_draw)

# 注销
def unregister():
    bpy.types.{panel_class.__name__}.remove(custom_draw)

#----------------------------------------
""")
            print(f"\n=== 以上为 {panel_info} 完整报告 ===")
        else:
            print("警告: 无法获取面板类信息")
            self.report({'INFO'}, "无法获取面板类信息")

        # 取消注册所有临时按钮
        unregister_all_panels()

        # 重绘所有区域
        all_tag_redraw()

        self.report({'INFO'}, "已提取出所有可提取信息，请前往控制台查阅")
        # 重置选择器状态

        return {'FINISHED'}

# ============================================================
# 操作：打印按钮/菜单/工具完整信息到控制台
# ============================================================

class BetterExperie_OT_DeveloperPrintElementInfo(bpy.types.Operator):
    #感谢 爿亣 提供核心代码
    bl_idname = "better_experie.developer_print_element_info"
    bl_label = "打印元素信息"
    bl_description = "将当前按钮/菜单/工具的完整信息打印到控制台"
    bl_options = {"REGISTER", "INTERNAL"}

    @classmethod
    def poll(cls, context):
        return (hasattr(context, "button_operator") and context.button_operator) or \
               getattr(context, "ui_menu", None) is not None

    def execute(self, context):
        success = False
        if getattr(context, "ui_menu", None):
            self._print_menu_info(context)
            success = True
        else:
            tool_id = _get_tool_id_from_context(context)
            if tool_id:
                self._print_tool_info(tool_id)
                success = True
            else:
                raw = _extract_operator_id_from_context(context)
                if raw:
                    self._print_button_info(raw)
                    success = True

        if not success:
            self.report({'WARNING'}, "无法识别元素类型")
            return {'CANCELLED'}

        unregister_all_panels()
        all_tag_redraw()
        self.report({'INFO'}, "已提取出所有可提取信息，请前往控制台查阅")
        return {'FINISHED'}

    def _print_button_info(self, raw):
        op_id = _normalize_operator_id(raw)
        op_class = _get_operator_class(op_id)
        filepath, line = _get_operator_module_info(op_id)

        print(f"\n=== 按钮信息: {op_id} ===")

        if op_class:
            print(f"\n操作符类: {op_class.__name__}")
            print(f"  标识符(bl_idname): {getattr(op_class, 'bl_idname', '未定义')}")
            print(f"  标签(bl_label): {getattr(op_class, 'bl_label', '未定义')}")
            desc = getattr(op_class, 'bl_description', '')
            if desc:
                print(f"  描述(bl_description): {desc}")
            print(f"  选项(bl_options): {getattr(op_class, 'bl_options', set())}")
            print(f"  模块: {op_class.__module__}")

            try:
                source_file = inspect.getfile(op_class)
                source_lines, line_num = inspect.getsourcelines(op_class)
                print(f"  源代码位置: {source_file}, 第 {line_num} 行")
            except Exception:
                pass

            if filepath == 'C operator':
                print(f"\n类型: Blender 内置 (C 实现)")
            elif filepath:
                root = _get_addon_root(filepath)
                if root:
                    print(f"\n所属插件: {root[0]}")
                    print(f"插件根路径: {root[1]}")
                print(f"文件路径: {filepath}")
                if line > 0:
                    print(f"定义行号: {line}")

            props = []
            for attr_name in dir(op_class):
                try:
                    attr = getattr(op_class, attr_name, None)
                    if attr is not None and hasattr(attr, '__class__'):
                        cls_name = attr.__class__.__name__
                        if 'Property' in cls_name:
                            props.append(f"{attr_name}({cls_name})")
                except Exception:
                    pass
            if props:
                print(f"\n属性列表:")
                for p in props:
                    print(f"  {p}")

            bases = [base.__name__ for base in op_class.__bases__]
            print(f"\n继承链: {' <- '.join(bases)} <- {op_class.__name__}")

            if hasattr(op_class, 'poll') and callable(getattr(op_class, 'poll', None)):
                try:
                    poll_source = inspect.getsource(op_class.poll)
                    print(f"\npoll() 方法:")
                    for poll_line in poll_source.split('\n'):
                        print(f"  {poll_line}")
                except Exception:
                    pass

            if hasattr(op_class, 'execute') and callable(getattr(op_class, 'execute', None)):
                try:
                    exec_source = inspect.getsource(op_class.execute)
                    print(f"\nexecute() 方法:")
                    for exec_line in exec_source.split('\n'):
                        print(f"  {exec_line}")
                except Exception:
                    pass

            if hasattr(op_class, 'invoke') and callable(getattr(op_class, 'invoke', None)):
                try:
                    inv_source = inspect.getsource(op_class.invoke)
                    print(f"\ninvoke() 方法:")
                    for inv_line in inv_source.split('\n'):
                        print(f"  {inv_line}")
                except Exception:
                    pass
        else:
            print(f"\n此操作符为 Blender 内置 (无 Python 类定义)")
            if filepath:
                print(f"文件路径: {filepath}")

        print(f"\n=== 以上为按钮 {op_id} 完整报告 ===\n")

        self.report({'INFO'}, f"按钮信息已打印: {op_id}")

    def _print_menu_info(self, context):
        menu = context.ui_menu
        cls = menu.__class__

        print(f"\n=== 菜单信息: {getattr(cls, 'bl_idname', cls.__name__)} ===")

        print(f"\n菜单类: {cls.__name__}")
        print(f"  标识符(bl_idname): {getattr(cls, 'bl_idname', '未定义')}")
        print(f"  标签(bl_label): {getattr(cls, 'bl_label', '未定义')}")
        print(f"  模块: {cls.__module__}")

        try:
            filepath = inspect.getfile(cls)
            source_lines, line_num = inspect.getsourcelines(cls)
            print(f"  源代码位置: {filepath}, 第 {line_num} 行")
            root = _get_addon_root(filepath)
            if root:
                print(f"\n所属插件: {root[0]}")
                print(f"插件根路径: {root[1]}")
            else:
                print(f"\n来源: Blender 内置")
        except Exception:
            print(f"\n无法获取源文件路径")

        if hasattr(cls, 'draw') and callable(getattr(cls, 'draw', None)):
            try:
                draw_source = inspect.getsource(cls.draw)
                print(f"\ndraw() 方法:")
                for draw_line in draw_source.split('\n'):
                    print(f"  {draw_line}")
            except Exception:
                pass

        bases = [base.__name__ for base in cls.__bases__]
        print(f"\n继承链: {' <- '.join(bases)} <- {cls.__name__}")

        print(f"\n=== 以上为菜单 {getattr(cls, 'bl_idname', cls.__name__)} 完整报告 ===\n")

        self.report({'INFO'}, f"菜单信息已打印: {getattr(cls, 'bl_idname', cls.__name__)}")

    def _print_tool_info(self, tool_id):
        filepath, line = _get_tool_source(tool_id)

        print(f"\n=== 工具信息: {tool_id} ===")

        tool_class = None
        for cls in bpy.types.WorkSpaceTool.__subclasses__():
            if getattr(cls, "bl_idname", "") == tool_id:
                tool_class = cls
                break

        if tool_class:
            print(f"\n工具类: {tool_class.__name__}")
            print(f"  标识符(bl_idname): {getattr(tool_class, 'bl_idname', '未定义')}")
            print(f"  标签(bl_label): {getattr(tool_class, 'bl_label', '未定义')}")
            print(f"  模块: {tool_class.__module__}")

        if filepath:
            root = _get_addon_root(filepath)
            if root:
                print(f"\n所属插件: {root[0]}")
                print(f"插件根路径: {root[1]}")
            else:
                print(f"\n来源: Blender 内置")
            print(f"文件路径: {filepath}")
            if line > 0:
                print(f"定义行号: {line}")
        else:
            print(f"\n此工具为 Blender 内置 (无 Python 定义)")

        print(f"\n=== 以上为工具 {tool_id} 完整报告 ===\n")

        self.report({'INFO'}, f"工具信息已打印: {tool_id}")


def _context_menu_draw(self, context):
    layout = self.layout
    if _get_tool_id_from_context(context):
        layout.separator()
        layout.operator("better_experie.developer_print_element_info", text="显示工具信息", icon='TOOL_SETTINGS')
        return
    if hasattr(context, "button_operator") and context.button_operator:
        layout.separator()
        layout.operator("better_experie.developer_print_element_info", text="显示按钮信息", icon='FILE_SCRIPT')
    if getattr(context, "ui_menu", None):
        layout.separator()
        layout.operator("better_experie.developer_print_element_info", text="显示菜单信息", icon='PLUGIN')


def all_tag_redraw():
    # 遍历所有窗口 → 所有屏幕 → 所有区域 → 所有区域类型 强制刷新
    for window in bpy.context.window_manager.windows:
        screen = window.screen
        for area in screen.areas:
            area.tag_redraw()
            for region in area.regions:
                region.tag_redraw()

# 检查面板是否已注册
def check_panel_registration(panel_class):
    try:
        bpy.types.Panel.bl_rna_get_subclass_py(panel_class.__name__)
        return True
    except:
        return False

# 根据 ID 查找面板类
def find_panel_class(panel_id):
    # 首先检查是否可以通过bl_idname直接找到
    for cls in bpy.types.Panel.__subclasses__():
        if getattr(cls, 'bl_idname', '') == panel_id:
            return cls
    for cls in bpy.types.Menu.__subclasses__():
        if getattr(cls, 'bl_idname', '') == panel_id:
            return cls
    for cls in bpy.types.Header.__subclasses__():
        if getattr(cls, 'bl_idname', '') == panel_id:
            return cls
    # 如果找不到，尝试通过类名查找
    for cls in bpy.types.Panel.__subclasses__():
        if cls.__name__ == panel_id:
            return cls
    for cls in bpy.types.Menu.__subclasses__():
        if cls.__name__ == panel_id:
            return cls
    for cls in bpy.types.Header.__subclasses__():
        if cls.__name__ == panel_id:
            return cls
    return None

# 创建临时提取按钮
def create_temp_button(panel_class, panel_type):
    def draw_temp_button(self, context):
        layout = self.layout
        row = layout.row()
        row.alert = True
        op = row.operator("better_experie.developer_pick_panel_location", text="提取面板", icon="EYEDROPPER")

        # 获取面板ID（优先使用bl_idname，否则使用类名）
        panel_id = getattr(panel_class, "bl_idname", panel_class.__name__)
        op.panel_id = panel_id
        op.panel_type = panel_type

    # 检查 panel_class 是否有 draw 方法
    if hasattr(panel_class, 'draw'):
        # 存储引用以便后续移除
        panel_class.append(draw_temp_button)
        registered_items.append((panel_class, draw_temp_button))
    else:
        print(f"警告: {panel_class.__name__} 类没有 draw 方法")

# 注册所有面板的临时按钮
def register_all_panels():
    global _picker_active
    # 清空之前的注册项
    unregister_all_panels()
    # 获取所有面板子类
    panel_classes = []
    # 面板
    for cls in bpy.types.Panel.__subclasses__():
        panel_classes.append((cls, "Panel"))
    # 菜单
    for cls in bpy.types.Menu.__subclasses__():
        panel_classes.append((cls, "Menu"))
    # 头部
    for cls in bpy.types.Header.__subclasses__():
        panel_classes.append((cls, "Header"))
    # 创建临时按钮
    for panel_class, panel_type in panel_classes:
        create_temp_button(panel_class, panel_type)

    # 注册右键菜单（按钮/菜单/工具信息提取）
    bpy.types.UI_MT_button_context_menu.append(_context_menu_draw)
    if hasattr(bpy.types, 'UI_MT_menu_context_menu'):
        bpy.types.UI_MT_menu_context_menu.append(_context_menu_draw)

    _picker_active = True


# 注销所有临时按钮
def unregister_all_panels():
    global _picker_active
    for panel_class, draw_func in registered_items:
        try:
            panel_class.remove(draw_func)
        except Exception as e:
            print(f"警告: 无法从 {panel_class.__name__} 中移除临时按钮: {e}")
    registered_items.clear()

    # 注销右键菜单
    if hasattr(bpy.types, 'UI_MT_menu_context_menu'):
        try:
            bpy.types.UI_MT_menu_context_menu.remove(_context_menu_draw)
        except Exception:
            pass
    try:
        bpy.types.UI_MT_button_context_menu.remove(_context_menu_draw)
    except Exception:
        pass

    _picker_active = False


# 插件注册与注销
classes = (
    BetterExperie_OT_DeveloperPanelPicker,
    BetterExperie_OT_DeveloperPickPanelLocation,
    BetterExperie_OT_DeveloperPrintElementInfo,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    

def unregister():
    # 清理残留按钮
    unregister_all_panels()
    
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

#===================================================================================================

if __name__ == "__main__":
    register()