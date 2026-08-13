# 检查更新：网络检测 → 目录权限检测 → 确保 RARA 扩展库存在 → 跳转 Get Extensions

import os
import urllib.request
import bpy

REPO_NAME = "RARA Extensions"
REPO_MODULE = "rara_extensions"
REPO_URL = "https://raracannot.github.io/extensions/index.json"


def _addon_dir():
    """返回插件根目录（本文件位于 ops/other/ 三层之下）"""
    return os.path.dirname(os.path.dirname(os.path.dirname(__file__)))


def _find_repo():
    """在所有扩展库中查找已包含 RARA 更新链接的仓库"""
    for repo in bpy.context.preferences.extensions.repos:
        if repo.remote_url == REPO_URL:
            return repo
    return None


def _ensure_repo():
    """若 RARA 扩展库不存在则新建，返回仓库对象"""
    repo = _find_repo()
    if repo is not None:
        return repo
    repo = bpy.context.preferences.extensions.repos.new(
        name=REPO_NAME,
        module=REPO_MODULE,
        remote_url=REPO_URL,
        source='USER',
    )
    repo.use_cache = True
    
    try: #新建后要自动保存
        bpy.ops.wm.save_userpref()
    except Exception:
        pass
    return repo
    
class BetterExperie_OT_CheckUpdate(bpy.types.Operator):
    bl_idname = "better_experie.check_update"
    bl_label = "检查更新"
    bl_description = "快速跳转至RARA插件库，查看可更新情况"
    bl_options = {'REGISTER'}

    def execute(self, context):
        # 插件目录读写权限检测
        addon_dir = _addon_dir()
        if not os.access(addon_dir, os.W_OK):
            self.report({'ERROR'}, f"插件所在文件夹{addon_dir}无写入权限，更新可能受阻，建议尝试以管理员启动blender，或手动将插件所在目录文件夹取消只读")

        try: # 检查/创建 RARA 扩展库
            repo = _ensure_repo()
        except Exception as e:
            self.report({'ERROR'}, f"创建扩展库失败: {e}")
            return {'CANCELLED'}

        try:
            # 尽力同步仓库，使插件列表可加载（失败不阻断跳转）
            bpy.ops.extensions.repo_sync('EXEC_DEFAULT', repo_directory=repo.directory)
        except Exception:
            pass

        try: # 跳转显示偏好设置界面
            bpy.ops.screen.userpref_show('INVOKE_DEFAULT')
        except Exception:
            pass

        try: #跳转至【获取扩展】
            bpy.context.preferences.active_section = 'EXTENSIONS'
        except Exception:
            pass

        wm = bpy.data.window_managers["WinMan"]
        try: #设置筛选条件便于查找更新
            wm.extension_use_filter = True
            wm.extension_type = 'ADDON'
            wm.extension_repo_filter = repo.module
        except Exception:
            pass
        
        try: #展开小面板
            bpy.ops.extensions.package_show_set(pkg_id="better_experie", repo_index=1)
        except Exception:
            pass

        self.report({'INFO'}, f"已跳转至 {REPO_NAME}，可查看最新版本并更新")
        
        # 检查插件所在库
        parts = [p for p in addon_dir.split(os.sep) if p.strip()]
        addon_folder_name = parts[-2] if len(parts)>=2 else ""
        if addon_folder_name != repo.module:
            self.report({'INFO'}, f"插件当前安装至{addon_folder_name}，有可能未安装至插件库{repo.module}中，为方便在线更新，建议先卸载本插件再在【偏好设置】【获取插件】里手动进行安装【更好的体验】")
            print("#"*50)
            print(f"当前安装路径为{addon_dir}")
            print(f"所在插件库为{addon_folder_name}")
            print(f"推荐插件库为{repo.module}")
            print("#"*50)
            
        return {'FINISHED'}


classes = (
    BetterExperie_OT_CheckUpdate,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
