# Better_Experie

> 优化原生体验、扩展功能的 Blender 插件合集 —— 一切功能服务于对原生功能的【体验优化】及【功能延展】

## 📖 在线功能说明书

👉 **[点击查看完整功能说明书（Tooltips）](https://raracannot.github.io/Better_Experie/)**

> 该页面为交互式功能目录，悬停卡片可查看详细说明、菜单位置、快捷键与完整操作符 ID。

## ✨ 功能概览

| 模块 | 说明 |
| --- | --- |
| 📁 文件浏览器 | 资源管理器路径跳转、批量重命名、文件树生成 |
| 🎨 节点编辑器 | 渐变库、曲线工具、剪贴板图像导入、GPU 烘焙、AOV 扫描 |
| 🔷 3D 视图 | 非流形循环选取、孤岛扩选、拓扑 HUD、可视化 UV 投射 |
| 🔨 网格工具 | 焊接共面/边到面、交点打断、顶点色/属性写入 |
| 🧱 大纲视图 | 空物体层级 ↔ 集合层级、集合实例打包 |
| 🎞 VSE / 文本 | 片段对齐/堆叠、文本批量处理、多语言输入 |
| 🌍 多语言 | 简体中文 / English 双语界面 |

## 📦 安装

1. 下载本仓库为 `.zip`（`Code` → `Download ZIP`）
2. Blender → 编辑 → 偏好设置 → 插件 → 安装
3. 勾选启用 `AA_Better_Experie`

## 🔧 环境要求

- Blender 4.5 及以上（推荐 5.x）
- 最低支持：Windows / macOS / Linux

## 🗂 项目结构

```
Better_Experie/
├── ops/             # 操作符（按编辑器分类）
│   ├── view3d/      #   3D 视图 / 网格编辑
│   ├── nodetree/    #   节点编辑器
│   ├── filebrowser/ #   文件浏览器
│   ├── outliner/    #   大纲视图
│   ├── sequencer/   #   视频序列编辑器
│   └── texteditor/  #   文本编辑器
├── menu/            # 菜单 / 面板注入
├── translation/     # 多语言（zh_HANS / en_US）
├── docs/            # 文档（功能说明书 HTML）
├── utils/           # 通用工具
└── scripts/         # 开发工具（翻译提取 / CSV 转换）
```

## 👤 作者

**来一点咖啡吗 (rara)** · [Bilibili](https://space.bilibili.com/27284213)

## 📄 License

GPL-3.0-or-later
