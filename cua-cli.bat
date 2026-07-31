@echo off
setlocal enabledelayedexpansion
set "action=%~1"
shift
if /I "%action%"=="do" (
    set "cmd=%~1"
    shift
    if /I "%cmd%"=="open_app" (
        set "target=%~1"
        if /I "!target!"=="notepad" (
            start "" notepad
            echo ✅ Opened notepad
            exit /b 0
        )
    )
    if /I "%cmd%"=="close_app" (
        set "target=%~1"
        if /I "!target!"=="notepad" (
            taskkill /im notepad.exe /f >nul 2>&1
            echo ✅ Closed notepad
            exit /b 0
        )
    )
)
echo ❌ Unknown command
exit /b 1