"""C4D Mesh Face Sorter — MVP Version

最小化可运行版本：确保插件能正常打开、显示面板、关闭时不崩溃。
功能逐步添加。

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
PLUGIN_HELP = "按面数/存储大小排列网格体（MVP 版本）"


# ──────────────────────────────────────
# Helper: count faces recursively
# ──────────────────────────────────────
def _count_faces_recursive(obj, max_depth=10):
    """递归计算物体的面数，含缓存（对参数化物体如人形素体也有效）"""
    if obj is None or max_depth <= 0:
        return 0

    total = 0
    try:
        # 如果是多边形物体，直接获取面数
        if obj.IsInstanceOf(c4d.Opolygon):
            total += obj.GetPolygonCount()
        else:
            # 尝试从缓存获取（参数化物体的生成结果）
            cache = obj.GetCache()
            if cache:
                # 递归统计缓存中的面数
                total += _count_faces_recursive(cache, max_depth - 1)
            # 某些物体的多边形在子级中
            child = obj.GetDown()
            while child:
                total += _count_faces_recursive(child, max_depth - 1)
                child = child.GetNext()
    except Exception:
        pass
    return total


# ──────────────────────────────────────
# Dialog — Main UI
# ──────────────────────────────────────
class MeshSorterDialog(gui.GeDialog):
    """主面板对话框 — MVP 版本（最小 UI）"""

    def __init__(self):
        super().__init__()

    def CreateLayout(self):
        """构建对话框布局"""
        self.SetTitle("Mesh Face Sorter")

        # 状态提示
        self.AddStaticText(1000, c4d.BFH_SCALEFIT, 0, 0,
                               name="Mesh Face Sorter",
                               borderstyle=c4d.BORDER_NONE)
        self.AddStaticText(1001, c4d.BFH_SCALEFIT, 0, 0,
                               name="点击「刷新列表」扫描场景",
                               borderstyle=c4d.BORDER_NONE)

        # 刷新按钮
        self.AddButton(2000, c4d.BFH_SCALEFIT, 120, 20, name="刷新列表")

        # 物体列表区域（滚动组）
        self.ScrollGroupBegin(3000, c4d.BFH_SCALEFIT | c4d.BFV_SCALEFIT, 380, 200)
        self._list_group = 3001
        self.GroupBegin(self._list_group, c4d.BFH_SCALEFIT | c4d.BFV_SCALEFIT, 1, 1)
        self.GroupEnd()
        self.ScrollGroupEnd()

        return True

    def Command(self, gid, msg):
        """处理按钮点击"""
        if gid == 2000:
            self._do_refresh()

        return True

    def _do_refresh(self):
        """扫描场景中的所有物体（递归遍历所有层级）"""
        doc = c4d.documents.GetActiveDocument()
        if doc is None:
            print("[MeshFaceSorter] 没有活动文档")
            return

        # 递归遍历所有物体（含子级）
        def _collect_all(obj):
            result = []
            stack = [obj]
            while stack:
                current = stack.pop()
                if current is None:
                    continue
                try:
                    # 获取面数：递归检查物体及其缓存的所有多边形
                    faces = _count_faces_recursive(current)

                    result.append({
                        "name": current.GetName(),
                        "type": current.GetType(),
                        "faces": faces,
                    })
                except Exception:
                    pass
                # 添加子级到栈
                child = current.GetDown()
                while child:
                    stack.append(child)
                    child = child.GetNext()
            return result

        all_objects = []
        try:
            for obj in doc.GetObjects():
                all_objects.extend(_collect_all(obj))
        except Exception as e:
            print(f"[MeshFaceSorter] 扫描出错: {e}")
            return

        count = len(all_objects)
        print(f"[MeshFaceSorter] 扫描完成：{count} 个物体")
        for item in all_objects[:50]:  # 打印前 50 个
            faces = item["faces"]
            print(f"[MeshFaceSorter]  {item['name']} (类型: {item['type']}, 面数: {faces})")

        # 在面板里显示结果
        self.SetString(1001, f"扫描完成：{count} 个物体")

        # 显示物体名称 + 面数（最多 50 个）
        self._build_list(all_objects)

    def _build_list(self, objects):
        """在滚动组中显示物体列表"""
        self.LayoutFlushGroup(self._list_group)
        self.GroupBegin(self._list_group, c4d.BFH_SCALEFIT | c4d.BFV_SCALEFIT, 1, 1)

        for i, item in enumerate(objects[:50]):  # 最多显示 50 个
            name = item["name"]
            faces = item["faces"]
            text = f"  {name} ({faces} 面)"
            self.AddStaticText(4000 + i, c4d.BFH_SCALEFIT, 0, 0, name=text)

        self.GroupEnd()
        self.LayoutChanged(self._list_group)


# ──────────────────────────────────────>
# Command — Entry point from menu/toolbar>
# ──────────────────────────────────────>
class MeshSorterCommand(c4d.plugins.CommandData):
    """命令入口：打开 Mesh Face Sorter 面板"""

    dialog = None

    def Execute(self, doc):
        if self.dialog is None or not self.dialog.IsOpen():
            self.dialog = MeshSorterDialog()
            self.dialog.Open(c4d.DLG_TYPE_ASYNC, PLUGIN_ID, -1, -1, 400, 300)
        else:
            self.dialog.Close()
            self.dialog = None
        return True

    def RestoreLayout(self, sec_ref):
        """恢复对话框（C4D 面板停靠恢复时调用）"""
        if self.dialog is None:
            self.dialog = MeshSorterDialog()
        self.dialog.Open(c4d.DLG_TYPE_ASYNC, PLUGIN_ID, -1, -1, 400, 300)
        return True


# ──────────────────────────────────────>
# Plugin registration>
# ──────────────────────────────────────>
def main():
    """插件入口函数（C4D 自动调用）"""
    try:
        result = c4d.plugins.RegisterCommandPlugin(
            PLUGIN_ID,
            PLUGIN_NAME,
            0,
            None,
            PLUGIN_HELP,
            MeshSorterCommand(),
        )

        if result:
            print(f"[MeshFaceSorter] 插件已加载，ID: {PLUGIN_ID}")
        else:
            print(f"[MeshFaceSorter] 注册失败（ID {PLUGIN_ID} 冲突？）")

    except Exception as e:
        print(f"[MeshFaceSorter] 加载异常：{e}")


main()
