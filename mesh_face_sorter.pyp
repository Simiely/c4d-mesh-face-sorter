"""C4D Mesh Face Sorter
Compatible: C4D 2023+ (2024/2025/2026)
License: MIT
"""
import c4d
import datetime
from c4d import gui, bitmaps

PLUGIN_ID = 1052328
PLUGIN_NAME = "Mesh Face Sorter"
PLUGIN_VERSION = "v2.0.6"

# ────────────── UI 控件 ID ──────────────
ID_STAT_INFO1 = 1001
ID_STAT_INFO2 = 1002
ID_GROUP_OP = 1010
ID_SORT_COMBO = 1011
ID_SORT_TOGGLE = 1012
ID_REFRESH = 1013
ID_GROUP_BTN = 1020
ID_SHOW_ALL = 1021
ID_EXPORT = 1022
ID_DELETE_EMPTY = 1023
ID_LIST_SCROLL = 3000
ID_LIST_GROUP = 3001
ID_ROW_BASE = 4000
ID_ROW_STEP = 2


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


# ────────────── 场景工具（纯函数，不依赖对话框） ──────────────

def collect_all_objects(doc):
    """深度优先收集文档中所有对象（含子级）。"""
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


def collect_polygons(doc):
    """收集所有多边形网格物体，返回 [{obj, name, faces, size}]。"""
    items = []
    for obj in collect_all_objects(doc):
        if obj.IsInstanceOf(c4d.Opolygon):
            items.append({
                "obj": obj,
                "name": obj.GetName(),
                "faces": obj.GetPolygonCount(),
                "size": obj.GetPointCount() * 24 + obj.GetPolygonCount() * 16,
            })
    return items


def fmt_num(n):
    if n >= 1000000:
        return f"{n / 1000000:.1f}M"
    if n >= 1000:
        return f"{n / 1000:.1f}K"
    return str(n)


def fmt_size(n):
    if n >= 1048576:
        return f"{n / 1048576:.1f}MB"
    if n >= 1024:
        return f"{n / 1024:.1f}KB"
    return f"{n}B"


def set_visible(obj, mode):
    """统一设置编辑器显示模式，并清除历史遗留的『忽略绘制』位。"""
    obj.SetEditorMode(mode)
    obj.DelBit(c4d.BIT_IGNOREDRAW)


def show_all(doc):
    """无条件恢复所有对象为默认可见（MODE_UNDEF = 跟随父级）。返回恢复数量。"""
    doc.StartUndo()
    count = 0
    for obj in collect_all_objects(doc):
        doc.AddUndo(c4d.UNDOTYPE_CHANGE_SMALL, obj)
        set_visible(obj, c4d.MODE_UNDEF)
        count += 1
    doc.EndUndo()
    c4d.EventAdd()
    return count


def isolate(doc, target):
    """孤立目标：目标强制显示（MODE_ON），其余隐藏（MODE_OFF）。"""
    doc.StartUndo()
    for obj in collect_all_objects(doc):
        doc.AddUndo(c4d.UNDOTYPE_CHANGE_SMALL, obj)
        if obj == target:
            set_visible(obj, c4d.MODE_ON)
        else:
            set_visible(obj, c4d.MODE_OFF)
    doc.AddUndo(c4d.UNDOTYPE_CHANGE_SMALL, target)
    target.SetBit(c4d.BIT_ACTIVE)
    doc.SetActiveObject(target)
    doc.EndUndo()
    c4d.EventAdd()


def select_only(doc, target):
    """仅选中目标，取消其余对象选中。"""
    doc.StartUndo()
    for obj in collect_all_objects(doc):
        doc.AddUndo(c4d.UNDOTYPE_CHANGE_SMALL, obj)
        obj.DelBit(c4d.BIT_ACTIVE)
    doc.AddUndo(c4d.UNDOTYPE_CHANGE_SMALL, target)
    target.SetBit(c4d.BIT_ACTIVE)
    doc.SetActiveObject(target)
    doc.EndUndo()
    c4d.EventAdd()


def find_empty_polygons(doc):
    """返回面数为 0 且无子级的多边形物体列表。"""
    return [obj for obj in collect_all_objects(doc)
            if obj.GetDown() is None
            and obj.IsInstanceOf(c4d.Opolygon)
            and obj.GetPolygonCount() == 0]


def delete_objects(doc, objs):
    doc.StartUndo()
    for obj in objs:
        doc.AddUndo(c4d.UNDOTYPE_DELETE, obj)
        obj.Remove()
    doc.EndUndo()
    c4d.EventAdd()


def export_report(path, items, sort_by, descending):
    """导出 Markdown 报表。items 需已按目标排序。"""
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    sort_label = "面数" if sort_by == "faces" else "存储大小"
    order_label = "降序" if descending else "升序"
    lines = ["# 网格体报表", "",
             f"- **生成时间**：{now}",
             f"- **排序方式**：{sort_label}（{order_label}）",
             f"- **网格体总数**：{len(items)}",
             f"- **总面数**：{sum(i['faces'] for i in items)}",
             f"- **总存储**：{fmt_size(sum(i['size'] for i in items))}",
             "", "| # | 物体名称 | 面数 | 存储 |",
             "|---|---|---|---|"]
    for i, item in enumerate(items, 1):
        lines.append(f"| {i} | {item['name']} | {item['faces']} | {fmt_size(item['size'])} |")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


# ────────────── 对话框 ──────────────

class MeshSorterDialog(gui.GeDialog):
    def __init__(self):
        super().__init__()
        self._items = []      # 全部多边形（未排序）
        self._sorted = []     # 当前排序后的列表，用于行点击索引
        self._scanned = False  # 是否已执行过扫描
        self.sort_by = "faces"
        self.descending = True

    def CreateLayout(self):
        self.SetTitle("Mesh Face Sorter")
        self.AddStaticText(ID_STAT_INFO1, c4d.BFH_SCALEFIT, 0, 0,
                           name="点击「刷新」扫描场景", borderstyle=c4d.BORDER_NONE)
        self.AddStaticText(ID_STAT_INFO2, c4d.BFH_SCALEFIT, 0, 0,
                           name="", borderstyle=c4d.BORDER_NONE)
        # 操作区
        self.GroupBegin(ID_GROUP_OP, c4d.BFH_SCALEFIT, 3, 0, "操作：")
        self.AddComboBox(ID_SORT_COMBO, c4d.BFH_SCALEFIT, 120, 12)
        self.AddChild(ID_SORT_COMBO, 0, "面数")
        self.AddChild(ID_SORT_COMBO, 1, "存储大小")
        self.SetInt32(ID_SORT_COMBO, 0)
        self.AddButton(ID_SORT_TOGGLE, c4d.BFH_SCALEFIT, 30, 20, name="↓↑")
        self.AddButton(ID_REFRESH, c4d.BFH_SCALEFIT, 120, 20, name="刷新")
        self.GroupEnd()
        # 按钮区
        self.GroupBegin(ID_GROUP_BTN, c4d.BFH_SCALEFIT, 3, 0, "")
        self.AddButton(ID_SHOW_ALL, c4d.BFH_SCALEFIT, 120, 20, name="显示全部")
        self.AddButton(ID_EXPORT, c4d.BFH_SCALEFIT, 120, 20, name="导出报表")
        self.AddButton(ID_DELETE_EMPTY, c4d.BFH_SCALEFIT, 120, 20, name="删除空物体")
        self.GroupEnd()
        # 列表区
        self.ScrollGroupBegin(ID_LIST_SCROLL, c4d.BFH_SCALEFIT | c4d.BFV_SCALEFIT,
                              c4d.SCROLLGROUP_VERT, 380, 200)
        self.GroupBegin(ID_LIST_GROUP, c4d.BFH_SCALEFIT | c4d.BFV_SCALEFIT, 1, 0)
        self.AddStaticText(0, c4d.BFH_SCALEFIT, 0, 0, name="（点击「刷新」开始扫描）")
        self.GroupEnd()
        self.GroupEnd()
        return True

    def Command(self, gid, msg):
        if gid == ID_SORT_COMBO:
            self.sort_by = "faces" if self.GetInt32(ID_SORT_COMBO) == 0 else "size"
            self._refresh_list()
        elif gid == ID_SORT_TOGGLE:
            self.descending = not self.descending
            self.SetString(ID_SORT_TOGGLE, "↓" if self.descending else "↑")
            self._refresh_list()
        elif gid == ID_REFRESH:
            self._do_refresh()
        elif gid == ID_SHOW_ALL:
            self._do_show_all()
        elif gid == ID_EXPORT:
            self._do_export()
        elif gid == ID_DELETE_EMPTY:
            self._do_delete_empty()
        elif gid >= ID_ROW_BASE:
            self._handle_row(gid)
        return True

    # ── 动作 ──
    def _do_refresh(self):
        doc = c4d.documents.GetActiveDocument()
        if doc is None:
            return
        self._items = collect_polygons(doc)
        self._scanned = True
        total_faces = sum(i["faces"] for i in self._items)
        total_size = sum(i["size"] for i in self._items)
        self.SetString(ID_STAT_INFO1, f"扫描完成：{len(self._items)} 个物体")
        self.SetString(ID_STAT_INFO2,
                       f"网格体：{len(self._items)}    总面数：{fmt_num(total_faces)}    总存储：{fmt_size(total_size)}")
        self._refresh_list()

    def _do_show_all(self):
        doc = c4d.documents.GetActiveDocument()
        if doc is None:
            return
        count = show_all(doc)
        if count > 0:
            gui.MessageDialog(f"已恢复 {count} 个物体的显示。")
        self._do_refresh()

    def _do_export(self):
        if not self._scanned:
            gui.MessageDialog("请先点击「刷新」扫描场景。")
            return
        if not self._items:
            gui.MessageDialog("场景中没有多边形物体。")
            return
        path = c4d.storage.SaveDialog(c4d.FILESELECTTYPE_ANYTHING,
                                      "导出 MD 报表", ".md", "", "mesh_report.md")
        if not path:
            return
        if not path.lower().endswith(".md"):
            path += ".md"
        try:
            export_report(path, self._sorted, self.sort_by, self.descending)
            gui.MessageDialog(f"已导出 {len(self._sorted)} 个物体到：\n{path}")
        except Exception as e:
            gui.MessageDialog(f"导出失败：{e}")

    def _do_delete_empty(self):
        doc = c4d.documents.GetActiveDocument()
        if doc is None:
            return
        empty = find_empty_polygons(doc)
        if not empty:
            gui.MessageDialog("没有可删除的空物体。")
            return
        if not gui.QuestionDialog(f"找到 {len(empty)} 个面数为 0 的空物体，确定删除？"):
            return
        delete_objects(doc, empty)
        gui.MessageDialog(f"已删除 {len(empty)} 个空物体。")
        self._do_refresh()

    def _handle_row(self, gid):
        idx = gid - ID_ROW_BASE
        action = idx % ID_ROW_STEP  # 0=选中, 1=孤立
        row = idx // ID_ROW_STEP
        if row >= len(self._sorted):
            return
        item = self._sorted[row]
        obj = item["obj"]
        if not obj or not obj.IsAlive():  # 对象在刷新后已被删除
            return
        doc = c4d.documents.GetActiveDocument()
        if doc is None:
            return
        if action == 0:
            select_only(doc, obj)
            self._refresh_list()
        else:
            isolate(doc, obj)
            self._do_refresh()

    def _refresh_list(self):
        key = "faces" if self.sort_by == "faces" else "size"
        self._sorted = sorted(self._items, key=lambda x: x[key], reverse=self.descending)
        self.LayoutFlushGroup(ID_LIST_GROUP)
        self.GroupBegin(ID_LIST_GROUP, c4d.BFH_SCALEFIT | c4d.BFV_SCALEFIT, 1, 0)
        sort_label = "面数" if self.sort_by == "faces" else "存储"
        self.AddStaticText(0, c4d.BFH_SCALEFIT, 0, 0,
                           name=f"  物体名称                    {sort_label}*   O",
                           borderstyle=c4d.BORDER_THIN_IN)
        for i, item in enumerate(self._sorted[:100]):
            base = ID_ROW_BASE + i * ID_ROW_STEP
            obj = item["obj"]
            is_sel = obj is not None and obj.IsAlive() and obj.GetBit(c4d.BIT_ACTIVE)
            prefix = "▶ " if is_sel else "  "
            name = item["name"]
            if len(name) > 20:
                name = name[:18] + ".."
            val = item["faces"] if self.sort_by == "faces" else item["size"]
            val_str = fmt_num(val) if self.sort_by == "faces" else fmt_size(val)
            display = f"{prefix}{name:<20} {val_str:>6}"
            self.GroupBegin(base, c4d.BFH_SCALEFIT, 2, 0, "")
            self.AddButton(base, c4d.BFH_SCALEFIT, 290, 16, name=display)
            self.AddButton(base + 1, c4d.BFH_SCALEFIT, 20, 16, name="O")
            self.GroupEnd()
        if len(self._sorted) > 100:
            self.AddStaticText(0, c4d.BFH_SCALEFIT, 0, 0,
                               name=f"（仅显示前 100 个，共 {len(self._sorted)} 个）")
        self.GroupEnd()
        self.LayoutChanged(ID_LIST_GROUP)


# ────────────── 插件命令 ──────────────

class MeshSorterCommand(c4d.plugins.CommandData):
    _dlg = None

    def Execute(self, doc):
        if self._dlg is None or not self._dlg.IsOpen():
            self._dlg = MeshSorterDialog()
            self._dlg.Open(c4d.DLG_TYPE_ASYNC, 0, -1, -1, 420, 420)
        else:
            self._dlg.Close()
            self._dlg = None
        return True

    def RestoreLayout(self, sec_ref):
        if self._dlg is not None:
            return self._dlg.Restore(PLUGIN_ID, sec_ref)
        return True


# ────────────── 注册 ──────────────

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
# v2.0.4 重构：移除 _original_modes 状态依赖，显示全部/孤立改为无状态幂等操作
# v2.0.5 加固：dead atom 判断改用 IsAlive()；RestoreLayout 调用 Dialog.Restore() 支持布局恢复
# v2.0.6 走查修复：导出区分「未刷新」与「无物体」提示；空场景显示全部不再弹无意义提示
