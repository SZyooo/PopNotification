@echo off
chcp 65001 >nul
title PopNotification 安装程序
cd /d "%~dp0"

echo ============================================
echo   PopNotification - 环境安装脚本
echo ============================================
echo.

:: --- 检查 Python ---
where python >nul 2>nul
if %errorlevel% equ 0 goto :python_found

echo [INFO] 未找到系统 Python，尝试下载安装...
echo.

:: 检测系统架构
reg Query "HKLM\Hardware\Description\System\CentralProcessor\0" | find /i "x86" >nul
if %errorlevel% equ 0 (set ARCH=x86) else (set ARCH=x64)

set PYTHON_VERSION=3.12.9
set INSTALLER=python-%PYTHON_VERSION%-%ARCH%.exe
set PYTHON_URL=https://www.python.org/ftp/python/%PYTHON_VERSION%/%INSTALLER%
set DOWNLOAD_DIR=%TEMP%\pop_install
set INSTALLER_PATH=%DOWNLOAD_DIR%\%INSTALLER%

if not exist "%DOWNLOAD_DIR%" mkdir "%DOWNLOAD_DIR%"

echo 正在下载 Python %PYTHON_VERSION% (%ARCH%)...
echo 下载地址: %PYTHON_URL%
echo 保存到: %INSTALLER_PATH%
echo.

:: 用 PowerShell 下载
powershell -Command "try { $wc = New-Object System.Net.WebClient; Write-Host '开始下载...'; $wc.DownloadFile('%PYTHON_URL%', '%INSTALLER_PATH%'); Write-Host '下载完成' } catch { Write-Host '下载失败: ' + $_.Exception.Message; exit 1 }"
if %errorlevel% neq 0 (
    echo.
    echo [错误] Python 下载失败！
    echo 请手动访问 https://www.python.org/downloads/ 安装 Python 后重试。
    echo.
    pause
    exit /b 1
)

echo.
echo 正在安装 Python (请勿关闭窗口)...
start /wait "" "%INSTALLER_PATH%" /quiet InstallAllUsers=0 PrependPath=1 Include_test=0 Shortcuts=0
if %errorlevel% neq 0 (
    echo [错误] Python 安装失败 (错误码: %errorlevel%)
    echo 可以尝试右键以管理员身份运行本脚本。
    pause
    exit /b 1
)
echo Python 安装成功！
echo.
echo 正在更新环境变量...
for /f "tokens=3*" %%i in ('reg query "HKCU\Environment" /v Path 2^>nul') do set "USER_PATH=%%i"
if defined USER_PATH set "PATH=%USER_PATH%;%PATH%"

:python_found
echo [OK] Python 已就绪
python --version

:: --- 检查/升级 pip ---
echo.
echo 正在检查 pip...
python -m pip --version >nul 2>nul
if %errorlevel% neq 0 (
    echo pip 未安装，正在安装...
    python -m ensurepip --upgrade
)
echo [OK] pip 已就绪

:: --- 安装依赖 ---
echo.
echo 正在安装项目依赖 (pystray, Pillow)...
echo.
python -m pip install --upgrade pip -q
python -m pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo.
    echo [错误] 依赖安装失败！
    pause
    exit /b 1
)

echo.
echo ============================================
echo   ✓ 安装完成！
echo.
echo   运行方式:
echo     启动.bat    — 后台运行（有控制台窗口）
echo     启动.vbs    — 静默后台运行（无窗口）
echo.
echo   如需添加开机自启，请运行:
echo     add_to_startup.bat
echo ============================================
echo.
pause
