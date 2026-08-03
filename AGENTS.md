# AGENTS.md · 项目规则

> 写给 AI / 未来维护者的项目上下文。只记录代码里看不出的信息。

## 技术栈

- C4D Python SDK（**C4D 2023 – 2026**），单文件 `.pyp` 插件
- 插件目录结构：`mesh_face_sorter/mesh_face_sorter.pyp` + `res/c4d_symbols.h`（**必须创建空白 c4d_symbols.h**，否则插件加载失败）
- 无构建工具；UI 用 GeDialog 异步对话框

## 关键坑（改代码前必读）

1. **对话框生命周期**：CommandData 必须用 `self._dlg` 保持对话框引用（局部变量会被垃圾回收导致面板空白）；`RestoreLayout()` 直接 `return True`，不要 `Open()` 旧对话框（否则二次打开崩溃）
2. **可见性控制**：`BaseObject.Hide()` **不存在**；用 `SetEditorMode(c4d.MODE_OFF/ON)`（最可靠）+ `SetBit(BIT_IGNOREDRAW)` 兼容。孤立显示必须先保存原始状态快照（**只在第一次时保存**），显示全部时恢复并清空
3. **对象标识用 GUID**：`GetGUID()` 保存/查找对象，**不要用名称**（场景同名对象会导致选中错误）
4. **API 参数命名坑**：`GroupBegin` 用 `title=` 不用 `name=`（`name=` 是 `AddStaticText` 的）；`ScrollGroupEnd` **不存在**，用 `GroupEnd()` 结束滚动组；C4D 部分 API 与 C++ SDK 文档不一致，以 Python SDK 为准
5. **参数化物体面数**：`GetPolygonCount()` 对未 C 掉的参数化物体返回 0，需 `GetCache()` 取生成后的多边形递归统计

## 约定

- UI 标签用中文；面板操作按钮集中；排序/筛选/导出都在面板完成
- 可见性操作遵循「保存快照 → 操作 → 恢复」模式
- 新增功能后更新 DEVELOPMENT.md 问题记录

## 常用命令

- 无构建 / 无测试命令；验证 = 放入 C4D 插件目录重启 C4D
- 发布 = 打包 zip（.pyp + icon），见知识库 模板/插件Release打包模板
- 详细开发记录见 DEVELOPMENT.md；版本历史见 CHANGELOG.md
