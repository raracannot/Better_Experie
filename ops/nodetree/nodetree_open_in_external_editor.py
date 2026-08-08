# 打开编辑图像

import bpy
import os
import subprocess
import tempfile
import platform

from ...utils.node_tree import get_image_from_selected_node ,set_image_to_node

def ensure_image_saved(image, context):
    # 获取图像的原始路径
    original_path = bpy.path.abspath(image.filepath)
    if image.source == 'FILE' and original_path and os.path.exists(original_path):
        return original_path
    # 如果图像不是文件类型，或者文件不存在，则保存到临时目录
    try:
        # 创建临时目录
        temp_dir = tempfile.mkdtemp(prefix="blender_image_")
        img_name = image.name if image.name else "untitled_image"
        if not img_name.lower().endswith(('.png', '.jpg', '.jpeg', '.tga', '.bmp')):
            img_name += ".png"
        temp_path = os.path.join(temp_dir, img_name)
        original_format = image.file_format
        image.file_format = 'PNG'
        
        # 色彩管理视口变换会影响save_render时的图像，所以要单独记录并还原
        view_settings = context.scene.view_settings
        original_view_settings = view_settings.view_transform
        view_settings.view_transform = 'Standard'
        
        image.save_render(filepath=temp_path)
        
        view_settings.view_transform = original_view_settings
        
        image.file_format = original_format
        print(f"图像已保存到临时目录: {temp_path}")
        return temp_path
    except Exception as e:
        return None


class BetterExperie_OT_OpenInBlenderEditor(bpy.types.Operator):
    bl_idname = "better_experie.open_in_blender_editor"
    bl_label = "在内部编辑器打开图像"
    bl_description = "在内部图像编辑器中打开选中的图像纹理"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        image_list = get_image_from_selected_node(context)
        return image_list is not None
        
    def execute(self, context):
        # 使用通用函数获取所有选中节点中的图像列表
        image_list = get_image_from_selected_node(context)

        # 检查是否找到图像
        if not image_list:
            self.report({'ERROR'}, "未在选中节点中找到任何图像对象")
            return {'CANCELLED'}

        # 取列表中的第一个图像
        node, prop_name, image = image_list[0]

        # 使用渲染分辨率控制窗口大小
        render = context.scene.render
        view = context.preferences.view

        # 保存原始设置
        old_res_x = render.resolution_x
        old_res_y = render.resolution_y
        old_res_percent = render.resolution_percentage
        old_display_type = view.render_display_type

        try:
            # 设置目标分辨率，使图片适配半窗口大小
            # 基于面积计算缩放比例（目标：窗口面积的1/4）
            image_width, image_height = image.size
            window_width = context.window.width
            window_height = context.window.height

            target_area = (window_width*window_height) / 4
            image_area = image_width * image_height
            scale = (target_area / image_area)**0.5
            scale = min(scale, (window_width*0.8) / image_width, (window_height*0.8) / image_height)

            res_x = int(image_width * scale)
            res_y = int(image_height * scale)
            render.resolution_x = res_x
            render.resolution_y = res_y
            render.resolution_percentage = 100
            view.render_display_type = 'WINDOW'

            # 打开窗口
            bpy.ops.render.view_show('INVOKE_DEFAULT')

            # 配置新窗口
            new_window = context.window_manager.windows[-1]
            area = next((_area for _area in new_window.screen.areas if _area.type == 'IMAGE_EDITOR'), None)
            if area:
                # space: SpaceImageEditor = area.spaces.active # type: ignore
                # bpy.types.SpaceImageEditor
                space = area.spaces.active
                space.ui_mode = "PAINT"
                space.image = image
                space.show_region_toolbar = True

                for region in area.regions:
                    if region.type == 'WINDOW':
                        with context.temp_override(window=new_window, area=area, region=region):
                            bpy.ops.image.view_all(fit_view=True)
                            bpy.ops.image.view_zoom_out(location=(0.5, 0.5))
                        break
        except Exception as e:
            self.report({'WARNING'}, f"打开图像编辑器失败:{e}")
        finally:
            # 恢复原始设置
            render.resolution_x = old_res_x
            render.resolution_y = old_res_y
            render.resolution_percentage = old_res_percent
            view.render_display_type = old_display_type

        return {'FINISHED'}  
        
        
class BetterExperie_OT_OpenInExternalEditor(bpy.types.Operator):
    bl_idname = "better_experie.open_in_external_editor"
    bl_label = "在外部编辑器打开图像"
    bl_description = "在外部图像编辑器中打开选中的图像纹理"

    filepath: bpy.props.StringProperty(subtype='FILE_PATH', description="图像编辑器可执行文件路径")
    imagepath: bpy.props.StringProperty(subtype='FILE_PATH', description="要打开的图像文件路径")

    # 其它系统，有没有默认绘图工具
    def invoke(self, context, event):
        # 使用通用函数获取所有选中节点中的图像列表
        image_list = get_image_from_selected_node(context)

        # 检查是否找到图像
        if not image_list:
            self.report({'ERROR'}, "未在选中节点中找到任何图像对象")
            return {'CANCELLED'}

        # 取列表中的第一个图像
        node, prop_name, image = image_list[0]

        # 确保图像已保存（如果需要则保存到临时目录）
        self.imagepath = ensure_image_saved(image, context)
        if not self.imagepath:
            self.report({'ERROR'}, "无法保存临时图像文件")
            return {'CANCELLED'}

        # 检查外部编辑器配置
        editor_path = context.preferences.filepaths.image_editor

        if editor_path and os.path.exists(editor_path):
            # 配置有效，直接打开图像
            return self.execute(context)
        else:
            # 配置无效，自动填充系统默认路径（如有）
            if platform.system() == "Windows":
                default_path = r"C:\Windows\System32\mspaint.exe"
            elif platform.system() == "Darwin":
                default_path = r"/Applications/Preview.app/Contents/MacOS/Preview"
            elif platform.system() == "Linux":
                default_path = r"/usr/bin/gimp"
            if os.path.exists(default_path):
                self.filepath = default_path
            # 弹出文件选择器
            context.window_manager.fileselect_add(self)
            return {'RUNNING_MODAL'}
        return {'FINISHED'}

    def execute(self, context):
        if self.filepath:
            if os.path.exists(self.filepath):
                context.preferences.filepaths.image_editor = self.filepath
                self.report({'INFO'}, f"已设置外部编辑器: {os.path.basename(self.filepath)}")
            else:
                self.report({'ERROR'}, "外部编辑器路径无效，请重新选择")
                return {'CANCELLED'}
        try:
            bpy.ops.image.external_edit(filepath=self.imagepath)
        except Exception as e:
            self.report({'ERROR'}, f"启动外部编辑器失败: {str(e)}")
            return {'CANCELLED'}
        self.report({'INFO'}, f"已在外部编辑器打开图像{self.imagepath}")
        return {'FINISHED'}


class BetterExperie_OT_ReloadImage(bpy.types.Operator):
    bl_idname = "better_experie.reload_image"
    bl_label = "重载图像"
    bl_description = "重新加载选中图像节点的所有图像文件"

    @classmethod
    def poll(cls, context):
        image_list = get_image_from_selected_node(context)
        if not image_list:
            return False
        have_image_path = False
        for _, _, image in image_list:
            image_path = bpy.path.abspath(image.filepath)
            if image_path or os.path.exists(image_path):
                have_image_path = True
                break
        return have_image_path

    def execute(self, context):
        # 使用通用函数获取所有选中节点中的图像列表
        image_list = get_image_from_selected_node(context)
        # 检查是否找到图像
        if not image_list:
            self.report({'ERROR'}, "未在选中节点中找到任何图像对象！")
            return {'CANCELLED'}
        # 统计成功/失败数量
        success_count = 0
        # 遍历所有找到的图像进行重载
        for node, prop_name, image in image_list:
            # 获取图像绝对路径
            image_path = bpy.path.abspath(image.filepath)
            # 检查路径是否存在（仅对文件类型图像验证，内嵌/临时图像跳过路径检查）
            if image.source == 'FILE' and (not image_path or not os.path.exists(image_path)):
                print(f"{image.name} (节点: {node.name}) - 文件不存在")
                continue
            try: # 执行图像重载
                image.reload()
                success_count += 1
            except Exception as e:
                print(f"{image.name} (节点: {node.name}) - {str(e)}")
        # 生成反馈信息
        if success_count > 0:
            self.report({'INFO'}, f"成功重载 {success_count}/{len(image_list)} 个图像")
        else:
            self.report({'ERROR'}, f"重载图像失败")
        return {'FINISHED'}


class BetterExperie_OT_OpenImageFolder(bpy.types.Operator):
    bl_idname = "better_experie.open_image_folder"
    bl_label = "打开文件夹"
    bl_description = "打开选中图像所在的文件夹"

    @classmethod
    def poll(cls, context):
        image_list = get_image_from_selected_node(context)
        if image_list:
            _, _, image = image_list[0]
            image_path = bpy.path.abspath(image.filepath)
            if image_path or os.path.exists(image_path):
                return True
        return False

    def execute(self, context):
        # 使用通用函数获取所有选中节点中的图像列表
        image_list = get_image_from_selected_node(context)
        # 检查是否找到图像
        if not image_list:
            self.report({'ERROR'}, "未在选中节点中找到任何图像对象！")
            return {'CANCELLED'}
        # 取列表中的第一个图像
        node, prop_name, image = image_list[0]
        image_path = bpy.path.abspath(image.filepath)
        # 检查路径是否存在
        if not image_path or not os.path.exists(image_path):
            self.report({'ERROR'}, f"图像文件不存在（{image.name}），无法打开文件夹！")
            return {'CANCELLED'}
        # 获取文件夹路径
        folder_path = os.path.dirname(image_path)

        try:
            # 不使用原生，因为原生在5.0会有概率造成卡死
            # 根据不同系统打开文件夹（跨平台兼容）
            if platform.system() == "Windows":
                os.startfile(folder_path)
            elif platform.system() == "Darwin":  # macOS
                subprocess.run(["open", folder_path], check=True)
            else:  # Linux
                subprocess.run(["xdg-open", folder_path], check=True)
            self.report({'INFO'}, f"已打开文件夹: {folder_path} (图像: {image.name})")
        except subprocess.CalledProcessError as e:
            self.report({'ERROR'}, f"打开文件夹失败: 命令执行错误 - {str(e)}")
            return {'CANCELLED'}
        except Exception as e:
            self.report({'ERROR'}, f"打开文件夹失败: {str(e)}")
            return {'CANCELLED'}
        return {'FINISHED'}


# 注册/注销函数
classes = (
    BetterExperie_OT_ReloadImage,
    BetterExperie_OT_OpenImageFolder,
    BetterExperie_OT_OpenInBlenderEditor,
    BetterExperie_OT_OpenInExternalEditor,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
