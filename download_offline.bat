@echo off
title BubbleMind - Download Offline Packages
cd /d "%~dp0"

set OFFLINE_DIR=offline_packages
if not exist "%OFFLINE_DIR%" mkdir "%OFFLINE_DIR%"

echo ============================================
echo   BubbleMind - Offline Package Download
echo ============================================
echo.
echo This will download all files needed for offline install.
echo You need internet access on THIS computer.
echo Then copy the offline_packages folder to the target PC.
echo.

:: --- Step 1: Download Python installer ---
echo [1/3] Downloading Python installer...
reg Query "HKLM\Hardware\Description\System\CentralProcessor\0" | find /i "x86" >nul
if %errorlevel% equ 0 (set PYTHON_SUFFIX=) else (set PYTHON_SUFFIX=-amd64)
set PYTHON_VERSION=3.8.10
set INSTALLER=python-%PYTHON_VERSION%%PYTHON_SUFFIX%.exe
set PYTHON_URL=https://www.python.org/ftp/python/%PYTHON_VERSION%/%INSTALLER%
if "%PYTHON_SUFFIX%"=="-amd64" (set PYTHON_LABEL=amd64) else (set PYTHON_LABEL=win32)

if exist "%OFFLINE_DIR%\%INSTALLER%" (
    echo [SKIP] %INSTALLER% already exists.
) else (
    echo Downloading...
    powershell -NoProfile -Command "try { $wc=New-Object System.Net.WebClient; Write-Host 'Downloading Python %PYTHON_VERSION% (%PYTHON_LABEL%)...'; $wc.DownloadFile('%PYTHON_URL%', '%OFFLINE_DIR%\%INSTALLER%'); Write-Host 'OK' } catch { Write-Host 'FAILED: ' + $_.Exception.Message; exit 1 }"
)
if %errorlevel% neq 0 (
    echo [ERROR] Python download failed.
    echo You can manually download from %PYTHON_URL%
    echo and place it in %OFFLINE_DIR%/
    pause
    exit /b 1
)
echo [OK] Python installer ready.

:: --- Step 2: Download pip packages for Python 3.8 ---
echo.
echo [2/3] Downloading pip packages for Python 3.8...
if "%PYTHON_SUFFIX%"=="-amd64" (
    python -m pip download --python-version 3.8 --only-binary=:all: --platform win_amd64 -r requirements.txt -d "%OFFLINE_DIR%"
) else (
    python -m pip download --python-version 3.8 --only-binary=:all: --platform win32 -r requirements.txt -d "%OFFLINE_DIR%"
)
if %errorlevel% neq 0 (
    echo [ERROR] pip download failed. Make sure Python and pip are installed.
    pause
    exit /b 1
)
echo [OK] Pip packages downloaded.

:: --- Step 3: Download get-pip.py for offline pip install ---
echo.
echo [3/3] Downloading get-pip.py...
powershell -NoProfile -Command "$wc=New-Object System.Net.WebClient; Write-Host 'Downloading get-pip.py...'; $wc.DownloadFile('https://bootstrap.pypa.io/get-pip.py', '%OFFLINE_DIR%\get-pip.py'); Write-Host 'OK'"

echo.
echo ============================================
echo   All files downloaded to %OFFLINE_DIR%/
echo.
echo   Copy this folder to the target computer, then run:
echo     install.bat
echo ============================================
pause