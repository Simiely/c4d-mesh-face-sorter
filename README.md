# C4D Mesh Face Sorter

> Cinema 4D 插件：按面数/顶点数/存储大小排列场景中所有网格体。
> **当前版本：MVP（最小可运行版本）** — 功能逐步添加中。

## 当前状态 (MVP)

✅ 插件能注册到菜单  
✅ 打开面板不崩溃  
✅ 关闭面板不崩溃  
⏳ 扫描场景（刷新按钮当前只打印到控制台）  
⏳ 排序功能  
⏳ 列表显示  
⏳ 减面功能  
⏳ 导出报表  

## 安装

### 方式一：下载 Release

1. 访问 [Releases](https://github.com/Simiely/c4d-mesh-face-sorter/releases)
2. 下载最新版本的 Source code (zip)
3. 解压后得到 `c4d-mesh-face-sorter` 文件夹
4. 将文件夹放入 C4D 插件目录：
   - **Windows:** `C:\Program Files\Maxon Cinema 4D 202X\plugins\`
   - **macOS:** `/Applications/Maxon Cinema 4D 202X/plugins/`
5. 重启 C4D

### 方式二：克隆仓库

```bash
git clone https://github.com/Simiely/c4d-mesh-face-sorter.git
```

将文件夹放入 C4D 插件目录。

## 使用方法（MVP）

1. 打开 C4D
2. 菜单 → **扩展** → **Mesh Face Sorter**
3. 面板打开后，点击「刷新列表」按钮（当前只打印到 C4D 控制台）
4. 关闭面板（不崩溃）

## 开发计划

- [x] MVP — 最小可运行版本（面板能打开/关闭）
- [ ] 功能 1 — 扫描场景并显示结果
- [ ] 功能 2 — 排序（面数/存储大小）
- [ ] 功能 3 — 列表显示（最多 500 个）
- [ ] 功能 4 — 孤立显示、减面 Tag、应用减面
- [ ] 功能 5 — 导出 md 报表

## 兼容性

- Cinema 4D 2023+（兼容 2024/2025/2026）
- Windows / macOS

## License

MIT
