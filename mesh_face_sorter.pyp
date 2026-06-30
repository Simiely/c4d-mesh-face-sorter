"""C4D Mesh Face Sorter — MVP 版本 + 排序功能

Compatible: C4D 2023+ (2024/2025/2026)
License: MIT
"""

import c4d
from c4d import gui

# ──────────────────────────────────────
# Plugin metadata
# ──────────────────────────────────────
PLUGIN_ID = 1052328
PLUGIN_NAME = "Mesh Face Sorter"
PLUGIN_HELP = "按面数/存储大小排列网格体"


# ──────────────────────────────────────
# Helper: count faces recursively
# ──────────────────────────────────────
def _count_faces_recursive(obj, max_depth=10):
    """递归计算物体的面数，含缓存（对参数化物体也有效）"""
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


# ──────────────────────────────────────
# Helper: estimate memory size
# ──────────────────────────────────────
def _estimate_size(obj):
    """估算物体的内存占用（字节）"""
    try:
        pts = obj.GetPointCount()
        polys = obj.GetPolygonCount()
        return pts * 24 + polys * 16
    except Exception:
        return 0


# ──────────────────────────────────────
# Helper: format numbers
# ──────────────────────────────────────
def _fmt_num(n):
    if n >= 1000000:
        return f"{n/1000000:.1f}M"
    if n >= 1000:
        return f"{n/1000:.1f}K"
    return str(n)


# ──────────────────────────────────────
# Dialog — Main UI
# ──────────────────────────────────────
class MeshSorterDialog(gui.GeDialog):
    """主面板对话框"""

    # Gadget IDs
    GID_STATUS = 1001
    GID_STAT_COUNT = 1002  # 统计文字
    GID_SORT_COMBO = 1010
    GID_SORT_TOGGLE = 1011
    GID_BTN_REFRESH = 2000
    GID_LIST_SCROLL = 3000
    GID_LIST_GROUP = 3001

    def __init__(self):
        super().__init__()
        self._objects = []          # 扫描结果 [{name, faces, size}]
        self.sort_by = "faces"      # "faces" 或 "size"
        self.descending = True

    def CreateLayout(self):
        """构建对话框布局"""
        self.SetTitle("Mesh Face Sorter")

        # 状态区
        self.AddStaticText(self.GID_STATUS, c4d.BFH_SCALEFIT, 0, 0,
                               name="点击「刷新列表」扫描场景",
                               borderstyle=c4d.BORDER_NONE)
        self.AddStaticText(self.GID_STAT_COUNT, c4d.BFH_SCALEFIT, 0, 0,
                               name="",
                               borderstyle=c4d.BORDER_NONE)

        # 排序区
        self.GroupBegin(1020, c4d.BFH_SCALEFIT, 3, 1, name="排序：")
        self.AddComboBox(self.GID_SORT_COMBO, c4d.BFH_SCALEFIT, 120, 12)
        self.AddChild(self.GID_SORT_COMBO, 0, "面数")
        self.AddChild(self.GID_SORT_COMBO, 1, "存储大小")
        self.SetInt32(self.GID_SORT_COMBO, 0)
        self.AddButton(self.GID_SORT_TOGGLE, c4d.BFH_SCALEFIT, 30, 20, name="↓↑")
        self.GroupEnd()

        # 刷新按钮
        self.AddButton(self.GID_BTN_REFRESH, c4d.BFH_SCALEFIT, 120, 20, name="刷新列表")

        # 物体列表区（滚动组）
        self.ScrollGroupBegin(self.GID_LIST_SCROLL,
                              c4d.BFH_SCALEFIT | c4d.BFV_SCALEFIT, 380, 200)
        self.GroupBegin(self.GID_LIST_GROUP,
                        c4d.BFH_SCALEFIT | c4d.BFV_SCALEFIT, 1, 1)
        self.GroupEnd()
        self.ScrollGroupEnd()

        return True

    def Command(self, gid, msg):
        """处理按钮点击和控件变更"""
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

        return True

    def _do_refresh(self):
        """扫描场景中的所有物体（递归遍历所有层级）"""
        doc = c4d.documents.GetActiveDocument()
        if doc is None:
            print("[MeshFaceSorter] 没有活动文档")
            return

        # 递归遍历所有物体
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
        try:
            for obj in doc.GetObjects():
                all_objects.extend(_scan(obj))
        except Exception as e:
            print(f"[MeshFaceSorter] 扫描出错: {e}")
            return

        self._objects = all_objects
        count = len(all_objects)
        print(f"[MeshFaceSorter] 扫描完成：{count} 个物体")
        for item in all_objects:
            print(f"  {item['name']} (面数: {item['faces']}, 存储: {item['size']}B)")

        # 更新面板
        self.SetString(self.GID_STATUS, f"扫描完成：{count} 个物体")
        total_faces = sum(o["faces"] for o in all_objects)
        self.SetString(self.GID_STAT_COUNT,
                       f"网格体：{count}    总面数：{_fmt_num(total_faces)}")
        self._refresh_list()

    def _refresh_list(self):
        """按当前排序方式重新显示列表"""
        objs = self._objects

        # 排序
        if self.sort_by == "faces":
            objs = sorted(objs, key=lambda x: x["faces"], reverse=self.descending)
        else:
            objs = sorted(objs, key=lambda x: x["size"], reverse=self.descending)

        # 构建列表
        self.LayoutFlushGroup(self.GID_LIST_GROUP)
        self.GroupBegin(self.GID_LIST_GROUP,
                        c4d.BFH_SCALEFIT | c4d.BFV_SCALEFIT, 1, 1)

        # 表头
        sort_label = "面数" if self.sort_by == "faces" else "存储"
        self.AddStaticText(3999, c4d.BFH_SCALEFIT, 0, 0,
                           name=f"  物体名称                         {sort_label}*",
                           borderstyle=c4d.BORDER_THIN_IN)

        # 列表行（最多 500 个）
        for i, item in enumerate(objs[:500]):
            name = item["name"]
            if len(name) > 26:
                name = name[:24] + ".."
            val = item["faces"] if self.sort_by == "faces" else item["size"]
            if self.sort_by == "size":
                val_str = f"{val//1024}KB" if val >= 1024 else f"{val}B"
            else:
                val_str = _fmt_num(val)
            self.AddStaticText(4000 + i, c4d.BFH_SCALEFIT, 0, 0,
                               name=f"  {name:<26} {val_str:>8}")

        if len(objs) > 500:
            self.AddStaticText(0, c4d.BFH_SCALEFIT, 0, 0,
                               name=f"（仅显示前 500 个，共 {len(objs)} 个）")

        self.GroupEnd()
        self.LayoutChanged(self.GID_LIST_GROUP)


# ──────────────────────────────────────
# Command — Entry point from menu/toolbar
# ──────────────────────────────────────
class MeshSorterCommand(c4d.plugins.CommandData):
    """命令入口：打开 Mesh Face Sorter 面板"""

    dialog = None

    def Execute(self, doc):
        if self.dialog is None or not self.dialog.IsOpen():
            self.dialog = MeshSorterDialog()
            self.dialog.Open(c4d.DLG_TYPE_ASYNC, PLUGIN_ID, -1, -1, 420, 350)
        else:
            self.dialog.Close()
            self.dialog = None
        return True

    def RestoreLayout(self, sec_ref):
        if self.dialog is None:
            self.dialog = MeshSorterDialog()
        self.dialog.Open(c4d.DLG_TYPE_ASYNC, PLUGIN_ID, -1, -1, 420, 350)
        return True


# ──────────────────────────────────────
# Plugin registration
# ──────────────────────────────────────
def main():
    try:
        result = c4d.plugins.RegisterCommandPlugin(
            PLUGIN_ID, PLUGIN_NAME, 0, None, PLUGIN_HELP, MeshSorterCommand(),
        )
        if result:
            print(f"[MeshFaceSorter] 插件已加载，ID: {PLUGIN_ID}")
        else:
            print(f"[MeshFaceSorter] 注册失败（ID {PLUGIN_ID} 冲突？）")
    except Exception as e:
        print(f"[MeshFaceSorter] 加载异常：{e}")


main()
