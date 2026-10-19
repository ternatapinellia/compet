@echo off
rem ---------------------------------------------------------------------------
rem Re-register the CompetLauncher logon task from CompetLauncher-task-fixed.xml.
rem Needs administrator rights (the task runs at HighestAvailable).
rem
rem What this task definition does
rem   * starts 1 minute after logon, so the graphics/input stack has finished
rem     recovering from hibernate before Compet.exe launches
rem   * first action: CompetLauncher-guard.ps1 cleans up orphan launchers
rem     (a CompetLauncher.exe with no Compet.exe child) left by a failed start
rem   * second action: launches CompetLauncher.exe
rem   * starts on battery and is not stopped when switching to battery
rem   * is not stopped when the machine goes idle
rem   * MultipleInstances=Parallel: a new logon is never blocked by a leftover
rem     instance (the guard action handles the cleanup)
rem
rem Run this once after a fresh Windows install or if the task gets reset.
rem ---------------------------------------------------------------------------
setlocal
set "XML=%~dp0CompetLauncher-task-fixed.xml"
set "GUARD=%~dp0CompetLauncher-guard.ps1"

if not exist "%XML%" (
    echo MISSING: %XML%
    pause
    exit /b 1
)
if not exist "%GUARD%" (
    echo MISSING: %GUARD%
    pause
    exit /b 1
)

net session >nul 2>&1
if errorlevel 1 (
    echo Requesting administrator rights...
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

echo Re-registering task CompetLauncher ...
schtasks /Create /TN "CompetLauncher" /XML "%XML%" /F
if errorlevel 1 (
    echo FAILED to register the task.
    pause
    exit /b 1
)

echo.
echo Done. Current settings:
schtasks /Query /TN "CompetLauncher" /XML | findstr /i "Batteries MultipleInstances StartWhenAvailable StopOnIdleEnd Delay guard"
echo.
pause
