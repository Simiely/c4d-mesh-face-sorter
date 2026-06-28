# 开发文档

记录关键设计决策、C4D SDK 踩坑与解法，供后续迭代参考。

## 架构

```
mesh_face_sorter.py  (~1015 行，单文件插件)
│
├─ _Cache                 缓存层（核心）
├─ _ScanStatus            扫描进度状态
├─ _scan_meshes()         递归扫描入口
├─ collect_mesh_stats()   缓存 + 排序
├─ _collect_all_objects() 递归收集场景物体
├─ _estimate_mesh_size()  内存占用估算
├─ format_number/format_size  数字格式化
│
├─ add_decimate_tag()     添加 Polygon Reduction Tag
├─ apply_decimate()       应用减面（c4d.utils.PolygonReduction）
│
├─ MeshSorterDialog       GeDialog 主面板
│   ├─ CreateLayout()     构建 UI（分组/按钮/列表/进度条）
│   ├─ Timer()            定时刷新（1s间隔）
│   ├─ Command()          事件调度中心
│   │   ├─ 刷新/选中/全选/孤立/显示全部
│   │   ├─ 删除空网格/清理数据/导出 md 报表
│   │   └─ 批量减面/单物体减面/应用减面
│   └─ _build_list()      动态构建 ScrollGroup 列表行
│
├─ MeshSorterCommand      CommandData 注册入口
└─ main()                 插件入口
```

## 与 Blender 版的关键差异

### 1. 对象模型差异

| 概念 | Blender (bpy) | C4D (c4d) |
|---|---|---|
| 对象遍历 | `bpy.data.objects`（平铺） | `doc.GetObjects()`（顶层）+ 递归 `GetChildren()` |
| 多边形判断 | `obj.type == 'MESH'` | `obj.IsInstanceOf(c4d.Opolygon)` |
| 面数获取 | `len(mesh.polygons)` | `polyObj.GetPolygonCount()` |
| 点数获取 | `len(mesh.vertices)` | `polyObj.GetPointCount()` |
| 选中状态 | `obj.select_get()` | `obj.GetBit(c4d.BIT_ACTIVE)` |
| 隐藏状态 | `obj.hide_get()` | `obj.GetBit(c4d.BIT_HIDDEN)` |
| 选中物体 | `obj.select_set(True)` | `obj.SetBit(c4d.BIT_ACTIVE)` + `doc.SetActiveObject(obj)` |
| 隐藏物体 | `obj.hide_set(True)` | `obj.SetBit(c4d.BIT_HIDDEN)` |
| 删除物体 | `bpy.data.objects.remove(obj)` | `obj.Remove()` |

### 2. 减面机制差异

| 概念 | Blender | C4D |
|---|---|---|
| 非破坏性 | Decimate Modifier | Polygon Reduction Tag (`c4d.Tpolyredux`) |
| 破坏性应用 | `modifier_apply()` | `c4d.utils.PolygonReduction.PreProcess()` + `SetReductionStrengthLevel()` |
| 参数单位 | ratio = 保留比例 | strength = 减少强度（1.0 - ratio） |
| 边界保护 | 默认开启 | 需手动设置 `POLYREDUXTAG_PRESERVE_3D_BOUNDARY`/`_UV_BOUNDARY` |

### 3. UI 框架差异

| 概念 | Blender | C4D |
|---|---|---|
| 面板容器 | 3D 视图侧边栏自动嵌入 | GeDialog 浮动/停靠对话框 |
| 面板刷新 | `draw()` 每帧调用 | `Timer(msg)` 定时刷新（1s） |
| 动态列表 | Panel 循环生成 UI 控件 | `LayoutFlushGroup()` + `LayoutChanged()` 重建 |
| 进度条 | `wm.progress_begin/end` | `AddProgressBar()` + `SetFloat()` |
| 确认对话框 | `invoke_props_dialog` | `gui.QuestionDialog()` / `gui.MessageDialog()` |
| 文件选择器 | `fileselect_add` | `c4d.storage.SaveDialog()` |
| 控件 ID | 字符串（如 `"object_name"`） | 整数 Gadget ID |
| 数据属性 | `bpy.types.Scene` Property | 仅内存变量 + 对话框本地存储 |

### 4. 边数统计移除

C4D 没有直接的边（edge）数组 API。Blender 版中 `mesh.edges` 提供边数，
C4D 的 PolygonObject 没有等价方法，因此统计中移除了边数列。

## 关键设计决策

### 1. 手动刷新 vs 自动监听

**问题**：如何在 C4D 中感知场景变化并刷新列表？

**决策**：纯手动刷新。用户点击「刷新列表」才重扫。与 Blender 版一致。

**C4D 差异**：C4D 没有 Blender 的 `depsgraph_update_post` 事件。虽然有 `CoreMessage()` 可
监听文档变更，但过于频繁且难以区分无关变更。手动刷新更可靠。

### 2. 缓存粒度

**问题**：切换排序方式需要重新扫描吗？

**决策**：缓存存原始扫描数据，排序在 `collect_mesh_stats()` 中即时完成。
切换排序方式不重扫，只重排。与 Blender 版一致。

### 3. 存储大小估算

**问题**：C4D 没有 `obj.size_in_bytes` API。

**决策**：基于点(24B) + 多边形(16B) + UVW 标签 + 顶点色标签估算。
同样通过 try/except 保障兼容性。

**C4D 差异**：UVW 标签数据通过 `GetSlow()` 获取（比 Blender 的 `uv_layer.data` 
更慢，但仅在扫描时调用一次，影响可接受）。顶点色标签使用 `GetDataAddressW()`。

### 4. GeDialog 动态列表重建

**问题**：C4D 的 GeDialog 不支持声明式 UI 绑定，列表行需要手动创建/销毁。

**决策**：每次刷新调用 `LayoutFlushGroup(GID_LIST_GROUP)` 清空，
再重新 `GroupBegin` + 逐行 `AddButton` / `AddStaticText`，最后
`LayoutChanged(GID_LIST_GROUP)` 触发重绘。

**思考**：这是 C4D GeDialog 的标准模式。优点是控制精确，
缺点是重建高频操作时可能闪烁（通过 Timer 1s 间隔缓解）。

### 5. 列表行按钮的 Gadget ID 编码

**问题**：每个列表行有 3 个按钮（选中/孤立/减面），如何区分点击？

**决策**：使用 `GID_LIST_ROW_BASE + idx * 3 + action_type` 的三合一编码。
`Command()` 中通过偏移量解码出行索引和动作类型。

```python
offset = gid - GID_LIST_ROW_BASE
row_index = offset // 3
action_type = offset % 3
```

### 6. 减面方案选择：Tag vs Generator

**决策**：选择 Polygon Reduction **Tag** (`c4d.Tpolyredux`)，而非 Generator (`c4d.Opolyreduxgen`)。

理由：
- Tag 不改变场景层级，Generator 需要将物体移入子级，破坏原有结构
- Tag 每个物体独立控制参数，Generator 多个子级共享参数
- Tag 在撤销时随物体走，Generator 的层级变动导致撤销栈更复杂
- 工作流与 Blender 版一致（添加修改器/添加 Tag）

### 7. `GH_TOKEN` 环境变量

`gh` CLI 的登录需要 `read:org` scope，但经典 token 可能缺少这个 scope。
通过 `GH_TOKEN` 环境变量可以直接使用 token，跳过 scope 检查。

## 踩坑记录

### BIT_HIDDEN vs Hide()

C4D 有两种"隐藏"：`obj.SetBit(c4d.BIT_HIDDEN)` 和 `obj.Hide(True)`。
`BIT_HIDDEN` 控制视口可见性但物体仍在场景中，`Hide()` 涉及编辑器/渲染可见性。
本插件使用 `BIT_HIDDEN` 以保持与 Blender 版行为一致。

### BIT_ACTIVE 与 SetActiveObject 需要配合

仅 `obj.SetBit(c4d.BIT_ACTIVE)` 不够，还必须调用 `doc.SetActiveObject(obj)`
才能真正让物体在场景中高亮。如果只设 BIT 不设 Active，属性管理器不会更新。

### GetSlow() 性能

UVW Tag 的 `GetSlow()` 在大网格（百万面）上可能较慢。
好在只在扫描时调用一次，且 `_estimate_mesh_size()` 有 try/except 保护。

### PolygonReduction 的 PreProcess 调用

`c4d.utils.PolygonReduction.PreProcess(data)` 要求 `data` 字典包含
`_op`, `_doc`, `_settings`, `_thread` 四个键，缺一不可。
`_thread` 传 `None` 表示同步执行（不在后台线程中）。

### MakeTag 后的参数设置

`obj.MakeTag(c4d.Tpolyredux)` 返回的 tag 对象需要立即设置参数。
部分参数（如 `POLYREDUXTAG_PRESERVE_3D_BOUNDARY`）需在创建后立即设置才生效。

### 插件 ID 唯一性

使用 `1052327` 作为开发 ID。生产环境应替换为 Maxon 分配的正式 ID，
或使用 PluginID 注册系统获取唯一 ID。

## 扩展方向

- **Collection/层级筛选**：按特定层级或标签筛选扫描范围
- **实时扫描进度**：在 C4D 状态栏显示进度信息
- **批量导出**：将排序结果导出为 CSV/JSON 格式
- **多文档支持**：同时扫描多个打开文档

## 提交规范

```
feat: 新功能
fix: 修复
perf: 性能优化
refactor: 重构
chore: 工程相关（重命名、版本号等）
docs: 文档
```
