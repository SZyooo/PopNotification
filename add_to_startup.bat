@echo off
chcp 65001 >nul
title PopNotification - 添加开机自启
cd /d "%~dp0"

python add_to_startup.py

if %errorlevel% equ 0 (
    echo.
    echo   下次开机时将自动启动 PopNotification。
) else (
    echo.
    echo [错误] 请确认已运行 install.bat 安装 Python 环境。
)

echo.
pause
