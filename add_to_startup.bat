@echo off
cd /d "%~dp0"
where python >nul 2>nul
if %errorlevel% equ 0 python add_to_startup.py && goto :ok
where py >nul 2>nul
if %errorlevel% equ 0 py add_to_startup.py && goto :ok
echo [ERROR] Python not found. Run install.bat first.
pause
exit /b 1
:ok
echo PopNotification will auto-start on next boot.
pause