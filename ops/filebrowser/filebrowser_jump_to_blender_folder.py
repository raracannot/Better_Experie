# blender文件管理器右键工具

import bpy
import sys
import os
import subprocess

IS_WINDOWS = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"
IS_LINUX = sys.platform.startswith("linux")

def get_target_path (context):
    # 从文件浏览器的上下文中获取要打开的目标路径（优先选中的文件/文件夹的完整路径）
    space = context.space_data
    if not space or space.type != 'FILE_BROWSER':
        return None

    current_dir = space.params.directory.decode('utf-8')
    target_path = None

    # 优先使用当前激活的文件（高亮项）
    active = context.active_file
    if active:
        # 检查是否有 relative_path 属性（递归模式下会存在）
        if hasattr(active, 'relative_path') and active.relative_path:
            # 使用相对路径拼接，例如：current_dir + "美甲测试\05.png"
            target_path = os.path.join(current_dir, active.relative_path)
        elif hasattr(active, 'name'):
            # 非递归模式，只有 name
            target_path = os.path.join(current_dir, active.name)
        else:
            target_path = current_dir  # 回退

    # 如果没有 active_file，则尝试使用 selected_files 的第一项
    elif context.selected_files:
        selected_name = context.selected_files[0].name
        target_path = os.path.join(current_dir, selected_name)

    # 最后保底：打开当前目录
    if not target_path:
        target_path = current_dir
    print(f"准备打开{target_path}") 
    return target_path


class BetterExperie_OT_JumpSelectedFolder(bpy.types.Operator):
    bl_idname = "better_experie.jump_selected_folder"
    bl_label = "打开所选文件夹"
    bl_description = "在系统资源管理器中打开当前选中的文件夹 / 文件所在文件夹"

    def execute(self, context):
        space = context.space_data
        if not space or space.type != 'FILE_BROWSER':
            self.report({"WARNING"}, "请在文件浏览器中使用")
            return {"CANCELLED"}

        target_path = get_target_path(context)
        if not target_path:
            self.report({"WARNING"}, "无法获取有效路径")
            return {"CANCELLED"}

        try:
            if IS_WINDOWS:
                subprocess.run(f'explorer /select,"{target_path}"', shell=False)
            elif IS_MAC:
                subprocess.run(['open', '-R', target_path])
            elif IS_LINUX:
                subprocess.run(['xdg-open', '--select', target_path])
        except Exception as e:
            self.report({"WARNING"}, f"打开失败: {e}")
            return {"CANCELLED"}

        return {"FINISHED"}
        

class BetterExperie_OT_JumpToFileLocation(bpy.types.Operator):
    bl_idname = "better_experie.jump_to_file_location"
    bl_label = "跳转到文件所在层级"
    bl_description = "将当前目录切换为选中文件/文件夹的实际所在位置，并高亮该文件/文件夹（仅在递归显示模式下有效）"

    def execute(self, context):
        space = context.space_data
        if not space or space.type != 'FILE_BROWSER':
            self.report({"WARNING"}, "请在文件浏览器中使用")
            return {"CANCELLED"}

        # 仅在递归显示模式下生效
        if space.params.recursion_level == 'NONE':
            self.report({"WARNING"}, "当前已在顶层（无递归显示），无需跳转")
            return {"CANCELLED"}

        target_path = get_target_path(context)
        if not target_path:
            self.report({"WARNING"}, "无法获取选中项的路径")
            return {"CANCELLED"}

        # 计算新目录：如果是文件则取其所在文件夹，如果是文件夹则取该文件夹本身
        if os.path.isfile(target_path):
            new_dir = os.path.dirname(target_path)
        else:
            new_dir = target_path

        if not os.path.exists(new_dir):
            self.report({"WARNING"}, f"目标目录不存在: {new_dir}")
            return {"CANCELLED"}

        # 获取选中项的基础名称（用于跳转后高亮）
        relative_name = os.path.basename(target_path)
        # 更改文件浏览器当前目录
        space.params.directory = new_dir.encode('utf-8')

        # 延迟高亮，等待文件列表刷新
        def delayed_highlight():
            try:
                space.activate_file_by_relative_path(relative_path=relative_name)
                print (f"已跳转到: {new_dir} 并选中 {relative_name}")
            except Exception as e:
                print (f"跳转成功，但无法自动高亮文件: {e}")
            return None  # 确保定时器只运行一次

        # 添加定时器，延迟 0.1 秒执行
        bpy.app.timers.register(delayed_highlight, first_interval=0.3)
        
        self.report({"INFO"}, f"已跳转到: {new_dir}")
        return {"FINISHED"}

        
class BetterExperie_OT_OpenAndJumpToFolder(bpy.types.Operator):
    bl_idname = "better_experie.open_and_jump_to_folder"
    bl_label = "跳转文件夹"
    bl_description = "一键跳转或打开工程文件夹 / 输出文件夹"

    open_folder: bpy.props.EnumProperty(
        name="打开或跳转",description="选择打开或跳转文件夹的模式",
        items=[
            ('PROJECT', "工程文件夹", "进入本项目所在的文件夹"),
            ('OUTPUT', "输出文件夹", "进入输出所在的文件夹")
        ],default='PROJECT')
        
    open_mode: bpy.props.EnumProperty(
        name="打开或跳转",description="选择打开或跳转文件夹的模式",
        items=[
            ('OPEN', "打开", "打开该文件夹"),
            ('JUMP', "跳转", "跳转至文件夹")
        ],default='OPEN')

    def execute(self, context):
        target_dir = None # 最终目标：永远是文件夹
        if self.open_folder == "PROJECT":
            blend_path = bpy.data.filepath
            if not blend_path:
                self.report({"WARNING"}, "请先保存工程文件")
                return {"CANCELLED"}
            # 获取 blend 文件所在的文件夹    
            target_dir = os.path.dirname(blend_path)
                
        elif self.open_folder == "OUTPUT":
            output_path = bpy.path.abspath(context.scene.render.filepath)
            # 获取输出文件所在的文件夹
            target_dir = os.path.dirname(output_path) 
        else:
            self.report({"WARNING"}, "暂未支持的选项")
            return {"CANCELLED"}
        
        # 确保路径存在
        if not os.path.exists(target_dir):
            try:
                os.makedirs(target_dir, exist_ok=True)
            except:
                self.report({"WARNING"}, "无法创建文件夹")
                return {"CANCELLED"}
                
        if self.open_mode == "OPEN":
            try:
                if IS_WINDOWS:
                    os.startfile(target_dir)
                elif IS_MAC:
                    subprocess.run(["open", target_dir], check=True)
                elif IS_LINUX:
                    subprocess.run(["xdg-open", target_dir], check=True)
            except Exception as e:
                self.report({"WARNING"}, f"打开文件夹失败：{e}")
                return {"CANCELLED"}
        elif self.open_mode == "JUMP":
            for area in context.screen.areas:
                if area.type == 'FILE_BROWSER':
                    for space in area.spaces:
                        if space.type == 'FILE_BROWSER':
                            # 直接跳转文件夹
                            space.params.directory = target_dir.encode()
                            # space.params.directory = os.path.dirname(target_dir).encode()    
            self.report({"INFO"}, "已跳转至目标文件夹")
        else:
            self.report({"WARNING"}, "暂未支持的选项")
            return {"CANCELLED"}
        
        return {'FINISHED'}


classes = (
    BetterExperie_OT_JumpSelectedFolder,
    BetterExperie_OT_JumpToFileLocation,
    BetterExperie_OT_OpenAndJumpToFolder,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)