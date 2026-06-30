"""C4D Mesh Face Sorter

Compatible: C4D 2023+ (2024/2025/2026)
License: MIT
"""

import c4d
import datetime
from c4d import gui

# ──────────────────────────────
# Plugin metadata
# ──────────────────────────────
PLUGIN_ID = 1052328
PLUGIN_NAME = "Mesh Face Sorter"
PLUGIN_HELP = "按面数/存储大小排列网格体"


# ──────────────────────────────
# Helpers
# ──────────────────────────────
def _count_faces_recursive(obj, max_depth=10):
    if obj is None or max_depth <= 0:
        return 0
    total = 0
    try:
        if obj.IsInstanceOf(c4d.Opolygon):
            total += obj.GetPolygonCount()
        else:
            cache = obj.GetCache()
            if cache:
                total += _count_faces_recursive(cache, max_depth - 1)
            child = obj.GetDown()
            while child:
                total += _count_faces_recursive(child, max_depth - 1)
                child = child.GetNext()
    except Exception:
        pass
    return total


def _estimate_size(obj):
    try:
        pts = obj.GetPointCount()
        polys = obj.GetPolygonCount()
        return pts * 24 + polys * 16
    except Exception:
        return 0


def _fmt_num(n):
    if n >= 1000000:
        return f"{n/1000000:.1f}M"
    if n >= 1000:
        return f"{n/1000:.1f}K"
    return str(n)


def _fmt_size(n):
    if n >= 1048576:
        return f"{n/1048576:.1f}MB"
    if n >= 1024:
        return f"{n/1024:.1f}KB"
    return f"{n}B"


# ──────────────────────────────
# Dialog — Main UI
# ──────────────────────────────
class MeshSorterDialog(gui.GeDialog):

    GID_STATUS = 1001
    GID_STAT_COUNT = 1002
    GID_SORT_COMBO = 1010
    GID_SORT_TOGGLE = 1011
    GID_BTN_REFRESH = 2000
    GID_BTN_SHOWALL = 2010
    GID_BTN_EXPORT = 2011
    GID_LIST_SCROLL = 3000
    GID_LIST_GROUP = 3001
    # 列表行按钮从 4000 起，每行占 3 个 ID（名称, 孤立, 减面）

    def __init__(self):
        super().__init__()
        self._objects = []
        self._doc_objects = {}  # name -> obj 映射
        self.sort_by = "faces"
        self.descending = True

    def CreateLayout(self):
        self.SetTitle("Mesh Face Sorter")

        # 状态区
        self.AddStaticText(self.GID_STATUS, c4d.BFH_SCALEFIT, 0, 0,
                               name="点击「刷新列表」扫描场景",
                               borderstyle=c4d.BORDER_NONE)
        self.AddStaticText(self.GID_STAT_COUNT, c4d.BFH_SCALEFIT, 0, 0,
                               name="",
                               borderstyle=c4d.BORDER_NONE)

        # 操作区：排序 + 刷新
        self.GroupBegin(1020, c4d.BFH_SCALEFIT, 3, 0, "操作：")
        self.AddComboBox(self.GID_SORT_COMBO, c4d.BFH_SCALEFIT, 120, 12)
        self.AddChild(self.GID_SORT_COMBO, 0, "面数")
        self.AddChild(self.GID_SORT_COMBO, 1, "存储大小")
        self.SetInt32(self.GID_SORT_COMBO, 0)
        self.AddButton(self.GID_SORT_TOGGLE, c4d.BFH_SCALEFIT, 30, 20, name="↓↑")
        self.AddButton(self.GID_BTN_REFRESH, c4d.BFH_SCALEFIT, 120, 20, name="刷新")
        self.GroupEnd()

        # 按钮区
        self.GroupBegin(1030, c4d.BFH_SCALEFIT, 3, 0, "")
        self.AddButton(self.GID_BTN_SHOWALL, c4d.BFH_SCALEFIT, 120, 20, name="显示全部")
        self.AddButton(self.GID_BTN_EXPORT, c4d.BFH_SCALEFIT, 120, 20, name="导出报表")
        self.GroupEnd()

        # 列表区（滚动组）
        self.ScrollGroupBegin(self.GID_LIST_SCROLL,
                              c4d.BFH_SCALEFIT | c4d.BFV_SCALEFIT,
                              c4d.SCROLLGROUP_VERT, 380, 200)
        self.GroupBegin(self.GID_LIST_GROUP,
                        c4d.BFH_SCALEFIT | c4d.BFV_SCALEFIT, 1, 0)
        self.AddStaticText(0, c4d.BFH_SCALEFIT, 0, 0, name="（点击「刷新」开始扫描）")
        self.GroupEnd()
        self.ScrollGroupEnd()

        return True

    def Command(self, gid, msg):
        if gid == self.GID_SORT_COMBO:
            idx = self.GetInt32(self.GID_SORT_COMBO)
            self.sort_by = "faces" if idx == 0 else "size"
            self._refresh_list()

        elif gid == self.GID_SORT_TOGGLE:
            self.descending = not self.descending
            label = "↓" if self.descending else "↑"
            self.SetString(self.GID_SORT_TOGGLE, label)
            self._refresh_list()

        elif gid == self.GID_BTN_REFRESH:
            self._do_refresh()

        elif gid == self.GID_BTN_SHOWALL:
            self._do_show_all()

        elif gid == self.GID_BTN_EXPORT:
            self._do_export()

        # 列表行按钮
        elif gid >= 4000:
            self._handle_row_action(gid)

        return True

    # ────────────── 操作实现 ──────────────

    def _do_refresh(self):
        doc = c4d.documents.GetActiveDocument()
        if doc is None:
            return

        def _scan(obj):
            result = []
            stack = [obj]
            while stack:
                current = stack.pop()
                if current is None:
                    continue
                try:
                    faces = _count_faces_recursive(current)
                    result.append({
                        "name": current.GetName(),
                        "faces": faces,
                        "size": _estimate_size(current),
                    })
                except Exception:
                    pass
                child = current.GetDown()
                while child:
                    stack.append(child)
                    child = child.GetNext()
            return result

        all_objects = []
        self._doc_objects.clear()
        try:
            for obj in doc.GetObjects():
                all_objects.extend(_scan(obj))
        except Exception:
            return

        self._objects = all_objects
        count = len(all_objects)
        total_faces = sum(o["faces"] for o in all_objects)
        total_size = sum(o["size"] for o in all_objects)

        self.SetString(self.GID_STATUS, f"扫描完成：{count} 个物体")
        self.SetString(self.GID_STAT_COUNT,
                       f"网格体：{count}    总面数：{_fmt_num(total_faces)}    总存储：{_fmt_size(total_size)}")
        self._refresh_list()

    def _do_show_all(self):
        """显示全部：取消所有物体的隐藏"""
        doc = c4d.documents.GetActiveDocument()
        if doc is None:
            return
        count = 0
        try:
            for obj in _collect_all(doc):
                try:
                    if obj.GetBit(c4d.BIT_HIDDEN):
                        obj.DelBit(c4d.BIT_HIDDEN)
                        count += 1
                except Exception:
                    pass
        except Exception:
            pass
        c4d.EventAdd()
        if count > 0:
            self._do_refresh()
        print(f"[MeshFaceSorter] 已取消 {count} 个物体的隐藏")

    def _do_export(self):
        """导出 md 报表"""
        if not self._objects:
            gui.MessageDialog("请先点击「刷新」扫描场景。")
            return

        path = c4d.storage.SaveDialog(
            title="导出 MD 报表",
            flags=c4d.FILESELECT_SAVE,
            def_path="",
            def_file="mesh_report.md",
        )
        if not path:
            return
        if not path.lower().endswith(".md"):
            path += ".md"

        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        sort_label = "面数" if self.sort_by == "faces" else "存储大小"
        order_label = "降序" if self.descending else "升序"

        lines = [
            "# 网格体报表",
            "",
            f"- **生成时间**：{now}",
            f"- **排序方式**：{sort_label}（{order_label}）",
            f"- **网格体总数**：{len(self._objects)}",
            f"- **总面数**：{sum(o['faces'] for o in self._objects)}",
            f"- **总存储**：{_fmt_size(sum(o['size'] for o in self._objects))}",
            "",
            "| # | 物体名称 | 面数 | 存储 |",
            "|---|---|---|---|",
        ]
        for i, item in enumerate(self._objects, 1):
            lines.append(f"| {i} | {item['name']} | {item['faces']} | {_fmt_size(item['size'])} |")

        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
            gui.MessageDialog(f"已导出 {len(self._objects)} 个物体到：\n{path}")
        except Exception as e:
            gui.MessageDialog(f"导出失败：{e}")

    # ────────────── 列表行处理 ──────────────

    def _handle_row_action(self, gid):
        """处理列表行按钮点击"""
        idx = gid - 4000
        action_type = idx % 3
        row_idx = idx // 3

        if row_idx >= len(self._objects):
            return

        item = self._objects[row_idx]
        doc = c4d.documents.GetActiveDocument()
        if doc is None:
            return

        # 查找物体
        obj = _find_object(doc, item["name"])
        if obj is None:
            return

        if action_type == 0:
            # 选中物体
            doc.StartUndo()
            for o in _collect_all(doc):
                try:
                    doc.AddUndo(c4d.UNDOTYPE_CHANGE_SMALL, o)
                    o.DelBit(c4d.BIT_ACTIVE)
                except Exception:
                    pass
            doc.AddUndo(c4d.UNDOTYPE_CHANGE_SMALL, obj)
            obj.SetBit(c4d.BIT_ACTIVE)
            doc.SetActiveObject(obj)
            doc.EndUndo()
            c4d.EventAdd()
            self._refresh_list()

        elif action_type == 1:
            # 孤立显示
            doc.StartUndo()
            for o in _collect_all(doc):
                try:
                    doc.AddUndo(c4d.UNDOTYPE_CHANGE_SMALL, o)
                    if o == obj:
                        o.DelBit(c4d.BIT_HIDDEN)
                    else:
                        o.SetBit(c4d.BIT_HIDDEN)
                except Exception:
                    pass
            doc.EndUndo()
            c4d.EventAdd()
            self._do_refresh()

        elif action_type == 2:
            # 减面 Tag
            self._do_decimate_single(obj, doc)

    def _do_decimate_single(self, obj, doc):
        """为单个物体添加 Polygon Reduction Tag"""
        try:
            if not obj.GetPolygonCount():
                gui.MessageDialog(f"{obj.GetName()} 没有多边形数据。")
                return
        except Exception:
            return

        tag = obj.GetTag(c4d.Tpolyredux)
        if tag:
            gui.MessageDialog(f"{obj.GetName()} 已有减面 Tag。")
            return

        doc.StartUndo()
        tag = obj.MakeTag(c4d.Tpolyredux)
        if tag:
            tag[c4d.POLYREDUXTAG_STRENGTH] = 0.5
            tag[c4d.POLYREDUXTAG_PRESERVE_3D_BOUNDARY] = True
            tag[c4d.POLYREDUXTAG_PRESERVE_UV_BOUNDARY] = True
            doc.AddUndo(c4d.UNDOTYPE_NEW, tag)
        doc.EndUndo()
        c4d.EventAdd()
        print(f"[MeshFaceSorter] 已为 {obj.GetName()} 添加减面 Tag")

    # ────────────── 列表渲染 ──────────────

    def _refresh_list(self):
        objs = self._objects
        if self.sort_by == "faces":
            objs = sorted(objs, key=lambda x: x["faces"], reverse=self.descending)
        else:
            objs = sorted(objs, key=lambda x: x["size"], reverse=self.descending)

        self.LayoutFlushGroup(self.GID_LIST_GROUP)
        self.GroupBegin(self.GID_LIST_GROUP,
                        c4d.BFH_SCALEFIT | c4d.BFV_SCALEFIT, 1, 0)

        # 表头
        sort_label = "面数" if self.sort_by == "faces" else "存储"
        self.AddStaticText(0, c4d.BFH_SCALEFIT, 0, 0,
                           name=f"  物体名称                    {sort_label}*   O   -",
                           borderstyle=c4d.BORDER_THIN_IN)

        # 列表行
        for i, item in enumerate(objs[:100]):
            base_id = 4000 + i * 3
            name = item["name"]
            if len(name) > 22:
                name = name[:20] + ".."
            val = item["faces"] if self.sort_by == "faces" else item["size"]
            val_str = _fmt_num(val) if self.sort_by == "faces" else _fmt_size(val)
            display = f"  {name:<22} {val_str:>6}"

            self.GroupBegin(base_id, c4d.BFH_SCALEFIT, 3, 0, "")
            self.AddButton(base_id,     c4d.BFH_SCALEFIT, 270, 16, name=display)  # 选中
            self.AddButton(base_id + 1, c4d.BFH_SCALEFIT, 20, 16, name="O")       # 孤立
            self.AddButton(base_id + 2, c4d.BFH_SCALEFIT, 20, 16, name="-")       # 减面
            self.GroupEnd()

        if len(objs) > 100:
            self.AddStaticText(0, c4d.BFH_SCALEFIT, 0, 0,
                               name=f"（仅显示前 100 个，共 {len(objs)} 个）")

        self.GroupEnd()
        self.LayoutChanged(self.GID_LIST_GROUP)


# ──────────────────────────────
# Module-level helpers
# ──────────────────────────────
def _collect_all(doc):
    """递归收集所有物体"""
    result = []
    stack = list(doc.GetObjects())
    while stack:
        obj = stack.pop()
        if obj is None:
            continue
        result.append(obj)
        child = obj.GetDown()
        while child:
            stack.append(child)
            child = child.GetNext()
    return result


def _find_object(doc, name):
    """在文档中按名称查找物体"""
    for obj in _collect_all(doc):
        try:
            if obj.GetName() == name:
                return obj
        except Exception:
            pass
    return None


# ──────────────────────────────
# Command — Entry point
# ──────────────────────────────
class MeshSorterCommand(c4d.plugins.CommandData):
    def Execute(self, doc):
        dialog = MeshSorterDialog()
        dialog.Open(c4d.DLG_TYPE_ASYNC, 0, -1, -1, 420, 420)
        return True

    def RestoreLayout(self, sec_ref):
        return True


# ──────────────────────────────
# Plugin registration
# ──────────────────────────────
def main():
    try:
        ok = c4d.plugins.RegisterCommandPlugin(
            PLUGIN_ID, PLUGIN_NAME, 0, None, PLUGIN_HELP, MeshSorterCommand(),
        )
        if ok:
            print(f"[MeshFaceSorter] 插件已加载，ID: {PLUGIN_ID}")
        else:
            print(f"[MeshFaceSorter] 注册失败")
    except Exception as e:
        print(f"[MeshFaceSorter] 加载异常：{e}")


main()
