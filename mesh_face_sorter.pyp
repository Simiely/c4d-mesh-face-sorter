import c4d
PLUGIN_ID = 1052328

class Dlg(c4d.gui.GeDialog):
    def CreateLayout(self):
        self.SetTitle("MFS Test")
        self.AddStaticText(1001, c4d.BFH_SCALEFIT, 0, 0, name="如果看到这一行，插件基础功能正常")
        self.AddButton(2001, c4d.BFH_SCALEFIT, 100, 20, name="测试按钮")
        return True

    def Command(self, gid, msg):
        print(f"点击了按钮 {gid}")
        return True

class Cmd(c4d.plugins.CommandData):
    def Execute(self, doc):
        dlg = Dlg()
        dlg.Open(c4d.DLG_TYPE_ASYNC, 0, -1, -1, 300, 150)
        return True

def main():
    ok = c4d.plugins.RegisterCommandPlugin(PLUGIN_ID, "Mesh Face Sorter", 0, None, "", Cmd())
    if ok:
        print("[MFS] OK")
    else:
        print("[MFS] FAIL")

main()
