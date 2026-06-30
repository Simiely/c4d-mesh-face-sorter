"""C4D Mesh Face Sorter — 极简排查版

逐个增加控件定位布局问题。
Compatible: C4D 2023+
"""

import c4d
from c4d import gui

PLUGIN_ID = 1052328

class MinimalDialog(gui.GeDialog):
    def CreateLayout(self):
        self.SetTitle("Mesh Face Sorter Debug")

        # 控件 1：文本
        self.AddStaticText(1001, c4d.BFH_SCALEFIT, 0, 0,
                               name="Step 1: StaticText",
                               borderstyle=c4d.BORDER_NONE)
        # 控件 2：Group 内的按钮
        self.GroupBegin(1010, c4d.BFH_SCALEFIT, 2, 0, name="")
        self.AddButton(2001, c4d.BFH_SCALEFIT, 100, 20, name="按钮 A")
        self.AddButton(2002, c4d.BFH_SCALEFIT, 100, 20, name="按钮 B")
        self.GroupEnd()

        # 控件 3：根级按钮
        self.AddButton(2003, c4d.BFH_SCALEFIT, 120, 20, name="刷新列表")

        # 控件 4：滚动组
        self.ScrollGroupBegin(3000, c4d.BFH_SCALEFIT | c4d.BFV_SCALEFIT,
                              c4d.SCROLLGROUP_VERT, 380, 100)
        self.AddStaticText(3001, c4d.BFH_SCALEFIT, 0, 0, name="滚动区域内部")
        self.ScrollGroupEnd()

        return True

    def Command(self, gid, msg):
        print(f"[MeshFaceSorter] 点击了控件 {gid}")
        return True

class MinimalCommand(c4d.plugins.CommandData):
    def Execute(self, doc):
        dlg = MinimalDialog()
        dlg.Open(c4d.DLG_TYPE_ASYNC, 0, -1, -1, 420, 300)
        return True

def main():
    c4d.plugins.RegisterCommandPlugin(
        PLUGIN_ID, "MFS Debug", 0, None, "调试版", MinimalCommand(),
    )
    print("[MeshFaceSorter] 调试版已加载")

main()
