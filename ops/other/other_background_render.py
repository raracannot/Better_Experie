# 后台渲染工具
# 漓舒s 提供

import os
import bpy
import stat
import platform
import subprocess

_running_render_processes = []


def _get_cycles_devices(context):
    cycles_prefs = context.preferences.addons.get("cycles")
    if cycles_prefs:
        device_type = cycles_prefs.preferences.compute_device_type
        devices = cycles_prefs.preferences.get_devices_for_type(device_type)
        enabled_devices = [d["name"] for d in devices if d.use]
        return device_type, enabled_devices
    return "CPU", []


def _get_scene_frame_range(context):
    scene = context.scene
    return scene.frame_start, scene.frame_end


def _get_current_frame(context):
    return context.scene.frame_current


def _get_actual_output_path(context, setting):
    output_path = context.scene.render.filepath if setting.use_scene_filepath else setting.filepath
    return bpy.path.abspath(output_path)

# 保守渲染条件
CONSERVATIVE_SCRIPT = """import bpy
bpy.context.preferences.system.use_online_access = False
bpy.context.scene.cycles.denoising_use_gpu = False
bpy.context.scene.render.compositor_device = 'CPU'
bpy.context.scene.render.compositor_denoise_device = 'CPU'
"""

def _generate_render_command(context, setting):
    blender_path = bpy.app.binary_path
    filepath = bpy.data.filepath
    output_path = _get_actual_output_path(context, setting)

    cmd = [
        blender_path,
        "--factory-startup",
        "-b",
        filepath,
        "-o", output_path,
    ]
    if hasattr(setting, "use_conservative_mode") and setting.use_conservative_mode:
        clean_script = "; ".join([line.strip() for line in CONSERVATIVE_SCRIPT.splitlines() if line.strip()])
        cmd.extend(["--python-expr", clean_script])
    if setting.operator_type == 'STILL':
        if setting.use_scene_frame:
            frame = _get_current_frame(context)
        else:
            frame = setting.frame_current
        cmd.extend(['-f', str(frame)])
    else:
        if setting.use_scene_frame:
            start, end = _get_scene_frame_range(context)
        else:
            start = setting.frame_start
            end = setting.frame_end
        cmd.extend(['--frame-start', str(start), '--frame-end', str(end), '-a'])

    device_type, enabled_devices = _get_cycles_devices(context)
    if enabled_devices and device_type != 'CPU':
        cmd.extend(['--', '--cycles-device', device_type])
        cmd.extend(['--cycles-use-device'] + enabled_devices)
    else:
        cmd.extend(['--', '--cycles-device', 'CPU'])

    return cmd


def _generate_batch_file(context, setting):
    system = platform.system()
    output_path = _get_actual_output_path(context, setting)
    output_dir = os.path.dirname(output_path)

    batch_file = os.path.join(
        output_dir,
        "batch_render.bat" if system == "Windows" else "batch_render.sh"
    )
    cmd = _generate_render_command(context, setting)
    cmd_str = ' '.join([f'"{c}"' if ' ' in str(c) else str(c) for c in cmd])
    if system == "Windows":
        content = f"@echo off\n{cmd_str}\npause\n"
    else:
        content = f"#!/bin/bash\n{cmd_str}\necho '渲染完成，按回车退出...'; read\n"

    try:
        with open(batch_file, "w", encoding="utf-8") as f:
            f.write(content)
    except Exception as e:
        print(f"写入批处理文件失败: {e}")

    if system != "Windows":
        os.chmod(batch_file, stat.S_IRWXU)
    return batch_file


def _execute_background_render(context, setting):
    global _running_render_processes

    if hasattr(setting, "frame_start") and hasattr(setting, "frame_end"):
        start = setting.frame_start
        end = setting.frame_end
        if start > end:
            setting.frame_start, setting.frame_end = end, start

    try:
        cmd = _generate_render_command(context, setting)

        output_path = _get_actual_output_path(context, setting)
        output_dir = os.path.dirname(output_path)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)

        system = platform.system()
        startupinfo = None
        if system == 'Windows':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

        process = subprocess.Popen(
            cmd,
            shell=False,
            startupinfo=startupinfo if system == 'Windows' else None
        )

        _running_render_processes.append(process)

        if setting.generate_batch_file:
            batch_file = _generate_batch_file(context, setting)
            print(f"已生成批处理文件：{batch_file}")

        if setting.open_dir:
            _open_dir_cross_platform(output_dir)

        return {'FINISHED'}
    except Exception as e:
        context.window_manager.popup_menu(
            lambda self, context: self.layout.label(text=str(e)),
            title="渲染错误",
            icon='ERROR'
        )
        return {'CANCELLED'}


def _open_dir_cross_platform(dir_path):
    dir_path = os.path.abspath(dir_path)
    system = platform.system()
    if system == 'Windows':
        os.startfile(dir_path)
    elif system == 'Darwin':
        subprocess.Popen(['open', dir_path])
    else:
        subprocess.Popen(['xdg-open', dir_path])


class BetterExperie_OT_BackgroundRenderExecute(bpy.types.Operator):
    bl_idname = "better_experie.background_render_execute"
    bl_label = "后台渲染"
    bl_description = "点击后设置参数并执行后台渲染，请确保本文件已进行过保存"
    bl_options = {'REGISTER'}

    operator_type: bpy.props.EnumProperty(
        name="渲染类型",
        items=[
            ('STILL', "单帧渲染", "渲染当前帧"),
            ('ANIM', "动画渲染", "渲染动画序列"),
        ], default='STILL')

    use_scene_frame: bpy.props.BoolProperty(
        name="使用场景帧", description="使用场景当前帧信息进行渲染", default=True)
    frame_current: bpy.props.IntProperty(
        name="指定帧号", description="要渲染的帧编号", default=1, min=1)
    frame_start: bpy.props.IntProperty(
        name="起始帧", default=1, min=1)
    frame_end: bpy.props.IntProperty(
        name="结束帧", default=250, min=1)

    use_scene_filepath: bpy.props.BoolProperty(
        name="使用场景输出路径", description="使用场景设置的输出路径", default=True)
    filepath: bpy.props.StringProperty(
        name="自定义路径", description="自定义输出路径", subtype='FILE_PATH', default="//render/")

    generate_batch_file: bpy.props.BoolProperty(
        name="生成批处理文件", description="执行后创建渲染批处理文件", default=False)
    open_dir: bpy.props.BoolProperty(
        name="打开输出目录", description="渲染完成后打开输出目录", default=False)
    
    use_conservative_mode: bpy.props.BoolProperty(
        name="保守渲染 (推荐)", description="渲染时，断开网络验证并取消GPU降噪，以提升稳定性", 
        default=False)
    
    @classmethod
    def poll(cls, context):
        return bpy.data.is_saved

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=350)

    def draw(self, context):
        layout = self.layout
        col = layout.column(align=True)

        row = col.row()
        row.prop(self, "operator_type", expand=True)
        col.separator()

        col.prop(self, "use_scene_frame", text="使用场景帧信息" if self.use_scene_frame else "使用自定义帧信息：")
        if not self.use_scene_frame:
            if self.operator_type == 'STILL':
                row = col.row(align=True)
                row.prop(self, "frame_current", text="渲染帧")
            else:
                row = col.row(align=True)
                row.prop(self, "frame_start", text="起始帧")
                row.prop(self, "frame_end", text="结束帧")
            col.separator()

        col.prop(self, "use_scene_filepath", text="使用场景输出路径" if self.use_scene_filepath else "使用自定义输出路径：")
        if not self.use_scene_filepath:
            col.prop(self, "filepath", text="")

        col.separator()
        col.prop(self, "generate_batch_file")
        col.prop(self, "open_dir")
        col.prop(self, "use_conservative_mode")

    def execute(self, context):
        return _execute_background_render(context, self)


class BetterExperie_OT_BackgroundRenderKill(bpy.types.Operator):
    bl_idname = "better_experie.background_render_kill"
    bl_label = "强制终止后台渲染"
    bl_description = "强制结束所有正在运行的后台渲染进程"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        global _running_render_processes
        _running_render_processes = [p for p in _running_render_processes if p.poll() is None]
        return len(_running_render_processes) > 0

    def execute(self, context):
        global _running_render_processes
        killed_count = 0

        for p in _running_render_processes:
            if p.poll() is None:
                try:
                    p.terminate()
                    killed_count += 1
                except Exception as e:
                    self.report({'ERROR'}, f"终止进程失败: {e}")

        _running_render_processes.clear()

        if killed_count > 0:
            self.report({'INFO'}, f"已强制终止 {killed_count} 个后台渲染进程")

        return {'FINISHED'}


class BETTER_EXPERIE_MT_background_render(bpy.types.Menu):
    bl_label = "后台渲染工具"
    bl_idname = "BETTER_EXPERIE_MT_background_render"

    def draw(self, context):
        layout = self.layout
        layout.operator(
            "better_experie.background_render_execute",
            text="配置并开始后台渲染",
            icon='RENDER_RESULT'
        )
        layout.operator(
            "better_experie.background_render_kill",
            text="强制终止后台渲染",
            icon='CANCEL'
        )


classes = (
    BetterExperie_OT_BackgroundRenderExecute,
    BetterExperie_OT_BackgroundRenderKill,
    BETTER_EXPERIE_MT_background_render,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
