# 资产库移动管理工具：在资产浏览器中移动、删除、重命名资产（后台 Blender 子进程执行）

import bpy
import os
import json
import tempfile
import subprocess
import textwrap
import threading

_UNASSIGNED_CATALOG_ID = "00000000-0000-0000-0000-000000000000"
_CATALOG_ENUM_CACHE = []
_BLEND_ENUM_CACHE = []
_LIBRARY_ENUM_CACHE = []
_BACKGROUND_JOBS = []

_ID_TYPE_TO_COLLECTION = {
    "OBJECT": "objects",
    "COLLECTION": "collections",
    "MATERIAL": "materials",
    "WORLD": "worlds",
    "ACTION": "actions",
    "BRUSH": "brushes",
    "NODETREE": "node_groups",
    "MESH": "meshes",
    "CURVE": "curves",
    "CAMERA": "cameras",
    "LIGHT": "lights",
    "IMAGE": "images",
}


def _get_collection_name_from_id(id_data):
    if isinstance(id_data, bpy.types.Object):
        return "objects"
    if isinstance(id_data, bpy.types.Collection):
        return "collections"
    if isinstance(id_data, bpy.types.Material):
        return "materials"
    if isinstance(id_data, bpy.types.World):
        return "worlds"
    if isinstance(id_data, bpy.types.Action):
        return "actions"
    if isinstance(id_data, bpy.types.Brush):
        return "brushes"
    if isinstance(id_data, bpy.types.NodeTree):
        return "node_groups"
    if isinstance(id_data, bpy.types.Mesh):
        return "meshes"
    if isinstance(id_data, bpy.types.Curve):
        return "curves"
    if isinstance(id_data, bpy.types.Camera):
        return "cameras"
    if isinstance(id_data, bpy.types.Light):
        return "lights"
    if isinstance(id_data, bpy.types.Image):
        return "images"
    return None


def _get_selected_asset_records(context):
    selected_assets = getattr(context, "selected_assets", []) or []
    records = []
    for asset_repr in selected_assets:
        local_id = getattr(asset_repr, "local_id", None)

        if local_id is not None and isinstance(local_id, bpy.types.ID):
            collection_name = _get_collection_name_from_id(local_id)
            if collection_name is None:
                print(f"警告：不支持的当前文件资产类型：{type(local_id).__name__}")
                continue

            records.append({
                "name": local_id.name,
                "collection": collection_name,
                "source": "",
                "local": True,
                "id_data": local_id,
            })
            continue

        asset_name = getattr(asset_repr, "name", "")
        source_path = getattr(asset_repr, "full_library_path", "")
        id_type = getattr(asset_repr, "id_type", "")

        if id_type:
            id_type = str(id_type).upper()
            if "." in id_type:
                id_type = id_type.split(".")[-1]
            collection_name = _ID_TYPE_TO_COLLECTION.get(id_type)
        else:
            collection_name = None

        if not asset_name:
            print("警告：无法读取外部资产名称。")
            continue
        if not source_path:
            print(f"警告：无法读取外部资产源文件：{asset_name}")
            continue
        if collection_name is None:
            print(f"警告：不支持的外部资产类型：{id_type} / {asset_name}")
            continue

        records.append({
            "name": asset_name,
            "collection": collection_name,
            "source": os.path.normpath(bpy.path.abspath(source_path)),
            "local": False,
            "id_data": None,
        })
    return records


def _get_asset_library_records(context=None):
    records = []
    try:
        preferences = (context.preferences if context is not None else bpy.context.preferences)
        for library in preferences.filepaths.asset_libraries:
            library_name = library.name.strip()
            library_path = bpy.path.abspath(library.path).strip()
            if not library_name or not library_path:
                continue

            records.append({
                "name": library_name,
                "path": os.path.normpath(library_path),
            })

    except Exception as exc:
        print(f"错误：无法读取本地资产库：{exc}")
    records.sort(key=lambda item: item["name"].lower())
    return records


def _get_selected_library_root(selected_library, context=None):
    if not selected_library or selected_library == "NONE":
        return ""
    for library in _get_asset_library_records(context):
        identifier = f"LIB::{library['name']}"
        if identifier == selected_library:
            return library["path"]
    return ""


def _get_catalog_file_path(library_root):
    return os.path.join(library_root, "blender_assets.cats.txt")


def _create_background_script(script_path):
    script_content = r'''
import bpy
import sys
import os
import json
import traceback

def get_arguments():
    argv = sys.argv
    if "--" not in argv:
        return []
    return argv[argv.index("--") + 1:]

def find_data_block(collection_name, data_name):
    collection = getattr(bpy.data, collection_name, None)
    if collection is None:
        return None
    for data_block in collection:
        if data_block.name == data_name:
            return data_block
    return None

def remove_data_block(collection_name, data_name):
    collection = getattr(bpy.data, collection_name, None)
    data_block = find_data_block(collection_name, data_name)

    if collection is None or data_block is None:
        print(f"警告：未找到资产：{collection_name} / {data_name}")
        return False
    try:
        collection.remove(data_block, do_unlink=True)
    except TypeError:
        collection.remove(data_block)

    print(f"已删除资产：{collection_name} / {data_name}")
    return True

def assign_catalog(data_block, catalog_id):
    try:
        if data_block.asset_data is None:
            data_block.asset_mark()
        data_block.asset_data.catalog_id = catalog_id
        print(f"已设置目录：{data_block.name} -> {catalog_id}")
        return True
    except Exception as exc:
        print(f"警告：无法设置资产目录：{data_block.name} / {exc}")
        return False

def save_current_file(filepath):
    bpy.ops.wm.save_as_mainfile(filepath=filepath,check_existing=False,compress=True,)

def run_move(payload):
    target_blend = os.path.normpath(payload["target_blend"])

    target_catalog_id = payload["catalog_id"]
    allow_duplicate = payload["allow_duplicate"]
    records = payload["records"]

    if not os.path.isfile(target_blend):
        raise RuntimeError(f"目标文件不存在：{target_blend}")

    bpy.ops.wm.open_mainfile(filepath=target_blend)

    same_file_records = []
    external_records = []

    for record in records:
        source_path = os.path.normpath(record["source"])
        if os.path.normcase(source_path) == os.path.normcase(target_blend):
            same_file_records.append(record)
        else:
            external_records.append(record)

    # 同一 Blend 内移动：直接修改 catalog_id。
    for record in same_file_records:
        data_block = find_data_block(record["collection"],record["name"],)
        if data_block is None:
            print(f"警告：未找到同文件资产：{record['collection']} / {record['name']}")
            continue
        assign_catalog(data_block, target_catalog_id)

    existing_names = {}
    for record in external_records:
        collection_name = record["collection"]
        if collection_name in existing_names:
            continue

        collection = getattr(bpy.data,collection_name,None,)
        if collection is None:
            existing_names[collection_name] = set()
        else:
            existing_names[collection_name] = {item.name for item in collection}

    accepted_records = []
    for record in external_records:
        collection_name = record["collection"]
        asset_name = record["name"]
        if not allow_duplicate:
            if asset_name in existing_names.get(collection_name, set()):
                print(f"跳过同名资产：{collection_name} / {asset_name}")
                continue
        accepted_records.append(record)

    source_groups = {}
    for record in accepted_records:
        source_path = record["source"]
        collection_name = record["collection"]
        if source_path not in source_groups:
            source_groups[source_path] = {}
        if collection_name not in source_groups[source_path]:
            source_groups[source_path][collection_name] = []

        source_groups[source_path][collection_name].append(record["name"])

    imported_assets = []
    for source_path, collection_groups in source_groups.items():
        if not os.path.isfile(source_path):
            print(f"警告：源文件不存在：{source_path}")
            continue

        print(f"正在追加源文件：{source_path}")
        with bpy.data.libraries.load(source_path,link=False,) as (data_from, data_to):
            for collection_name, names in collection_groups.items():
                if hasattr(data_from, collection_name):
                    setattr(data_to,collection_name,names,)

        for collection_name in collection_groups:
            appended_items = getattr(data_to,collection_name,[],)
            for data_block in appended_items:
                if data_block is not None:
                    imported_assets.append(data_block)

    for data_block in imported_assets:
        assign_catalog(data_block, target_catalog_id)
    save_current_file(target_blend)
    print(f"目标文件已保存：{target_blend}")

    delete_groups = {}
    for record in accepted_records:
        if not record.get("delete_source", False):
            continue
        source_path = record["source"]
        if source_path not in delete_groups:
            delete_groups[source_path] = []
        delete_groups[source_path].append(record)

    for source_path, delete_records in delete_groups.items():
        if not os.path.isfile(source_path):
            print(f"警告：源文件不存在：{source_path}")
            continue
        if os.path.normcase(source_path) == os.path.normcase(target_blend):
            continue

        bpy.ops.wm.open_mainfile(filepath=source_path)
        for record in delete_records:
            remove_data_block(record["collection"],record["name"],)
        save_current_file(source_path)
        print(f"源文件已保存：{source_path}")
    print("后台移动任务完成")

def run_delete(payload):
    source_groups = {}
    for record in payload["records"]:
        source_path = record["source"]
        if source_path not in source_groups:
            source_groups[source_path] = []
        source_groups[source_path].append(record)

    for source_path, records in source_groups.items():
        if not os.path.isfile(source_path):
            print(f"警告：源文件不存在：{source_path}")
            continue
        bpy.ops.wm.open_mainfile(filepath=source_path)
        for record in records:
            remove_data_block(record["collection"],record["name"],)

        save_current_file(source_path)
        print(f"删除结果已保存：{source_path}")
    print("后台删除任务完成")

def run_rename(payload):
    source_path = payload["source"]
    collection_name = payload["collection"]
    old_name = payload["old_name"]
    new_name = payload["new_name"]
    if not os.path.isfile(source_path):
        raise RuntimeError(f"源文件不存在：{source_path}")

    bpy.ops.wm.open_mainfile(filepath=source_path)
    data_block = find_data_block(collection_name,old_name,)
    if data_block is None:
        raise RuntimeError(f"未找到待重命名资产：{collection_name} / {old_name}")
    data_block.name = new_name
    save_current_file(source_path)
    print(f"重命名完成：{old_name} -> {new_name}")

def main():
    arguments = get_arguments()
    if not arguments:
        raise RuntimeError("缺少后台任务参数。")

    payload = json.loads(arguments[0])
    operation = payload.get("operation", "")
    if operation == "move":
        run_move(payload)
    elif operation == "delete":
        run_delete(payload)
    elif operation == "rename":
        run_rename(payload)
    else:
        raise RuntimeError(f"不支持的任务类型：{operation}")
    print("QMA_BACKGROUND_SUCCESS")

if __name__ == "__main__":
    try:
        main()
    except Exception:
        print("QMA_BACKGROUND_FAILED")
        print(traceback.format_exc())
        sys.exit(1)
'''
    with open(script_path, "w", encoding="utf-8") as file:
        file.write(textwrap.dedent(script_content))


def _cleanup_temp_files(temp_dir, source_blend, script_path):
    try:
        if script_path and os.path.isfile(script_path):
            os.remove(script_path)
        if source_blend and os.path.isfile(source_blend):
            os.remove(source_blend)
        if temp_dir and os.path.isdir(temp_dir):
            if not os.listdir(temp_dir):
                os.rmdir(temp_dir)
    except Exception as exc:
        print(f"警告：清理临时文件失败：{exc}")


def _wait_for_background_job(process, temp_dir, source_blend, script_path, task_name):
    try:
        stdout, stderr = process.communicate()
        print(f"\n========== 后台{task_name}日志 ==========")
        print(stdout)
        if stderr:
            print("---------- 错误输出 ----------")
            print(stderr)
        if process.returncode == 0 and "QMA_BACKGROUND_SUCCESS" in stdout:
            print(f"========== 后台{task_name}完成 ==========")
        else:
            print(f"========== 后台{task_name}失败 ==========")
            print(f"返回代码：{process.returncode}")
    except Exception as exc:
        print(f"错误：等待后台任务失败：{exc}")

    finally:
        _cleanup_temp_files(temp_dir, source_blend, script_path)
        try:
            _BACKGROUND_JOBS.remove(process)
        except ValueError:
            pass


def _start_background_job(payload, task_name, temp_dir="", source_blend=""):
    if not temp_dir:
        temp_dir = tempfile.mkdtemp(prefix="blender_asset_task_")
    script_path = os.path.join(temp_dir, "asset_background_task.py")
    try:
        _create_background_script(script_path)
        command = [
            bpy.app.binary_path,
            "--background",
            "--python",
            script_path,
            "--",
            json.dumps(payload, ensure_ascii=False),
        ]

        popen_kwargs = {
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "text": True,
            "encoding": "utf-8",
            "errors": "replace",
        }

        if os.name == "nt":
            popen_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

        process = subprocess.Popen(command, **popen_kwargs)
        _BACKGROUND_JOBS.append(process)
        worker = threading.Thread(
            target=_wait_for_background_job,
            args=(process, temp_dir, source_blend, script_path, task_name),
            daemon=True,
        )

        worker.start()
        return True
    except Exception as exc:
        print(f"错误：启动后台{task_name}失败：{exc}")
        _cleanup_temp_files(temp_dir, source_blend, script_path)
        return False


def _read_asset_catalogs(library_root):
    catalogs = []
    if not library_root:
        return catalogs

    catalog_file = _get_catalog_file_path(library_root)
    if not os.path.isfile(catalog_file):
        return catalogs

    try:
        with open(catalog_file, "r", encoding="utf-8") as file:
            lines = file.readlines()
    except Exception as exc:
        print(f"错误：无法读取 Catalog 文件：{exc}")
        return catalogs

    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line.startswith("#"):
            continue
        if line.startswith("VERSION"):
            continue
        parts = line.split(":", 2)
        if len(parts) != 3:
            continue

        catalog_id = parts[0].strip()
        catalog_path = parts[1].strip()
        catalog_name = parts[2].strip()
        if not catalog_id or not catalog_path:
            continue
        catalogs.append({"id": catalog_id, "path": catalog_path, "name": catalog_name})

    catalogs.sort(key=lambda item: item["path"].lower())
    return catalogs


def _get_blend_files(library_root, max_depth=3):
    blend_files = []
    if not library_root or not os.path.isdir(library_root):
        return blend_files

    library_root = os.path.normpath(library_root)
    for current_dir, dir_names, file_names in os.walk(library_root):
        relative_dir = os.path.relpath(current_dir, library_root)

        depth = (0 if relative_dir == "." else len(relative_dir.split(os.sep)))

        if depth >= max_depth:
            dir_names[:] = []

        for file_name in file_names:
            if not file_name.lower().endswith(".blend"):
                continue
            full_path = os.path.join(current_dir, file_name)
            relative_path = os.path.relpath(full_path, library_root)
            blend_files.append(relative_path.replace("\\", "/"))

    blend_files.sort(key=lambda item: item.lower())
    return blend_files


def _update_asset_library(self, context):
    self.target_blend = "NONE"
    self.catalog_id = "UNASSIGNED"


def _get_asset_library_enum_items(self, context):
    global _LIBRARY_ENUM_CACHE
    _LIBRARY_ENUM_CACHE = [("NONE", "请选择资产库", "请选择 Blender 偏好设置中注册的本地资产库", "ASSET_MANAGER", 0)]

    for index, library in enumerate(_get_asset_library_records(context), start=1):
        identifier = f"LIB::{library['name']}"
        _LIBRARY_ENUM_CACHE.append((identifier, library["name"], library["path"], "ASSET_MANAGER", index))
    return _LIBRARY_ENUM_CACHE


def _get_blend_enum_items(self, context):
    global _BLEND_ENUM_CACHE
    _BLEND_ENUM_CACHE = [("NONE", "请选择目标 Blend 文件", "请选择目标资产库中的 Blend 文件", "FILE_BLEND", 0)]
    if context is None:
        return _BLEND_ENUM_CACHE
    library_root = _get_selected_library_root(self.asset_library_name, context)
    if not library_root:
        return _BLEND_ENUM_CACHE

    blend_files = _get_blend_files(library_root, max_depth=3)
    for index, relative_path in enumerate(blend_files, start=1):
        full_path = os.path.join(library_root, relative_path.replace("/", os.sep))
        _BLEND_ENUM_CACHE.append((relative_path, relative_path, full_path, "FILE_BLEND", index))
    return _BLEND_ENUM_CACHE


def _get_catalog_enum_items(self, context):
    global _CATALOG_ENUM_CACHE
    _CATALOG_ENUM_CACHE = [("UNASSIGNED", "未分配", "将资产放入未分配目录", "NONE", 0)]
    if context is None:
        return _CATALOG_ENUM_CACHE
    library_root = _get_selected_library_root(self.asset_library_name, context)
    if not library_root:
        return _CATALOG_ENUM_CACHE

    catalogs = _read_asset_catalogs(library_root)
    for index, catalog in enumerate(catalogs, start=1):
        _CATALOG_ENUM_CACHE.append((catalog["id"], catalog["path"], f"显示名称：{catalog['name']}\nUUID：{catalog['id']}", "FILE_FOLDER", index))
    return _CATALOG_ENUM_CACHE


class BetterExperie_OT_AssetMove(bpy.types.Operator):
    bl_idname = "better_experie.asset_move"
    bl_label = "移动选中资产"
    bl_description = "移动或复制选中资产到目标 Blend 文件和目标目录"
    bl_options = {"REGISTER"}

    transfer_mode: bpy.props.EnumProperty(
        name="转移方式",
        items=[
            ('MOVE', "移动到目标位置", "移动：目标文件追加后删除源资产"),
            ('COPY', "复制到目标位置", "复制：目标文件追加后保留源资产"),
        ],
        default='MOVE',
    )
    asset_library_name: bpy.props.EnumProperty(
        name="目标资产库",
        description="选择 Blender 偏好设置中已注册的本地资产库",
        items=_get_asset_library_enum_items,
        update=_update_asset_library,
    )
    target_blend: bpy.props.EnumProperty(
        name="目标 Blend",
        description="从目标资产库中选择 Blend 文件，最多扫描三级目录",
        items=_get_blend_enum_items,
    )
    catalog_id: bpy.props.EnumProperty(
        name="目标目录",
        description="从 blender_assets.cats.txt 中读取资产目录",
        items=_get_catalog_enum_items,
    )
    allow_duplicate: bpy.props.BoolProperty(
        name="允许同名追加",
        description="关闭时跳过目标文件同名资产；开启时使用 .001 等后缀",
        default=False,
    )

    @classmethod
    def poll(cls, context):
        return (
            context.area is not None
            and context.area.ui_type == "ASSETS"
            and len(getattr(context, "selected_assets", []) or []) > 0)

    def draw(self, context):
        layout = self.layout
        records = _get_selected_asset_records(context)
        library_root = _get_selected_library_root(self.asset_library_name, context)
        layout.label(text=f"当前选中资产：{len(records)}", icon="ASSET_MANAGER")
        layout.prop(self, "transfer_mode", text="转移方式")
        layout.prop(self, "asset_library_name", text="目标资产库")
        layout.prop(self, "target_blend", text="目标 Blend")
        layout.prop(self, "catalog_id", text="目标目录")
        layout.prop(self, "allow_duplicate", text="允许同名追加")

        if library_root:
            blend_count = len(_get_blend_files(library_root, max_depth=3))
            layout.label(text=f"检测到 {blend_count} 个 Blend 文件。", icon="INFO")
            catalog_file = _get_catalog_file_path(library_root)
            if not os.path.isfile(catalog_file):
                row = layout.row()
                row.alert = True
                row.label(text="未找到 blender_assets.cats.txt", icon="ERROR")

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=520)

    def get_target_blend_path(self, context):
        library_root = _get_selected_library_root(self.asset_library_name, context)
        if not library_root:
            return ""
        relative_path = self.target_blend
        if not relative_path or relative_path == "NONE":
            return ""
        target_path = os.path.normpath(os.path.join(library_root, relative_path.replace("/", os.sep)))
        try:
            root_common_path = os.path.commonpath([library_root])
            target_common_path = os.path.commonpath([library_root, target_path])
            if os.path.normcase(root_common_path) != os.path.normcase(target_common_path):
                return ""
        except Exception:
            return ""
        return target_path

    def execute(self, context):
        records = _get_selected_asset_records(context)
        target_blend = self.get_target_blend_path(context)
        if not records:
            print("错误：没有可移动的有效资产。")
            return {"CANCELLED"}
        if not target_blend:
            print("错误：请先选择目标资产库和目标 Blend 文件。")
            return {"CANCELLED"}
        if not os.path.isfile(target_blend):
            print(f"错误：目标 Blend 文件不存在：{target_blend}")
            return {"CANCELLED"}

        temp_dir = tempfile.mkdtemp(prefix="blender_asset_move_")
        source_blend = os.path.join(temp_dir, "LocalSelectedAssets.blend")
        local_assets = []
        move_records = []
        current_file = (os.path.normpath(bpy.data.filepath) if bpy.data.filepath else "")
        for record in records:
            if record["local"]:
                local_assets.append(record["id_data"])
            else:
                move_records.append({
                    "name": record["name"],
                    "collection": record["collection"],
                    "source": record["source"],
                    "delete_source": self.transfer_mode == 'MOVE',
                })

        # 当前文件就是目标文件时，仅修改目标 Catalog。
        if local_assets and current_file:
            if os.path.normcase(current_file) == os.path.normcase(target_blend):
                for record in records:
                    if record["local"]:
                        move_records.append({
                            "name": record["name"],
                            "collection": record["collection"],
                            "source": target_blend,
                            "delete_source": False,
                        })

                local_assets = []

        # 当前文件资产移动到其他文件时，导出临时 Blend。
        if local_assets:
            try:
                bpy.data.libraries.write(
                    filepath=source_blend,
                    datablocks=set(local_assets),
                    path_remap="RELATIVE_ALL",
                    fake_user=True,
                    compress=True,
                )

                for record in records:
                    if record["local"]:
                        move_records.append({
                            "name": record["name"],
                            "collection": record["collection"],
                            "source": source_blend,
                            "delete_source": False,
                        })

            except Exception as exc:
                print(f"错误：无法导出当前文件资产：{exc}")
                _cleanup_temp_files(temp_dir, source_blend, "")
                return {"CANCELLED"}

        if not move_records:
            print("错误：没有可移动资产。")
            _cleanup_temp_files(temp_dir, source_blend, "")
            return {"CANCELLED"}

        # 获取目标 Catalog UUID
        if self.catalog_id == "UNASSIGNED":
            target_catalog_id = _UNASSIGNED_CATALOG_ID
        else:
            target_catalog_id = self.catalog_id

        payload = {
            "operation": "move",
            "target_blend": target_blend,
            "catalog_id": target_catalog_id,
            "allow_duplicate": self.allow_duplicate,
            "records": move_records,
        }

        if not _start_background_job(payload, "移动资产", temp_dir, source_blend):
            return {"CANCELLED"}

        self.report({"INFO"}, "已开始后台移动资产，请查看系统控制台结果。")

        print("========== 已开始后台移动资产 ==========")
        print(f"目标文件：{target_blend}")
        print(f"资产数量：{len(move_records)}")
        print("前台 Blender 不会被阻塞。")
        print("======================================")

        return {"FINISHED"}


class BetterExperie_OT_AssetDelete(bpy.types.Operator):
    bl_idname = "better_experie.asset_delete"
    bl_label = "删除选中资产"
    bl_description = "删除其他 Blend 文件中选中的资产；对当前文件资产取消资产标记"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        if context.area is None:
            return False
        if context.area.ui_type != "ASSETS":
            return False
        return bool(_get_selected_asset_records(context))

    def execute(self, context):
        records = _get_selected_asset_records(context)
        local_records = [r for r in records if r["local"]]
        external_records = [r for r in records if not r["local"]]

        # 当前文件资产：取消资产标记（不删除数据块）
        cleared = 0
        for record in local_records:
            id_data = record["id_data"]
            try:
                if id_data.asset_data is not None:
                    id_data.asset_clear()
                    cleared += 1
            except Exception as exc:
                print(f"取消资产标记失败：{record['name']} / {exc}")

        # 外部资产：后台删除
        delete_records = [
            {"name": r["name"], "collection": r["collection"], "source": r["source"]}
            for r in external_records
        ]

        if delete_records:
            payload = {"operation": "delete", "records": delete_records}
            if not _start_background_job(payload, "删除资产"):
                self.report({"ERROR"}, "启动后台删除资产失败")
                return {"CANCELLED"}

            if cleared:
                self.report({"INFO"}, f"已取消 {cleared} 个本地资产标记，并已开始后台删除 {len(delete_records)} 个外部资产，请查看系统控制台结果。")
            else:
                self.report({"INFO"}, "已开始后台删除资产，请查看系统控制台结果。")
            print("========== 已开始后台删除资产 ==========")
            print(f"资产数量：{len(delete_records)}")
            print("======================================")
            return {"FINISHED"}

        if cleared:
            self.report({"INFO"}, f"已取消 {cleared} 个当前文件资产的资产标记")
            return {"FINISHED"}

        self.report({"INFO"}, "没有可删除的资产")
        return {"CANCELLED"}

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)


class BetterExperie_OT_AssetRename(bpy.types.Operator):
    bl_idname = "better_experie.asset_rename"
    bl_label = "重命名选中资产"
    bl_description = "重命名选中的单个资产（当前文件直接改名，外部文件后台改名）"
    bl_options = {"REGISTER"}

    asset_new_name: bpy.props.StringProperty(name="新名称", description="重命名资产时使用的新名称", default="")

    @classmethod
    def poll(cls, context):
        if context.area is None:
            return False
        if context.area.ui_type != "ASSETS":
            return False
        records = _get_selected_asset_records(context)
        return len(records) == 1

    def draw(self, context):
        layout = self.layout
        records = _get_selected_asset_records(context)
        if records:
            layout.label(text=f"当前名称：{records[0]['name']}", icon="ASSET_MANAGER")
        layout.prop(self, "asset_new_name", text="新名称")

    def invoke(self, context, event):
        records = _get_selected_asset_records(context)

        if len(records) != 1:
            print("错误：重命名时只能选择一个资产。")
            return {"CANCELLED"}

        # 默认填入当前资产名称，方便直接修改。
        self.asset_new_name = records[0]["name"]
        return context.window_manager.invoke_props_dialog(self, width=420)

    def execute(self, context):
        records = _get_selected_asset_records(context)
        new_name = self.asset_new_name.strip()
        if len(records) != 1:
            print("错误：重命名时只能选择一个资产。")
            return {"CANCELLED"}

        if not new_name:
            print("错误：请输入新的资产名称。")
            return {"CANCELLED"}

        record = records[0]
        if new_name == record["name"]:
            print("错误：新名称与原名称相同。")
            return {"CANCELLED"}

        # 当前文件资产：直接重命名数据块
        if record["local"]:
            id_data = record["id_data"]
            try:
                id_data.name = new_name
            except Exception as exc:
                self.report({"ERROR"}, f"重命名失败：{exc}")
                return {"CANCELLED"}
            self.report({"INFO"}, f"已重命名：{record['name']} -> {new_name}")
            return {"FINISHED"}

        # 外部资产：后台重命名
        payload = {
            "operation": "rename",
            "source": record["source"],
            "collection": record["collection"],
            "old_name": record["name"],
            "new_name": new_name,
        }
        if not _start_background_job(payload, "重命名资产"):
            return {"CANCELLED"}

        self.report({"INFO"}, "已开始后台重命名资产，请查看系统控制台结果。")
        print("========== 已开始后台重命名资产 ==========")
        print(f"原名称：{record['name']}")
        print(f"新名称：{new_name}")
        print("========================================")

        return {"FINISHED"}


class BetterExperie_OT_InvokeAssetMove(bpy.types.Operator):
    bl_idname = "better_experie.invoke_asset_move"
    bl_label = "移动选中资产（代理）"
    bl_description = "代理入口：通过 INVOKE_DEFAULT 调起移动选中资产面板"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        return BetterExperie_OT_AssetMove.poll(context)

    def execute(self, context):
        try:
            bpy.ops.better_experie.asset_move('INVOKE_DEFAULT')
        except Exception as exc:
            self.report({'ERROR'}, f"调起移动资产面板失败：{exc}")
            return {'CANCELLED'}
        return {'FINISHED'}


class BetterExperie_OT_InvokeAssetRename(bpy.types.Operator):
    bl_idname = "better_experie.invoke_asset_rename"
    bl_label = "重命名选中资产（代理）"
    bl_description = "代理入口：通过 INVOKE_DEFAULT 调起重命名资产面板"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        return BetterExperie_OT_AssetRename.poll(context)

    def execute(self, context):
        try:
            bpy.ops.better_experie.asset_rename('INVOKE_DEFAULT')
        except Exception as exc:
            self.report({'ERROR'}, f"调起重命名资产面板失败：{exc}")
            return {'CANCELLED'}
        return {'FINISHED'}


class BetterExperie_OT_InvokeAssetDelete(bpy.types.Operator):
    bl_idname = "better_experie.invoke_asset_delete"
    bl_label = "删除选中资产（代理）"
    bl_description = "代理入口：通过 INVOKE_DEFAULT 调起删除资产确认"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        return BetterExperie_OT_AssetDelete.poll(context)

    def execute(self, context):
        try:
            bpy.ops.better_experie.asset_delete('INVOKE_DEFAULT')
        except Exception as exc:
            self.report({'ERROR'}, f"调起删除资产确认失败：{exc}")
            return {'CANCELLED'}
        return {'FINISHED'}


def _assetbrowser_context_menu_draw(self, context):
    layout = self.layout
    layout.separator()
    layout.operator("better_experie.invoke_asset_move", text="移动选中资产", icon="DECORATE_DRIVER")
    layout.operator("better_experie.invoke_asset_rename", text="重命名选中资产", icon="GREASEPENCIL")
    layout.operator("better_experie.invoke_asset_delete", text="删除选中资产", icon="TRASH")


classes = (
    BetterExperie_OT_AssetMove,
    BetterExperie_OT_AssetDelete,
    BetterExperie_OT_AssetRename,
    BetterExperie_OT_InvokeAssetMove,
    BetterExperie_OT_InvokeAssetRename,
    BetterExperie_OT_InvokeAssetDelete,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    try:
        bpy.types.ASSETBROWSER_MT_context_menu.append(_assetbrowser_context_menu_draw)
    except (ValueError, AttributeError):
        pass


def unregister():
    try:
        bpy.types.ASSETBROWSER_MT_context_menu.remove(_assetbrowser_context_menu_draw)
    except (ValueError, AttributeError):
        pass
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
