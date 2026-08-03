# 开发文档（DEVELOPMENT.md）

> 面向开发者的项目文档：架构说明 + 关键问题与方案（一坑一篇）。
> 每个问题用统一格式：**TL;DR**（一句话结论）→ 问题 / 根因 / 解决 / 预防。

## 项目概览

C4D 插件（v2.0.3，兼容 C4D 2023-2026），单文件 `.pyp`。按面数/存储大小排列场景多边形物体，支持孤立显示、删除空物体、导出 Markdown 报表。

## 架构说明

```
mesh_face_sorter.pyp
├── CommandData（插件入口）
│   ├── Execute()：切换式打开/关闭对话框（self._dlg 保持引用）
│   └── RestoreLayout()：直接 return True（避免二次打开崩溃）
├── Dialog（GeDialog 异步对话框）
│   ├── CreateLayout()：排序控件 + 功能按钮 + 列表
│   ├── _scan()：扫描场景多边形物体（GetGUID + GetPolygonCount + GetCache）
│   ├── 排序逻辑：面数 / 存储大小，升降序切换
│   ├── 孤立显示：SetEditorMode + BIT_IGNOREDRAW，状态快照保存/恢复
│   ├── 删除空物体：面数=0 且无子级的安全删除
│   └── 导出报表：Markdown 场景报告
└── 数据层：_objects（原始）/ _sorted_objects（排序后），GUID 映射
```

## 关键问题与方案

### A. 对话框生命周期

#### A1. 面板打开后完全空白

**TL;DR**：异步对话框的 Python 对象被垃圾回收了——`Execute()` 里用局部变量 `dlg`，函数返回后对象被回收，窗口失去回调连接显示空白。**CommandData 必须保持对话框引用**。

- **问题**：面板打开后完全空白，无任何控件
- **根因**：局部变量 `dlg` 在 `Execute()` 返回后被 GC 回收，C4D 窗口失去 Python 回调连接
- **解决**：用 `self._dlg` 保存引用，Execute 改为切换式（打开/关闭）

```python
if self._dlg is None or not self._dlg.IsOpen():
    self._dlg = Dialog()
    self._dlg.Open(...)
else:
    self._dlg.Close()
    self._dlg = None
```

- **预防**：对话框对象必须挂在 CommandData 实例上，不用局部变量；官方示例用 `global` 是偷懒做法

#### A2. 第二次打开崩溃（RestoreLayout）

**TL;DR**：关闭后再次打开崩溃，根因是 `RestoreLayout()` 尝试 `Open()` 已销毁的旧对话框。**直接 `return True` 不做事**，并设 `dialogid=0`。

- **问题**：第一次打开正常，关闭后再次打开 → C4D 崩溃（栈：`Py_HashPointer` + `PyIter_Send`，hash 已释放的 C4D 对象）
- **根因**：`RestoreLayout()` 未正确处理——用户关闭后 C4D 调用它恢复布局，它却 `Open()` 一个已销毁的对话框
- **解决**：`RestoreLayout` 直接 `return True`（不做任何操作）+ `dialogid=0` 避免与插件 ID 冲突
- **预防**：异步对话框生命周期有两个入口（Execute 和 RestoreLayout），两个都要处理

### B. UI 构建

#### B1. GroupBegin 的 name 参数（按钮全消失）

**TL;DR**：`GroupBegin` 不接受 `name=`，它用 `title=`；写错会抛 TypeError，`CreateLayout` 提前退出导致后面控件全被跳过（无声故障）。

- **问题**：添加排序下拉框后所有按钮都不显示
- **根因**：`GroupBegin(id, flags, cols, rows, name="xxx")` 抛 `TypeError`，CreateLayout 提前退出
- **解决**：去掉 `name=`，改用位置参数 `GroupBegin(id, flags, cols, rows, "xxx")`
- **预防**：C4D 方法参数名与常规理解不一致（AddStaticText 用 `name=`，GroupBegin 用 `title=`），写 UI 前查 Python SDK 签名，别想当然

#### B2. ScrollGroupEnd 不存在

**TL;DR**：C4D Python SDK 没有 `ScrollGroupEnd`（C++ SDK 有），用 `GroupEnd()` 结束滚动组。

- **问题**：C4D 2024 报 `AttributeError: 'GeDialog' has no attribute 'ScrollGroupEnd'`
- **解决**：用 `GroupEnd()` 结束滚动组
- **预防**：Python SDK 与 C++ SDK 不完全一致，以 Python SDK 文档为准

### C. 可见性控制

#### C1. Hide() 方法不存在

**TL;DR**：`BaseObject.Hide()` 不存在；`SetBit(BIT_HIDDEN)` 无效果；`BIT_IGNOREDRAW` 是控制编辑器绘制可见性最直接的标志。

- **问题**：点击 O 按钮物体没有隐藏（AttributeError 被 try/except 静默吞掉）
- **根因**：C4D Python API 没有统一「隐藏/显示」接口，可见性分散在 Bit 标志、图层、描述参数中
- **解决**：`SetBit(BIT_IGNOREDRAW)` 控制编辑器绘制可见性
- **预防**：可见性功能先确认目标 API 存在，异常别静默吞掉

#### C2. 老工程中孤立显示无效

**TL;DR**：`BIT_IGNOREDRAW` 无法覆盖 Layer/编辑器模式设置；**`SetEditorMode(MODE_OFF/ON)` 最可靠**，配合 Bit 标志兼容。

- **问题**：新工程可用，老工程点击后无效果
- **根因**：老工程对象可能属于 Layer，Layer 可见性覆盖对象级 Bit 标志（可见性层级：Layer > 对象 > Bit）
- **解决**：改用 `SetEditorMode(c4d.MODE_OFF)` 隐藏 / `SetEditorMode(c4d.MODE_ON)` 显示，配合 `BIT_IGNOREDRAW`
- **预防**：可见性操作统一走 `SetEditorMode`，Bit 标志只作兼容补充

#### C3. 显示全部影响之前的操作

**TL;DR**：显示全部时不能强制全部显示，要恢复「孤立前的原始状态」——操作前保存快照，操作后恢复。

- **问题**：孤立后点显示全部，连用户之前手动隐藏的对象也显示出来了
- **根因**：显示全部时强制所有对象 `MODE_UNDEF`，没保存孤立前状态
- **解决**：孤立前保存所有对象原始状态（编辑器模式 + BIT_IGNOREDRAW）到 `self._original_modes`，显示全部时恢复
- **预防**：临时操作遵循「保存快照 → 操作 → 恢复」模式

#### C4. 多次独显后无法恢复（状态快照语义）

**TL;DR**：快照要在**第一次进入临时状态时保存**，而不是每次切换都保存（否则只恢复到最后一次）；退出时恢复并清空。

- **问题**：多次点击不同对象 O 按钮后，显示全部只能恢复到最后一次孤立前状态
- **根因**：每次点击都 `self._original_modes.clear()` 再保存，快照被反复重置
- **解决**：移除 clear()，只在 `_original_modes` 为空时保存；恢复后自动清空

```python
if not self._original_modes:   # 只在第一次独显时保存快照
    self._original_modes = snapshot()
```

- **预防**：临时操作保存「进入临时状态前那一刻」的完整状态，不是「每次切换时」的状态

### D. 数据一致性

#### D1. 排序后选中错误

**TL;DR**：数据层与展示层分离时，用独立字段保存排序后的列表（`_sorted_objects`），事件处理一律用它查找，保持「展示索引 → 数据索引」一致映射。

- **问题**：排序后点第 2 行选中的却是错误物体
- **根因**：`_handle_row` 用排序后的行索引去未排序的 `_objects` 查找
- **解决**：刷新时排序结果存入 `self._sorted_objects`，事件处理统一用它

#### D2. 同名对象导致混乱

**TL;DR**：C4D 对象名称不唯一，**用 `GetGUID()` 作为唯一标识**保存和查找，不用名称。

- **问题**：多个同名对象时选中错误对象
- **根因**：`_find_object(doc, name)` 返回第一个同名匹配
- **解决**：`_scan()` 保存 `cur.GetGUID()`，查找用 GUID 精确匹配

#### D3. 父级组对象统计子级面数

**TL;DR**：只对 `c4d.Opolygon` 类型的对象统计面数，用 `GetPolygonCount()` 取单对象面数，不递归统计组对象子级。

- **问题**：扫描时父级组对象把子级面数算进去，排在最前面
- **根因**：`_scan()` 遍历所有对象（含组）并递归统计面数
- **解决**：只统计 `c4d.Opolygon` 类型，`GetPolygonCount()` 直接取单对象面数

### E. 扫描统计

#### E1. 参数化物体面数为 0

**TL;DR**：未 C 掉的参数化物体（立方体/球体）`GetPolygonCount()` 返回 0；用 `GetCache()` 取生成后的多边形数据递归统计。`_count_faces_recursive()` 是整个插件的基石函数。

- **问题**：参数化物体统计面数为 0
- **根因**：参数化物体没有直接的面数数据
- **解决**：`GetPolygonCount()` 为 0 且非 Opolygon 时，`GetCache()` 获取缓存后递归统计

## 开发环境

- Cinema 4D 2023 – 2026 + Python SDK（无构建工具，单文件 .pyp）
- 验证：放入 C4D 插件目录重启

## 版本演进

| 版本 | 核心变更 |
|------|----------|
| v2.0.0 | 排序 / 孤立显示 / 删除空物体 / 导出报表 / 显示全部 |
| v2.0.1 | PNG 透明图标支持 |
| v2.0.2 | 老工程孤立修复（SetEditorMode）/ GUID 查找 / 只统计纯多边形 |
| v2.0.3 | 多次独显恢复修复（状态快照语义） |
