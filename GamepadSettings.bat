@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0GamepadSettings.ps1"
if errorlevel 1 echo Gamepad settings failed.
pause
