import c4d
PLUGIN_ID = 1052328

class Dlg(c4d.gui.GeDialog):
    def CreateLayout(self):
        self.SetTitle("MFS Test")
        self.AddStaticText(1001, c4d.BFH_SCALEFIT, 0, 0, name="如果看到这一行，插件基础功能正常")
        self.AddButton(2001, c4d.BFH_SCALEFIT, 100, 20, name="测试按钮")
        print("[MFS_Dlg] CreateLayout 执行完毕")
        return True

    def Command(self, gid, msg):
        print(f"[MFS_Dlg] 点击了按钮 {gid}")
        return True

class Cmd(c4d.plugins.CommandData):
    _dlg = None  # 保持引用，防止垃圾回收

    def Execute(self, doc):
        if self._dlg is None or not self._dlg.IsOpen():
            print("[MFS_Cmd] 创建新对话框")
            self._dlg = Dlg()
            self._dlg.Open(c4d.DLG_TYPE_ASYNC, 0, -1, -1, 300, 150)
        else:
            print("[MFS_Cmd] 关闭对话框")
            self._dlg.Close()
            self._dlg = None
        return True

def main():
    print("[MFS_main] 开始注册插件...")
    ok = c4d.plugins.RegisterCommandPlugin(PLUGIN_ID, "Mesh Face Sorter", 0, None, "", Cmd())
    if ok:
        print("[MFS_main] 注册成功")
    else:
        print("[MFS_main] 注册失败")

main()
