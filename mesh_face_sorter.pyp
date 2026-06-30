"""C4D Mesh Face Sorter — MVP Version

最小化可运行版本：确保插件能正常打开、显示面板、关闭时不崩溃。
功能逐步添加。

Compatible: C4D 2023+ (2024/2025/2026)
License: MIT
"""

import c4d
from c4d import gui

# ──────────────────────────────────────────────
# Plugin metadata
# ──────────────────────────────────────────────
PLUGIN_ID = 1052328
PLUGIN_NAME = "Mesh Face Sorter"
PLUGIN_HELP = "按面数/存储大小排列网格体（MVP 版本）"


# ──────────────────────────────────────────────
# Dialog — Main UI (Minimal)
# ──────────────────────────────────────────────
class MeshSorterDialog(gui.GeDialog):
    """主面板对话框 — MVP 版本（最小 UI）"""

    def __init__(self):
        super().__init__()

    def CreateLayout(self):
        """构建对话框布局 — MVP: 只显示标题和提示"""
        self.SetTitle("Mesh Face Sorter")

        # 状态提示
        self.AddStaticText(1000, c4d.BFH_SCALEFIT, 0, 0,
                           name="Mesh Face Sorter - MVP",
                           borderstyle=c4d.BORDER_NONE)
        self.AddStaticText(1001, c4d.BFH_SCALEFIT, 0, 0,
                           name="点击「刷新列表」扫描场景",
                           borderstyle=c4d.BORDER_NONE)

        # 刷新按钮
        self.AddButton(2000, c4d.BFH_SCALEFIT, 120, 20, name="刷新列表")

        return True

    def Command(self, gid, msg):
        """处理按钮点击"""
        if gid == 2000:
            # 刷新按钮：扫描场景（MVP 版本，只打印到控制台）
            self._do_refresh()

        return True

    def _do_refresh(self):
        """扫描场景中的网格体（MVP: 只打印到控制台）"""
        doc = c4d.documents.GetActiveDocument()
        if doc is None:
            print("[MeshFaceSorter] 没有活动文档")
            return

        count = 0
        try:
            for obj in doc.GetObjects():
                if obj.IsInstanceOf(c4d.Opolygon):
                    count += 1
        except Exception as e:
            print(f"[MeshFaceSorter] 扫描出错: {e}")
            return

        print(f"[MeshFaceSorter] 扫描完成：{count} 个多边形物体")
        self.SetString(1001, f"扫描完成：{count} 个多边形物体")


# ──────────────────────────────────────────────
# Command — Entry point from menu/toolbar
# ──────────────────────────────────────────────
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


# ──────────────────────────────────────────────
# Plugin registration
# ──────────────────────────────────────────────
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
