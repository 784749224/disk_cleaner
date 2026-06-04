@echo off
chcp 65001 >nul
cd /d %~dp0
echo === 打包 C 盘清理助手 ===
pip install -r requirements.txt
pyinstaller --noconfirm --onefile --windowed ^
    --name "DiskCleaner" ^
    --uac-admin ^
    main.py
echo.
echo 完成! 可执行文件位于 dist\DiskCleaner.exe
pause
