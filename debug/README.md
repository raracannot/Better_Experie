# debug/ — 插件自检用例

给**人**和**agent**用的快速回归：跨 Blender 版本验证"现有功能还活着"，不依赖手动点界面。

## 怎么跑

必须是 **GUI 模式**（插件的 `register()` 在 `-b` 后台模式下是空实现，后台跑等于没测）：

```powershell
& "R:\sandbox_blender\blender-5.1.0-windows-x64\blender.exe" `
  --python "R:\sandbox_blender\blender-5.1.0-windows-x64\portable\scripts\addons\Better_Experie\debug\run_tests.py"
```

有用参数（放在 `--` 后面）：

```powershell
... --python "<...>/debug/run_tests.py" -- --only smart_template,force_update --verbose
... --python "<...>/debug/run_tests.py" -- --list
```

## 输出怎么读

```
BET_START addon=Better_Experie version=5.1.0 background=False
[PASS] 操作符 better_experie.force_update
[FAIL] File Output 目录写回 :: /tmp\
BET_RESULT {"version": "5.1.0", "pass": 32, "fail": 0, ...}
BET_DONE pass=32 fail=0 用时 0.04s -> C:\Users\...\better_experie_debug_last.json
```

- 每个断言一行 `[PASS]/[FAIL]`
- **最后一行 `BET_RESULT {...}` 是给机器解析的**，agent 直接正则抓这一行即可
- 完整结果另存到系统临时目录 `better_experie_debug_last.json`

## 用例清单

当前 12 个用例文件、**82 条断言**，5 个版本（4.5 / 5.0 / 5.1 / 5.2 / 5.3）全绿。

| 文件 | 覆盖 |
| --- | --- |
| `case_core.py` | 关键操作符 / 面板 / 场景属性 / 偏好设置 / 强制更新模块内部状态 |
| `case_registry.py` | 全量清点：215 个操作符的 RNA、注册类数量、面板与菜单数量 |
| `case_poll.py` | 扫荡所有操作符的 `poll()`，只对"大面积抛异常"报警 |
| `case_rna_enums.py` | 操作符枚举项是否还有值、数值范围是否写反、偏好设置枚举 |
| `case_handlers.py` | `bpy.app.handlers` 上的回调是否还在、有没有重复注册 |
| `case_translation.py` | 中英词条映射、关键文案、空值、英文表残留中文 |
| `case_utils.py` | 所有 util 子模块可导入、版本比较函数行为 |
| `case_smart_template.py` | 模板预览、token 词表、File Output 写回、未知 token / 非法格式串报错 |
| `case_token_settings.py` | token 弹窗设置项、node_pointer 字符串存储、缺词条兜底 |
| `case_force_update.py` | 代理过滤、线路顺序、限流识别、无代理快速返回、版本/大小/线路文案 |
| `case_material_slots.py` | 优化加速清理空材质槽（olpha 报过的崩溃回归） |
| `case_operators.py` | 真跑三个安全操作符：清理材质、创建空物体组、游标到所选 |

## 加一个用例

在 `cases/` 下新建 `case_xxx.py`，实现：

```python
def run(context):
    # context["find_module"]("ops.other.other_force_update") 可以拿到插件子模块
    return [
        {"name": "断言名字", "ok": True, "detail": "失败时给的说明"},
    ]
```

约定：

- 造出来的数据块**命名以 `BET_` 开头**，跑完 runner 会自动清理
- 不要联网、不要写文件到插件目录（临时文件请用 `tempfile`）
- 用例之间不要有顺序依赖

## 跨版本矩阵

`run_matrix.ps1` 会把**当前插件目录**复制进每个沙箱再跑一遍：

```powershell
powershell -ExecutionPolicy Bypass -File "<...>/debug/run_matrix.ps1"
powershell -ExecutionPolicy Bypass -File "<...>/debug/run_matrix.ps1" -Versions "5.2.0","5.3"
```

- 默认扫 `R:\sandbox_blender\blender-*`，跳过 4.5 以下的沙箱
- 会**覆盖**沙箱里的同名插件目录（沙箱本来就是一次性的）
- 脚本只认 ASCII 文本，避免 Windows PowerShell 5.1 的编码坑

## 注意

- runner 跑完会**退出 Blender**（`quit_blender`），别在开着未保存工程的实例上跑
- 这些文件默认**不打包进发布 zip**（`blender_manifest.toml` 的 `paths_exclude_pattern` 里有 `debug/`）；要随包发布就把那条删掉
- 后台模式（`-b`）会直接报错退出，这是刻意的
