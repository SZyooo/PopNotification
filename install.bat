@echo off
title PopNotification Setup
cd /d "%~dp0"

set OFFLINE_DIR=offline_packages
set HAS_OFFLINE=0
if exist "%OFFLINE_DIR%\*.whl" set HAS_OFFLINE=1

echo ============================================
echo   PopNotification - Environment Setup
echo ============================================
echo.

if %HAS_OFFLINE% equ 1 echo [MODE] Offline packages detected, will try offline first.
if %HAS_OFFLINE% equ 0 echo [MODE] Online mode (no offline packages found).
echo.

where python >nul 2>nul
if %errorlevel% equ 0 goto python_found

echo [INFO] Python not found, attempting install...

reg Query "HKLM\Hardware\Description\System\CentralProcessor\0" | find /i "x86" >nul
if %errorlevel% equ 0 set PYTHON_SUFFIX=
if %errorlevel% equ 1 set PYTHON_SUFFIX=-amd64
set PYTHON_LABEL=win32
if "%PYTHON_SUFFIX%"=="-amd64" set PYTHON_LABEL=amd64
set PYTHON_VERSION=3.8.10

if %HAS_OFFLINE% equ 1 (
    if exist "%OFFLINE_DIR%\python-%PYTHON_VERSION%%PYTHON_SUFFIX%.exe" (
        echo Installing Python from local file...
        start /wait "" "%OFFLINE_DIR%\python-%PYTHON_VERSION%%PYTHON_SUFFIX%.exe" /quiet InstallAllUsers=0 PrependPath=1 Include_test=0 Shortcuts=0
        if %errorlevel% equ 0 goto refresh_path
        echo [WARN] Offline Python install failed, trying online...
    ) else (
        echo [WARN] Python installer not found in %OFFLINE_DIR%/, trying online...
    )
)

set DOWNLOAD_DIR=%TEMP%\pop_install
set INSTALLER_PATH=%DOWNLOAD_DIR%\python-%PYTHON_VERSION%%PYTHON_SUFFIX%.exe
if not exist "%DOWNLOAD_DIR%" mkdir "%DOWNLOAD_DIR%"
set PYTHON_URL=https://www.python.org/ftp/python/%PYTHON_VERSION%/python-%PYTHON_VERSION%%PYTHON_SUFFIX%.exe
echo Downloading Python %PYTHON_VERSION% (%PYTHON_LABEL%)...
powershell -NoProfile -Command "try { $wc=New-Object System.Net.WebClient; Write-Host 'Downloading...'; $wc.DownloadFile('%PYTHON_URL%', '%INSTALLER_PATH%'); Write-Host 'OK' } catch { Write-Host 'FAILED: ' + $_.Exception.Message; exit 1 }"
if %errorlevel% neq 0 (
    echo [ERROR] Download failed.
    echo Please manually install Python from https://www.python.org/downloads/
    pause
    exit /b 1
)
echo Installing Python (please wait)...
start /wait "" "%INSTALLER_PATH%" /quiet InstallAllUsers=0 PrependPath=1 Include_test=0 Shortcuts=0
if %errorlevel% neq 0 (
    echo [ERROR] Python installer failed (code: %errorlevel%)
    pause
    exit /b 1
)
echo Python installed successfully.

:refresh_path
set PATH=%LOCALAPPDATA%\Programs\Python\Python38\;%PATH%
set PATH=%LOCALAPPDATA%\Programs\Python\Python38\Scripts\;%PATH%

where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [WARN] Python not found in PATH. Trying common locations...
    if exist "%LOCALAPPDATA%\Programs\Python\Python38\python.exe" set PATH=%LOCALAPPDATA%\Programs\Python\Python38\;%PATH%
    if exist "%LOCALAPPDATA%\Programs\Python\Python38-32\python.exe" set PATH=%LOCALAPPDATA%\Programs\Python\Python38-32\;%PATH%
    where python >nul 2>nul
    if %errorlevel% neq 0 (
        echo [ERROR] Python installed but not found. Try rebooting.
        pause
        exit /b 1
    )
)

:python_found
echo [OK] Python ready
python --version
echo.

python -m pip --version >nul 2>nul
if %errorlevel% neq 0 (
    echo pip not found, installing...
    if exist "%OFFLINE_DIR%\get-pip.py" (
        python "%OFFLINE_DIR%\get-pip.py" --no-index --find-links="%OFFLINE_DIR%"
    ) else (
        python -m ensurepip --upgrade
    )
)
echo [OK] pip ready
echo.

echo Installing dependencies...
if %HAS_OFFLINE% equ 1 (
    python -m pip install --no-index --find-links="%OFFLINE_DIR%" -r requirements.txt
    if %errorlevel% neq 0 (
        echo [WARN] Offline dependency install failed, trying online...
        python -m pip install --upgrade pip -q
        python -m pip install -r requirements.txt
    )
)
if %HAS_OFFLINE% equ 0 (
    python -m pip install --upgrade pip -q
    python -m pip install -r requirements.txt
)
if %errorlevel% neq 0 (
    echo [ERROR] Dependency installation failed.
    pause
    exit /b 1
)

echo.
echo ============================================
echo   Setup Complete!
echo.
echo   Run: launch.bat  (with console window)
echo   Or:  launch.vbs  (silent, no window)
echo.
echo   For auto-start: run add_to_startup.bat
echo ============================================
echo.
pause