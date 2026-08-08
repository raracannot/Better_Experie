# Better_Experie 开发规范

---

## 文件命名

```
{domain}_{subdomain}_{action_description}.py
```

| 部分 | 说明 | 示例 |
|---|---|---|
| `domain` | 编辑器域 | `view3d_` `nodetree_` `filebrowser_` `texteditor_` `outliner_` |
| `subdomain` | 作用对象 | `mesh_` `obj_` `compositor_` `shader_` `color_ramp_` `color_curve_` |
| `action` | 功能描述 | `add_vertex_group` `filter_batch_selector` `screen_snapshot` |

- 文件名**只允许英文 ASCII**，禁止中文、空格、括号
- 禁止使用 `[test]` `[abandon]` 等标记前缀
- 禁止将独立 `bl_info` 块留在子模块中（合并残留）

```
view3d_mesh_filter_batch_selector.py
nodetree_color_ramp_tools.py
nodetree_compositor_bake_node.py
texteditor_editing_tool.py
```

---

## 类命名

| 类型 | 前缀 | 示例 |
|---|---|---|
| Operator | `BetterExperie_OT_` + PascalCase | `BetterExperie_OT_MeshAddVertexGroup` |
| Panel | `BETTER_EXPERIE_PT_` + snake_case | `BETTER_EXPERIE_PT_screen_snapshot` |
| Menu | `BETTER_EXPERIE_MT_` + snake_case | `BETTER_EXPERIE_MT_color_ramp_tools` |
| PropertyGroup | `BetterExperie_` + PascalCase | `BetterExperie_ScreenSnapshotSettings` |
| Preferences | `BetterExperie_Preferences` | （固定名称，仅一个） |

### bl_idname 对应规则

| 类型 | bl_idname 格式 |
|---|---|
| Operator | `"better_experie.{snake_case}"` |
| Panel | `"BETTER_EXPERIE_PT_{snake_case}"` |
| Menu | `"BETTER_EXPERIE_MT_{snake_case}"` |

```python
# Operator
class BetterExperie_OT_ColorRampFlipPositions(bpy.types.Operator):
    bl_idname = "better_experie.color_ramp_flip_positions"

# Panel
class BETTER_EXPERIE_PT_screen_snapshot(bpy.types.Panel):
    bl_idname = "BETTER_EXPERIE_PT_screen_snapshot"

# Menu
class BETTER_EXPERIE_MT_color_ramp_tools(bpy.types.Menu):
    bl_idname = "BETTER_EXPERIE_MT_color_ramp_tools"

# PropertyGroup（无需 bl_idname，只用于 bpy.props.PointerProperty 绑定）
class BetterExperie_ScreenSnapshotSettings(bpy.types.PropertyGroup):
    ...
```

---

## 属性命名

### Scene 属性（挂载到 `bpy.types.Scene`）

```python
bpy.types.Scene.better_experie_{snake_case} = bpy.props.PointerProperty(type=...)
```

### Preferences 属性

```python
show_{feature_name}: bpy.props.BoolProperty(
    name="中文名", description="中文说明", default=True)
```

---

## 每个 Operator 必须包含

```python
class BetterExperie_OT_Xxx(bpy.types.Operator):
    bl_idname = "better_experie.xxx"
    bl_label = "中文标签"
    bl_description = "中文功能说明"   # ← 必须显式声明，禁止用 docstring 代替
    bl_options = {'REGISTER', 'UNDO'}  # ← 不可省略
```

- **禁止**使用类 docstring 代替 `bl_description`
- 工具/调试类 operator 如不涉及数据修改，可省略 `bl_options`
- 建议实现 `@classmethod poll(cls, context)` 做上下文守卫

---

## 文件结构模板

```python
# 功能简述

import bpy

class BetterExperie_OT_Xxx(bpy.types.Operator):
    bl_idname = "better_experie.xxx"
    bl_label = "标签"
    bl_description = "描述"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        ...
    def execute(self, context):
        ...
        return {'FINISHED'}

classes = (
    BetterExperie_OT_Xxx,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
```

- 禁止出现 `if __name__ == "__main__": register()`
- 禁止出现独立 `bl_info = {...}` 块

---

## Preferences 访问

**在子包（`ops/view3d/` `ops/nodetree/` 等）中，`__package__` 不再是插件根名，禁止直接用它查找 preferences。**

统一使用 `utils/__init__.py` 提供的 `get_pref()`：

```python
from ...utils import get_pref

prefs = get_pref()
```

`get_pref()` 内部通过 `from .. import __package__ as base_package` 获取根包名，自动适配任意嵌套深度。

---

## UI 开关模式

在 `addon_prefs.py` 中添加布尔属性，然后在 Panel/Menu/Header 中检查：

```python
# addon_prefs.py
show_screen_snapshot: bpy.props.BoolProperty(
    name="屏显快照", description="...", default=True)

# 在子模块中
from ...utils import get_pref

# Panel poll
@classmethod
def poll(cls, context):
    prefs = get_pref()
    return getattr(prefs, "show_screen_snapshot", True)

# Header draw
def header_draw(self, context):
    prefs = get_pref()
    if not getattr(prefs, "show_screen_snapshot", True):
        return
    self.layout.operator("better_experie.xxx")
```

> 说明：`getattr(prefs, "xxx", True)` 兜底 `True`，防止旧版 prefs 无此属性时崩溃。

---

## 菜单架构

插件采用双层菜单布局：

```
menu/          ← 定义"总入口"子菜单，注入到 Blender 原生右键菜单
                  运行时无条件显示，聚合分散在各处的功能入口
                  一个 Blender 原生菜单位置只应被一个 draw 函数注入

ops/{module}/  ← Operator 自带上下文子菜单（含 poll 检查）
                  仅当条件满足时才出现（如选中特定节点类型）
                  注入到标题栏菜单（NODE_MT_editor_menus），不直接注入右键菜单
```

**原则**：右键菜单（`*_MT_context_menu`）只由 `menu/` 层注入一个总入口，避免出现多个分散条目。`ops/` 内的上下文子菜单通过 `layout.menu()` 嵌套在总入口中，同时单独注册到标题栏。

### Menu 类命名

```python
class NODETREE_MT_color_ramp_tools(bpy.types.Menu):
    bl_label = "颜色渐变工具"
    bl_idname = "NODETREE_MT_color_ramp_tools"

    @classmethod
    def poll(cls, context):   # 上下文子菜单建议实现 poll
        return bool(get_selected_ramp_nodes(context))

    def draw(self, context):
        ...
```

- Menu `bl_idname` 统一用 `{DOMAIN}_MT_{description}` 格式
- 上下文相关的 Menu 实现 `poll()`，嵌套在总菜单中时会自动按需显示/隐藏

### 总菜单嵌套上下文子菜单

```python
# menu/nodetree_mt.py — 总入口
class NODETREE_MT_rara_submenu(bpy.types.Menu):
    def draw(self, context):
        layout = self.layout
        # 上下文子菜单（有 poll 自动控制显隐）
        layout.menu("NODETREE_MT_color_ramp_tools")
        layout.menu("NODETREE_MT_curve_submenu")
        layout.separator()
        # 通用功能...
```

### 注册

```python
# 总入口（menu/ 层）— 注入右键菜单
def draw_nodetree_submenu(self, context):
    self.layout.separator()
    self.layout.menu("NODETREE_MT_rara_submenu")

def register():
    bpy.types.NODE_MT_context_menu.append(draw_nodetree_submenu)

# 上下文子菜单（ops/ 层）— 注入标题栏
def color_ramp_context_draw(self, context):
    if not get_selected_ramp_nodes(context):
        return
    self.layout.menu("NODETREE_MT_color_ramp_tools")

def register():
    bpy.types.NODE_MT_editor_menus.append(color_ramp_context_draw)
```

- 右键菜单：只由 `menu/` 注入 **一处** 总入口
- 标题栏菜单：由各自的 `ops/` 模块注入，带 poll 前置检查

---


## 文件清理清单

新文件 / 从外部合并文件时，必须检查并移除：

- [ ] 独立 `bl_info = {...}` 块
- [ ] `if __name__ == "__main__":` 块
- [ ] 非 `BetterExperie_` 前缀的类名
- [ ] 非 `better_experie.` 前缀的 `bl_idname`
- [ ] 用 docstring 代替 `bl_description` 的写法
- [ ] `__package__` 直接用于 preferences 查找
- [ ] 插件目录内保存临时文件（应用 `tempfile.gettempdir()`）
- [ ] 重复定义的函数

---

## 目录注册模板

每个子包 `__init__.py`：

```python
import bpy
import importlib

MODULE_NAMES = [
    "view3d_obj_apply_all_modifiers",
    "view3d_screen_snapshot",
]

ops_module_list = [importlib.import_module(f".{name}", __package__) for name in MODULE_NAMES]

def register():
    for ops in ops_module_list:
        if hasattr(ops, "register"):
            ops.register()

def unregister():
    for ops in reversed(ops_module_list):
        if hasattr(ops, "unregister"):
            ops.unregister()

def update():
    unregister()
    for ops in ops_module_list:
        importlib.reload(ops)
    register()
```

---

## 临时文件

内部缓存/快照等文件使用系统临时目录，不污染插件目录：

```python
import tempfile
import os

def get_temp_path(filename="better_experie_cache.png"):
    return os.path.join(tempfile.gettempdir(), filename)
```

---

## 快捷键 + 菜单双入口 — invoke/execute fallback

当 Operator 同时注册了快捷键（含 `invoke` 利用鼠标坐标）和菜单按钮入口时，菜单触发不会传入有效的 3D 视口坐标，invoke 中的 `event.mouse_region_x/y` 不可信。

**规则**：invoke 只做"尽力尝试"设置参数，**永不返回 `CANCELLED`**，始终坠落 `execute`。execute 内部检查参数是否有效，无效时 fallback 到降级逻辑（如取当前选中的元素）。

```python
def invoke(self, context, event):
    obj = context.edit_object
    bm = bmesh.from_edit_mesh(obj.data)

    # 尽力从快捷键上下文获取参数
    active = bm.select_history.active
    if isinstance(active, bmesh.types.BMEdge):
        self.edge_a_index = active.index
        bpy.ops.view3d.select(
            'EXEC_DEFAULT', extend=True, deselect_all=False,
            location=(event.mouse_region_x, event.mouse_region_y))
        bm.select_history.validate()
        new_active = bm.select_history.active
        if isinstance(new_active, bmesh.types.BMEdge) and new_active.index != active.index:
            self.edge_b_index = new_active.index

    # 不返回 CANCELLED，始终坠落 execute 用 fallback
    return self.execute(context)

def execute(self, context):
    bm = bmesh.from_edit_mesh(obj.data)

    # fallback：菜单触发时参数未设置，从当前选中元素获取
    if self.edge_a_index == 0 and self.edge_b_index == 0:
        selected = [e for e in bm.edges if e.select]
        if len(selected) >= 2:
            self.edge_a_index = selected[0].index
            self.edge_b_index = selected[1].index
        else:
            self.report({'WARNING'}, "请使用 Ctrl+Shift+右键 或先选中两条边")
            return {'CANCELLED'}

    # ... 正常执行逻辑 ...
```

**要点**：
- invoke 只尝试设置参数，失败不拦截
- execute 在参数缺省时走 fallback 路径
- 不要在 invoke 中 `report({'WARNING'})` + `return {'CANCELLED'}`，这会阻断菜单入口

---

## 错误报告

```python
self.report({'WARNING'}, "...")   # 用户操作不当（如未选中节点）
self.report({'ERROR'}, "...")     # 操作失败（如文件写入失败）
self.report({'INFO'}, "...")      # 操作成功提示

return {'CANCELLED'}              # 与 WARNING/ERROR 搭配
return {'FINISHED'}               # 与 INFO 搭配
```

- 不要用 `{'INFO'}` 搭配 `{'CANCELLED'}`
- 不要用 `{'ERROR'}` 搭配 `{'FINISHED'}`

---

# 强制条例

以下规则标有【必须】【务必】【一定】【强制】，模块在修改和新增时**无论如何均不得违反**。

---

## 模态与绘制安全

所有模态类（Modal Operator）和绘制回调（GPU Draw Handler / Gizmo）的代码，**【必须】使用 `try/except Exception` 包裹核心逻辑**，并准备好安全退出（cleanup）路径。

模态执行中或绘制过程中的任何未捕获异常，**都【必须】触发安全退出**，确保资源（draw handler、timer、BMesh 备份等）被完整回收，绝不允许因异常导致 Blender 残留僵尸 handler 或锁定的编辑模式。

### 模态类模板

```python
class BetterExperie_OT_Xxx(bpy.types.Operator):
    bl_idname = "better_experie.xxx"
    bl_label = "标签"
    bl_description = "描述"
    bl_options = {'REGISTER', 'UNDO'}

    _handler = None
    _timer = None

    def invoke(self, context, event):
        try:
            self._handler = bpy.types.SpaceView3D.draw_handler_add(
                self._draw_callback, (self, context), 'WINDOW', 'POST_VIEW')
            self._timer = context.window_manager.event_timer_add(0.05, window=context.window)
            context.window_manager.modal_handler_add(self)
            return {'RUNNING_MODAL'}
        except Exception:
            self._cleanup()
            return {'CANCELLED'}

    def modal(self, context, event):
        try:
            if event.type == 'ESC' or event.type == 'RIGHTMOUSE':
                self._cleanup()
                return {'CANCELLED'}

            # 核心事件处理...
            context.area.tag_redraw()
            return {'RUNNING_MODAL'}
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.report({'ERROR'}, str(e))
            self._cleanup()
            return {'CANCELLED'}

    @staticmethod
    def _draw_callback(self, context):
        try:
            # 核心绘制逻辑...
            pass
        except ReferenceError:
            pass  # 对象已被删除，安全跳过
        except Exception:
            import traceback
            traceback.print_exc()
        finally:
            gpu.state.blend_set('NONE')
            gpu.state.depth_test_set('LESS_EQUAL')
            gpu.state.line_width_set(1.0)

    def _cleanup(self):
        """安全退出：移除 draw handler、timer 等所有资源"""
        if self._handler:
            bpy.types.SpaceView3D.draw_handler_remove(self._handler, 'WINDOW')
            self._handler = None
        if self._timer and bpy.context.window_manager:
            bpy.context.window_manager.event_timer_remove(self._timer)
            self._timer = None
```

### 绘制回调模板（非模态）

```python
def draw_callback():
    try:
        # 核心绘制逻辑
        shader.bind()
        batch.draw(shader)
    except ReferenceError:
        pass  # 目标对象被删除
    except Exception:
        import traceback
        traceback.print_exc()
    finally:
        # 【必须】恢复 GPU 默认状态
        gpu.state.blend_set('NONE')
        gpu.state.depth_test_set('LESS_EQUAL')
        gpu.state.line_width_set(1.0)
        gpu.state.point_size_set(1.0)
```

### 关键规则

- **`finally` 中恢复 GPU 状态**（blend、depth_test、line_width、point_size），不可省略
- **捕获 `ReferenceError`**：绘制回调运行时，目标对象可能已被垃圾回收
- **`_cleanup()` 中的每个资源移除操作自身也应安全**：用 `if self._handler:` 和 `try/except` 防御
- **`invoke` 中任何 setup 失败也【必须】调用 `_cleanup()`**，避免部分资源泄漏

现有参考：
- `ops/view3d/view3d_mesh_modal_weld.py:26-63` — invoke 中 try/except 包裹初始化
- `ops/view3d/view3d_mesh_modal_weld.py:197-201` — modal 中 try/except 包裹事件处理，附带 `traceback.format_exc()` + `self.report()`
- `ops/view3d/view3d_empty_wireframe.py:156-161` — draw 回调中捕获 `ReferenceError`
- `ops/view3d/view3d_empty_wireframe.py:258-263` — draw_prepare 中捕获 `ReferenceError`
- `ops/view3d/view3d_mesh_topology_hud.py:651-654` — finally 中恢复 GPU 状态

---

# 建议条例

以下规则标有【应当】【酌情】【按需】【建议】，模块在修改和新增时**优先遵循**。如果存在合理性理由（如特定场景下规则不适用），允许违反，但应在代码注释或 commit message 中说明理由。

---

## 网格不可见面的忽略

所有的网格操作（选择循环线、拓扑遍历、焊接、法线分析等），**【应当】自动忽略不可见的网格元素**。参考 Blender 原生选择循环线的行为——遇到隐藏面（hidden faces）时会自动断开。

### 实现指引

- 使用 `bm.verts[i].hide` / `bm.edges[i].hide` / `bm.faces[i].hide` 判断元素是否隐藏
- 在遍历/扩散算法中，将隐藏元素视为屏障，不跨越隐藏边或隐藏面
- 对于网格生成/编辑类操作，建议跳过隐藏区域，避免产生不可预见的网格数据
- 如果操作结果因隐藏面而受限，可用 `self.report({'INFO'}, ...)` 提示用户

```python
# 示例：遍历边循环时跳过隐藏边
for edge in bm.edges:
    if edge.hide:
        continue  # 视作屏障，断开循环
    # 正常处理...
```

### 注意

- `bm.xxx.hide` 是**每个元素级别的隐藏**（H key），与编辑模式下的全局隐藏不同
- `mesh.vertices[i].hide` 绑定到 Mesh 层级的顶点隐藏属性，与 BMesh 对应

---

## 选取类操作的修饰符支持

所有的选取类操作（元素选择、框选、点选、路径选择等），**【应当】保底支持 Shift + Ctrl 修饰符**，这是 Blender 的基础交互设计语言：

| 修饰符 | 行为 | 语义 |
|---|---|---|
| 无修饰符（默认） | 替换选择 | SET |
| Shift | 追加选择（加选） | ADD / EXTEND |
| Ctrl | 移除选择（减选） | REMOVE / SUBTRACT |

### 实现指引

即使功能内部逻辑复杂（如循环边选择、最短路径选择），也应在顶层入口支持这套修饰符语义：

```python
def invoke(self, context, event):
    self.selection_mode = 'SET'
    if event.shift and not event.ctrl:
        self.selection_mode = 'ADD'
    elif event.ctrl and not event.shift:
        self.selection_mode = 'REMOVE'
    return self.execute(context)
```

在 `execute` 内，根据 `self.selection_mode` 决定：
- `SET`：先清空同类元素选择，再设置新选择
- `ADD`：保留现有选择，追加新选中的元素
- `REMOVE`：从现有选择中移除命中的元素

```python
def execute(self, context):
    bm = bmesh.from_edit_mesh(obj.data)

    if self.selection_mode == 'SET':
        for e in bm.edges:
            e.select = e in result_edges
    elif self.selection_mode == 'ADD':
        for e in result_edges:
            e.select = True
    elif self.selection_mode == 'REMOVE':
        for e in result_edges:
            e.select = False

    bm.select_flush_mode()
    bmesh.update_edit_mesh(obj.data)
    return {'FINISHED'}
```

### 扩展修饰符组合

如果功能的交互场景需要，可进一步支持：
- **Ctrl + Shift**：交集选择（仅保留同时匹配的）
- **Alt**：循环/环选择模式切换

但 Shift（加选）和 Ctrl（减选）是**最低要求**。

现有参考：
- `ops/view3d/view3d_mesh_filter_batch_selector.py:407-482` — SET / ADD / REMOVE 模式
- `ops/view3d/view3d_mesh_select_region_by_loop.py:169-183` — shift/ctrl 修饰符解析

---

## GPU 绘制的 X-Ray 深度检测自适应

三维空间中 GPU 绘制的元素（线段、面、点等），**【应当】依据视口的 X-Ray（透视显示 `show_xray`）状态，自动切换深度检测模式**：

| X-Ray 状态 | 深度检测 | 效果 |
|---|---|---|
| 开启（实体/线框 X-Ray） | `'NONE'` 或 `'ALWAYS'` | 绘制元素永远可见，穿透遮挡物 |
| 关闭（正常模式） | `'LESS_EQUAL'` | 绘制元素被遮挡物正确遮挡 |

### 实现模板

```python
import gpu

def draw(context):
    is_xray = False
    if context.space_data and hasattr(context.space_data.shading, 'show_xray'):
        is_xray = context.space_data.shading.show_xray

    try:
        if is_xray:
            gpu.state.depth_test_set('NONE')
        else:
            gpu.state.depth_test_set('LESS_EQUAL')

        shader.bind()
        batch.draw(shader)
    except Exception:
        import traceback
        traceback.print_exc()
    finally:
        gpu.state.depth_test_set('LESS_EQUAL')  # 恢复默认
```

### 关键规则

- **只影响 3D 空间的绘制**（`'POST_VIEW'`），2D 覆盖层（`'POST_PIXEL'`）不受影响
- **`finally` 中恢复 `'LESS_EQUAL'`**，避免影响后续其他绘制
- **检查 `hasattr(context.space_data.shading, 'show_xray')`**：部分上下文（如渲染视图）可能不存在该属性

现有参考：
- `ops/view3d/view3d_mesh_topology_hud.py:584-589` — X-ray 模式下使用 `'NONE'`
- `ops/view3d/view3d_mesh_vertex_group_stats.py:111-119` — 条件深度检测
- `ops/view3d/view3d_empty_wireframe.py:163-169` — 匹配 X-ray 状态切换深度检测

---

## 性能优化建议

所有功能项，如果存在显著的性能优化方案，**【应当】评估并向用户提出建议**，让用户确认是否采用，而非擅自引入重型依赖或复杂优化代码。

### 常用优化手段一览

| 优化手段 | 适用场景 | 注意事项 |
|---|---|---|
| NumPy 向量化（`np.bincount`、广播、`np.linalg`） | 批量顶点/边/面数据处理 | 需要 `numpy` 已安装（Blender 自带）；适合遍历数万元素以上的场景 |
| KDTree（`mathutils.kdtree.KDTree`） | 近邻搜索、顶点焊接、投影 | Blender 内置，无额外依赖；适合点云查询 O(n log n) |
| BVHTree（`mathutils.bvhtree.BVHTree`） | 射线检测、面碰撞 | Blender 内置；适合面级空间查询 |
| `foreach_get` / `foreach_set` | 批量属性读写 | 比逐元素访问快 10-100 倍；适合需要遍历所有元素的场景 |

### 决策流程

1. **识别瓶颈**：评估当前实现的复杂度，识别可能的性能瓶颈
2. **提出方案**：给出保守方案（逐个遍历，简单可靠）和优化方案（KDTree/NumPy 加速，性能显著提升）的对比
3. **让用户决策**：在代码评审或功能讨论中明确性能差异，由用户选择是否引入优化

### 代码中体现

当存在可优化路径时，建议在注释或文档中标注：

```python
# 方案 A（当前实现）：逐个遍历所有顶点，O(n²)，适合 n < 1000
# 方案 B（可选优化）：KDTree 近邻搜索，O(n log n)，n > 10000 时提升明显
#     需要确认用户是否愿意引入 KDTree 构建开销
```

### 额外规则

- 如果性能差异可达 10 倍以上，且优化方案无额外依赖（如 KDTree/BVHTree 是 Blender 内置的），**可直接采用优化方案**，无需向用户确认
- 禁止使用需要引入额外依赖的优化（如 `scipy`、`numba`）
- `foreach_get/set` 是纯性能提升且无副作用的 API，**可自由使用**，无需特别确认

### 注意事项

- KDTree/BVHTree 有构建成本，仅为少量元素构建可能得不偿失
- 优化代码的可读性通常低于简单遍历，需权衡维护成本

现有参考：
- `ops/view3d/view3d_mesh_weld_verts_to_edges.py:60-85` — KDTree 加速边中点近邻搜索
- `ops/view3d/view3d_mesh_modal_weld.py:65-74` — KDTree + BVHTree 联合使用
- `ops/view3d/view3d_mesh_topology_hud.py:343-388` — NumPy 向量化批量计算拓扑统计
- `ops/view3d/view3d_mesh_topology_hud.py:430-487` — NumPy 批量构建三角/四边形面绘制数据
- `ops/nodetree/nodetree_color_ramp_tools.py:157-158` — NumPy linspace/clip 加速颜色渐变

---

## 菜单注入归属

按钮注入（`bpy.types.XXX_MT_XXX.append/prepend(draw_func)`）**优先集中在 `menu/blender_mt_custom.py` 统一管理**。

**【允许】** ops 模块自行在 `register()` 中注入菜单的情形：

- **draw 函数重度依赖模块内部状态**（如 `hud_manager`、`_stats_cache`、线程/Popen 进程等），无法以合理代价内联或通过字符串字面量消除依赖
- **draw 函数体量极大**（超过 40 行），内联到 `blender_mt_custom.py` 会显著降低该文件的可读性

其余无特殊说明的情况下，**_MT_优先注入到 `blender_mt_custom.py`**，保持菜单注册的集中可视性。

> 示例：`filebrowser_jump_to_active_folder.py` 的 draw 依赖模块级缓存/线程状态，`topology_hud.py` 的 draw 依赖 `hud_manager` 单例，两者自行注入。

---

## 面板注入（PT / HT）

面板（`*_PT_*`）与标题栏（`*_HT_*`）注入**由各自 ops 模块自行在 `register()` 中管理**（不集中到 `blender_mt_custom.py`）。

**插件最低支持 Blender 4.5**，因此核心 startup 面板（`NODE_PT_overlay`、`DATA_PT_*`、`VIEW3D_PT_*`、`TOPBAR_HT_*`、`OUTLINER_HT_header`、`FILEBROWSER_PT_*` 等）在 4.5 中**恒存在**，可直接 `bpy.types.XXX.append(draw_func)`，无需存在性检查。

**【必须】** 对**引擎依赖**的面板（仅特定渲染引擎启用时才存在于 `bpy.types`），注入/注销时用 `getattr` 检查，并 try 包裹：

```python
PANEL_TYPES = [
    "CYCLES_RENDER_PT_passes_aov",        # Cycles 专用
    "VIEWLAYER_PT_layer_passes_aov",      # EEVEE 专用
]

def register():
    for panel_name in PANEL_TYPES:
        panel_cls = getattr(bpy.types, panel_name, None)
        if panel_cls:
            try:
                panel_cls.append(draw_func)
            except Exception:
                pass

def unregister():
    for panel_name in PANEL_TYPES:
        panel_cls = getattr(bpy.types, panel_name, None)
        if panel_cls:
            try:
                panel_cls.remove(draw_func)
            except Exception:
                pass
```

> 背景：`CYCLES_RENDER_PT_passes_aov` 定义在 Cycles 引擎 addon 中，未启用 Cycles 时不存在；`VIEWLAYER_PT_layer_passes_aov` 的 `COMPAT_ENGINES = {'BLENDER_EEVEE'}`，EEVEE 专用。两者分别对应不同引擎的 AOV 面板。

---

# 开发工作流

## 中文文件编码安全

插件源码含大量中文（标签、描述、注释）。**所有 `.py` 文件保持 UTF-8（无 BOM）编码**，修改时遵守以下规则：

### 修改规则

- **优先使用 Edit 工具**修改含中文的文件，避免编码损坏。
- **禁止**用 PowerShell `Get-Content` / `Set-Content` 往返修改中文文件——PowerShell 5.1 按 GBK 控制台代码页解码，易把中文替换成不可逆的 `U+FFFD` 损坏字符；且 `Set-Content -Encoding UTF8` 会写入 BOM。
- 若必须用命令行替换，用 Python 脚本：

```python
p = r"path/to/file.py"
s = open(p, encoding="utf-8").read()
s = s.replace("旧字符串", "新字符串")
open(p, "w", encoding="utf-8", newline="\n").write(s)
```

### 编码判断（避免误判）

- **控制台打印中文乱码（`��`）≠ 文件损坏**——可能是 GBK 控制台显示问题。
- 判断文件是否损坏，检查替换字符 `U+FFFD`：

```bash
python -c "s=open(p, encoding='utf-8-sig').read(); print('\ufffd' in s)"   # False=未损坏
```

- 验证中文完整性，用**包含判断**而非打印：

```bash
python -c "s=open(p, encoding='utf-8').read(); print('清理颜色' in s)"   # True=完整
```

- BOM 检测：`open(p, 'rb').read(3) == b'\xef\xbb\xbf'`（True 表示带 BOM，如为 UTF-8-sig 读取则忽略）。
