# 开发文档

记录开发过程中的关键问题和解决思路。

---

## 1. 对话框显示空白

**现象：** 面板打开后完全空白，没有任何控件。

**原因：** 异步对话框的 Python 对象被垃圾回收了。

`Execute()` 中用局部变量 `dlg = Dialog()`，函数返回后 `dlg` 被回收，C4D 窗口失去 Python 回调连接，显示空白。

**解决：** 用 `self._dlg` 保存引用，并将 `Execute` 改为切换式（打开/关闭）。

**思考：** C4D Python SDK 的「引用计数 + C++ 对象生命周期」容易踩坑。官方示例虽用 `global` 解决，但正确做法是 **CommandData 保持对话框引用**。

```python
if self._dlg is None or not self._dlg.IsOpen():
    self._dlg = Dialog()
    self._dlg.Open(...)
else:
    self._dlg.Close()
    self._dlg = None
```

---

## 2. 第二次打开崩溃

**现象：** 第一次打开正常，关闭后再次打开 → C4D 崩溃。

**崩溃栈：** `Py_HashPointer` + `PyIter_Send` —— Python 尝试 hash 已释放的 C4D 对象。

**根因：** `RestoreLayout()` 未正确处理。C4D 可能在用户关闭对话框后调用 `RestoreLayout` 恢复布局，如果该函数尝试 `Open()` 一个已经销毁的旧对话框，导致崩溃。

**解决：** `RestoreLayout` 直接返回 `True`（不做任何操作），加上 `dialogid=0` 避免与插件 ID 冲突。

**思考：** C4D 对异步对话框的生命周期管理有两个入口（`Execute` 和 `RestoreLayout`），第二个很容易被忽略。在处理「第二次打开崩溃」时，花了多次迭代才定位到 `RestoreLayout`。

---

## 3. 按钮不显示（GroupBegin 的 name 参数）

**现象：** 添加排序下拉框后，所有按钮都不显示了。

**根因：** `GroupBegin` 不接受 `name=` 关键词参数，它用的是 `title=`。错误写法 `GroupBegin(id, flags, cols, rows, name="xxx")` 抛出 `TypeError`，`CreateLayout` 提前退出，后面控件全部被跳过。

**修复：** 去掉 `name=`，改用位置参数 `GroupBegin(id, flags, cols, rows, "xxx")`。

**思考：** C4D 很多方法的参数名与常规理解不同（`AddStaticText` 用 `name=`，`GroupBegin` 却用 `title=`）。这种不一致导致了一个无声崩溃 —— 没有错误弹窗，只有第一个 StaticText 可见。

---

## 4. 孤立显示无效（Hide() 不存在）

**现象：** 点击 O 按钮后物体没有隐藏。

**根因：** C4D Python SDK 中 **`BaseObject.Hide()` 方法不存在**。第一次尝试 `SetBit(BIT_HIDDEN)` 无效果，第二次尝试 `Hide(True)` → `AttributeError` 被 try/except 静默吞掉。

**修复：** 改用 `SetBit(BIT_IGNOREDRAW)` 控制编辑器绘制可见性。经测试 `BIT_IGNOREDRAW` 是 `BaseList2D` 中与可见性最直接相关的标志。

**思考：** C4D Python API 没有统一的「隐藏/显示」接口，可见性控制分散在 Bit 标志、图层参数、描述参数中。`BIT_IGNOREDRAW` 是最简单可靠的方案。

---

## 5. 排序后选中错误

**现象：** 排序后列表顺序变了，点击第 2 行选中的却是错误物体。

**根因：** 数据分两个列表：`_objects`（未排序）和 `_sorted_objects`（排序后显示）。`_handle_row` 用排序后的行索引去 `_objects` 中查找，取错了物体。

**修复：** 每次刷新列表时将排序结果存入 `self._sorted_objects`，`_handle_row` 一律用 `_sorted_objects` 查找。

**思考：** 数据层和展示层分离时，必须保持「展示索引 → 数据索引」的一致映射。用独立字段保存排序后的列表比实时计算更安全。

---

## 6. ScrollGroupEnd 不存在

**现象：** C4D 2024 报 `AttributeError: 'GeDialog' has no attribute 'ScrollGroupEnd'`。

**修复：** 用 `GroupEnd()` 结束滚动组。

**思考：** C4D Python SDK 中部分 API 与 C++ SDK 不完全一致（`ScrollGroupBegin` 存在但 `ScrollGroupEnd` 不存在）。开发时应以 Python SDK 文档为准。

---

## 7. 扫描参数化物体

**现象：** `GetPolygonCount()` 对参数化物体（未 C 掉的立方体、球体）返回 0。

**修复：** 先用 `GetPolygonCount()`，如果为 0 且不是 `Opolygon` 类型，则尝试 `GetCache()` 获取生成后的多边形数据递归统计。

**思考：** C4D 的参数化物体没有直接的面数数据，需要通过缓存获取。`_count_faces_recursive()` 成为了整个插件的基石函数。

---

## 8. 孤立显示在老工程中无效

**现象：** 新开工程可以使用孤立功能，但老工程中点击后物体没有隐藏。

**根因：** `BIT_IGNOREDRAW` 无法覆盖 Layer 或明确的编辑器模式设置（Object Manager 中的眼睛/点图标）。老工程中的对象可能属于 Layer，Layer 的可见性设置会覆盖对象级别的 Bit 标志。

**修复：** 改用 `SetEditorMode(c4d.MODE_OFF)` 隐藏对象，`SetEditorMode(c4d.MODE_ON)` 显示对象，同时配合 `BIT_IGNOREDRAW` 确保兼容性。

**思考：** C4D 的可见性控制层级较多：Layer 级别 > 对象级别 > Bit 标志。最可靠的方案是直接操作对象的编辑器模式。

---

## 9. 显示全部影响之前的操作

**现象：** 使用孤立功能后，点击显示全部会取消所有对象的隐藏状态，包括用户之前手动隐藏的对象。

**根因：** 显示全部时强制将所有对象设为 `MODE_UNDEF`，没有保存孤立前的原始状态。

**修复：** 在孤立前保存所有对象的原始状态（编辑器模式 + BIT_IGNOREDRAW）到 `self._original_modes`，显示全部时恢复到原始状态而非强制取消隐藏。

**思考：** 状态保存/恢复模式是实现「临时操作」的标准模式，需要在操作前记录状态，操作后根据需要恢复。

---

## 10. 同名对象导致混乱

**现象：** 场景中有多个同名对象时，点击列表中的某一行可能选中错误的对象。

**根因：** 使用对象名称查找对象（`_find_object(doc, name)`），同名时返回第一个匹配的对象，导致选中错误。

**修复：** 改用对象 GUID 查找（`_find_object(doc, guid)`）。在 `_scan()` 中保存 `cur.GetGUID()`，查找时用 GUID 精确匹配。

**思考：** C4D 对象名称不唯一，必须使用 GUID 或对象指针作为唯一标识符。

---

## 11. 父级组对象统计子级面数

**现象：** 扫描时会把父级组对象的子级面数统计到父级上，导致父级排在最前面。

**根因：** `_scan()` 会遍历所有对象（包括组对象），并使用 `_count_faces_recursive()` 统计递归面数。

**修复：** 只对 `c4d.Opolygon` 类型的对象进行统计，使用 `cur.GetPolygonCount()` 直接获取单个对象的面数，不再递归统计子级。

**思考：** 用户需要的是每个多边形对象的独立面数统计，而非组对象的累积面数。需要与 C4D 对象管理器的筛选逻辑保持一致。

---

## 12. 多次独显后显示全部无法恢复

**现象：** 多次点击不同对象的"O"按钮（孤立显示）后，点击"显示全部"只能恢复到最后一次孤立前的状态，无法恢复到最开始的状态。用户需要多次撤销才能回到初始状态。

**原因：** 每次点击"孤立"按钮时都会执行 `self._original_modes.clear()`，导致只保存最后一次操作前的状态，`_original_modes` 被反复清空重置。

**修复：** 移除 `self._original_modes.clear()`，改为条件判断：只在 `_original_modes` 为空时（即第一次点击"孤立"）才保存原始状态到 `_original_modes`。这样无论中间切换多少次孤立对象，"显示全部"都能根据 `_original_modes` 恢复到最开始的状态，并在恢复后自动清空 `_original_modes`。

**思考：** 这是一个典型的「状态快照」语义问题。临时操作（如孤立显示）需要保存「进入临时状态前的那一刻」的完整状态，而不是「每次临时操作切换时」的状态。正确的做法是在第一次进入临时状态时保存快照，退出临时状态时恢复并清除快照。
