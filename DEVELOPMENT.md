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
