"""C4D Mesh Face Sorter

Compatible: C4D 2023+ (2024/2025/2026)
License: MIT
"""

import c4d
import datetime
from c4d import gui, bitmaps

PLUGIN_ID = 1052328
PLUGIN_NAME = "Mesh Face Sorter"


def _create_plugin_icon():
    import os
    icon_path = os.path.join(os.path.dirname(__file__), "res", "icon.png")
    bmp = bitmaps.BaseBitmap()
    result = bmp.InitWith(icon_path)
    if isinstance(result, tuple):
        if result[0] != c4d.IMAGERESULT_OK:
            return None
    else:
        if result != 0 and result != c4d.IMAGERESULT_OK:
            return None
    return bmp


# ────────────── Helpers ──────────────
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


def _collect_all(doc):
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


def _find_object(doc, guid):
    for obj in _collect_all(doc):
        try:
            if obj.GetGUID() == guid:
                return obj
        except Exception:
            pass
    return None


# ────────────── Dialog ──────────────
class MeshSorterDialog(gui.GeDialog):

    def __init__(self):
        super().__init__()
        self._objects = []
        self._sorted_objects = []  # 排序后的列表，用于行点击索引
        self.sort_by = "faces"
        self.descending = True
        self._original_modes = {}  # 保存对象原始编辑器模式状态

    def CreateLayout(self):
        self.SetTitle("Mesh Face Sorter")

        self.AddStaticText(1001, c4d.BFH_SCALEFIT, 0, 0,
                           name="点击「刷新」扫描场景", borderstyle=c4d.BORDER_NONE)
        self.AddStaticText(1002, c4d.BFH_SCALEFIT, 0, 0,
                           name="", borderstyle=c4d.BORDER_NONE)

        # 操作区
        self.GroupBegin(1010, c4d.BFH_SCALEFIT, 3, 0, "操作：")
        self.AddComboBox(1011, c4d.BFH_SCALEFIT, 120, 12)
        self.AddChild(1011, 0, "面数")
        self.AddChild(1011, 1, "存储大小")
        self.SetInt32(1011, 0)
        self.AddButton(1012, c4d.BFH_SCALEFIT, 30, 20, name="↓↑")
        self.AddButton(1013, c4d.BFH_SCALEFIT, 120, 20, name="刷新")
        self.GroupEnd()

        # 按钮区
        self.GroupBegin(1020, c4d.BFH_SCALEFIT, 3, 0, "")
        self.AddButton(1021, c4d.BFH_SCALEFIT, 120, 20, name="显示全部")
        self.AddButton(1022, c4d.BFH_SCALEFIT, 120, 20, name="导出报表")
        self.AddButton(1023, c4d.BFH_SCALEFIT, 120, 20, name="删除空物体")
        self.GroupEnd()

        # 列表区
        self.ScrollGroupBegin(3000, c4d.BFH_SCALEFIT | c4d.BFV_SCALEFIT,
                              c4d.SCROLLGROUP_VERT, 380, 200)
        self.GroupBegin(3001, c4d.BFH_SCALEFIT | c4d.BFV_SCALEFIT, 1, 0)
        self.AddStaticText(0, c4d.BFH_SCALEFIT, 0, 0, name="（点击「刷新」开始扫描）")
        self.GroupEnd()
        self.GroupEnd()

        return True

    def Command(self, gid, msg):
        if gid == 1011:  # 排序
            idx = self.GetInt32(1011)
            self.sort_by = "faces" if idx == 0 else "size"
            self._refresh_list()
        elif gid == 1012:  # 升降序切换
            self.descending = not self.descending
            self.SetString(1012, "↓" if self.descending else "↑")
            self._refresh_list()
        elif gid == 1013:  # 刷新
            self._do_refresh()
        elif gid == 1021:  # 显示全部
            self._do_show_all()
        elif gid == 1022:  # 导出报表
            self._do_export()
        elif gid == 1023:  # 删除空物体
            self._do_delete_empty()
        elif gid >= 4000:  # 列表行按钮
            self._handle_row(gid)
        return True

    def _do_refresh(self):
        doc = c4d.documents.GetActiveDocument()
        if doc is None:
            return

        def _scan(obj):
            r = []
            stack = [obj]
            while stack:
                cur = stack.pop()
                if cur is None:
                    continue
                try:
                    if cur.IsInstanceOf(c4d.Opolygon):
                        r.append({"name": cur.GetName(),
                                  "guid": cur.GetGUID(),
                                  "faces": cur.GetPolygonCount(),
                                  "size": _estimate_size(cur)})
                except Exception:
                    pass
                child = cur.GetDown()
                while child:
                    stack.append(child)
                    child = child.GetNext()
            return r

        all_objs = []
        try:
            for obj in doc.GetObjects():
                all_objs.extend(_scan(obj))
        except Exception:
            return

        self._objects = all_objs
        total_faces = sum(o["faces"] for o in all_objs)
        total_size = sum(o["size"] for o in all_objs)
        self.SetString(1001, f"扫描完成：{len(all_objs)} 个物体")
        self.SetString(1002, f"网格体：{len(all_objs)}    总面数：{_fmt_num(total_faces)}    总存储：{_fmt_size(total_size)}")
        self._refresh_list()

    def _do_show_all(self):
        doc = c4d.documents.GetActiveDocument()
        if doc is None:
            return
        count = 0
        doc.StartUndo()
        if self._original_modes:
            for o, (mode, ignoredraw) in self._original_modes.items():
                try:
                    doc.AddUndo(c4d.UNDOTYPE_CHANGE_SMALL, o)
                    o.SetEditorMode(mode)
                    if ignoredraw:
                        o.SetBit(c4d.BIT_IGNOREDRAW)
                    else:
                        o.DelBit(c4d.BIT_IGNOREDRAW)
                    count += 1
                except Exception:
                    pass
            self._original_modes.clear()
        else:
            for o in _collect_all(doc):
                try:
                    mode = o.GetEditorMode()
                    if mode != c4d.MODE_UNDEF or o.GetBit(c4d.BIT_IGNOREDRAW):
                        doc.AddUndo(c4d.UNDOTYPE_CHANGE_SMALL, o)
                        o.SetEditorMode(c4d.MODE_UNDEF)
                        o.DelBit(c4d.BIT_IGNOREDRAW)
                        count += 1
                except Exception:
                    pass
        doc.EndUndo()
        c4d.EventAdd()
        if count > 0:
            self._do_refresh()

    def _do_delete_empty(self):
        """删除面数为 0 且没有子级的空物体"""
        doc = c4d.documents.GetActiveDocument()
        if doc is None:
            return
        empty = []
        for obj in _collect_all(doc):
            try:
                if obj.GetDown() is not None:
                    continue  # 有子级，不删
                if obj.GetPolygonCount() == 0 and obj.IsInstanceOf(c4d.Opolygon):
                    empty.append(obj)
            except Exception:
                pass
        if not empty:
            gui.MessageDialog("没有可删除的空物体。")
            return
        ok = gui.QuestionDialog(f"找到 {len(empty)} 个面数为 0 的空物体，确定删除？")
        if not ok:
            return
        doc.StartUndo()
        for obj in empty:
            doc.AddUndo(c4d.UNDOTYPE_DELETE, obj)
            obj.Remove()
        doc.EndUndo()
        c4d.EventAdd()
        gui.MessageDialog(f"已删除 {len(empty)} 个空物体。")
        self._do_refresh()

    def _do_export(self):
        if not self._objects:
            gui.MessageDialog("请先点击「刷新」扫描场景。")
            return
        path = c4d.storage.SaveDialog(c4d.FILESELECTTYPE_ANYTHING,
                                      "导出 MD 报表", ".md", "", "mesh_report.md")
        if not path:
            return
        if not path.lower().endswith(".md"):
            path += ".md"

        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        sort_label = "面数" if self.sort_by == "faces" else "存储大小"
        order_label = "降序" if self.descending else "升序"
        lines = ["# 网格体报表", "",
                 f"- **生成时间**：{now}",
                 f"- **排序方式**：{sort_label}（{order_label}）",
                 f"- **网格体总数**：{len(self._objects)}",
                 f"- **总面数**：{sum(o['faces'] for o in self._objects)}",
                 f"- **总存储**：{_fmt_size(sum(o['size'] for o in self._objects))}",
                 "", "| # | 物体名称 | 面数 | 存储 |",
                 "|---|---|---|---|"]
        for i, item in enumerate(self._objects, 1):
            lines.append(f"| {i} | {item['name']} | {item['faces']} | {_fmt_size(item['size'])} |")
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
            gui.MessageDialog(f"已导出 {len(self._objects)} 个物体到：\n{path}")
        except Exception as e:
            gui.MessageDialog(f"导出失败：{e}")

    def _handle_row(self, gid):
        idx = gid - 4000
        action = idx % 2  # 0=选中, 1=孤立
        row = idx // 2
        if row >= len(self._objects):
            return
        item = self._sorted_objects[row]
        doc = c4d.documents.GetActiveDocument()
        if doc is None:
            return
        obj = _find_object(doc, item["guid"])
        if obj is None:
            return

        if action == 0:  # 选中
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
        elif action == 1:  # 孤立
            try:
                doc.StartUndo()
                self._original_modes.clear()
                for o in _collect_all(doc):
                    try:
                        self._original_modes[o] = (o.GetEditorMode(), o.GetBit(c4d.BIT_IGNOREDRAW))
                        doc.AddUndo(c4d.UNDOTYPE_CHANGE_SMALL, o)
                        if o == obj:
                            o.SetEditorMode(c4d.MODE_ON)
                            o.DelBit(c4d.BIT_IGNOREDRAW)
                        else:
                            o.SetEditorMode(c4d.MODE_OFF)
                            o.SetBit(c4d.BIT_IGNOREDRAW)
                    except Exception:
                        pass
                # 选中孤立对象
                doc.AddUndo(c4d.UNDOTYPE_CHANGE_SMALL, obj)
                obj.SetBit(c4d.BIT_ACTIVE)
                doc.SetActiveObject(obj)
                doc.EndUndo()
                c4d.EventAdd()
            except Exception as e:
                print(f"[MeshFaceSorter] 孤立出错: {e}")
            self._do_refresh()

    def _refresh_list(self):
        objs = self._objects
        if self.sort_by == "faces":
            objs = sorted(objs, key=lambda x: x["faces"], reverse=self.descending)
        else:
            objs = sorted(objs, key=lambda x: x["size"], reverse=self.descending)
        self._sorted_objects = objs  # 保存排序后的列表，用于行点击索引

        self.LayoutFlushGroup(3001)
        self.GroupBegin(3001, c4d.BFH_SCALEFIT | c4d.BFV_SCALEFIT, 1, 0)

        sort_label = "面数" if self.sort_by == "faces" else "存储"
        self.AddStaticText(0, c4d.BFH_SCALEFIT, 0, 0,
                           name=f"  物体名称                    {sort_label}*   O",
                           borderstyle=c4d.BORDER_THIN_IN)

        doc = c4d.documents.GetActiveDocument()
        for i, item in enumerate(objs[:100]):
            base = 4000 + i * 2
            name = item["name"]
            # 检查是否选中
            is_sel = False
            obj = _find_object(doc, item["guid"]) if doc else None
            if obj:
                try:
                    is_sel = obj.GetBit(c4d.BIT_ACTIVE)
                except Exception:
                    pass
            prefix = "▶ " if is_sel else "  "
            if len(name) > 20:
                name = name[:18] + ".."
            val = item["faces"] if self.sort_by == "faces" else item["size"]
            val_str = _fmt_num(val) if self.sort_by == "faces" else _fmt_size(val)
            display = f"{prefix}{name:<20} {val_str:>6}"
            self.GroupBegin(base, c4d.BFH_SCALEFIT, 2, 0, "")
            self.AddButton(base,     c4d.BFH_SCALEFIT, 290, 16, name=display)
            self.AddButton(base + 1, c4d.BFH_SCALEFIT, 20, 16, name="O")
            self.GroupEnd()

        if len(objs) > 100:
            self.AddStaticText(0, c4d.BFH_SCALEFIT, 0, 0,
                               name=f"（仅显示前 100 个，共 {len(objs)} 个）")
        self.GroupEnd()
        self.LayoutChanged(3001)


# ────────────── Command ──────────────
class MeshSorterCommand(c4d.plugins.CommandData):
    _dlg = None

    def Execute(self, doc):
        # 模式：保存引用 + 检查 IsOpen + dialogid=0
        # （用户确认过 test 版此模式不崩溃）
        if self._dlg is None or not self._dlg.IsOpen():
            self._dlg = MeshSorterDialog()
            self._dlg.Open(c4d.DLG_TYPE_ASYNC, 0, -1, -1, 420, 420)
        else:
            self._dlg.Close()
            self._dlg = None
        return True

    def RestoreLayout(self, sec_ref):
        return True


# ────────────── Registration ──────────────
def main():
    icon = _create_plugin_icon()
    ok = c4d.plugins.RegisterCommandPlugin(
        PLUGIN_ID, PLUGIN_NAME, 0, icon, "按面数/存储大小排列网格体", MeshSorterCommand(),
    )
    if ok:
        print("[MeshFaceSorter] 插件已加载")
    else:
        print("[MeshFaceSorter] 注册失败")

main()
