# C 盘清理助手 (Disk Cleaner)

PyQt5 编写的 Windows 磁盘清理辅助工具，三个功能：

1. **安全清理**：一键扫描并清理常见垃圾（Temp、Update 缓存、浏览器缓存、缩略图、Prefetch、崩溃转储等）
2. **大文件扫描**：扫描指定目录下大于 N MB 的文件，定位/删除
3. **已装软件**：列出全部已安装软件、版本、大小、安装目录，可一键调用卸载程序

## 运行

```powershell
pip install -r requirements.txt
python main.py
```

建议右键以管理员身份运行 PowerShell，否则 `Windows\Temp` 等系统目录的部分文件会清不掉。

## 打包成 exe

双击 `build_exe.bat`，或：

```powershell
pip install pyinstaller
pyinstaller --noconfirm --onefile --windowed --name DiskCleaner --uac-admin main.py
```

完成后可执行文件位于 `dist\DiskCleaner.exe`，启动时会自动请求管理员权限。

## 安全说明

- 默认勾选项均为公认安全的清理路径
- `Windows.old` 等标记为"谨慎"的项目默认不勾选
- 软件卸载只是调用各软件自己的 `UninstallString`，不会强删
- 大文件删除前有二次确认，删除后不进回收站，请慎重
