@echo off
setlocal
cd /d "%~dp0"

if not exist "%~dp0.venv\Scripts\python.exe" (
    call "%~dp0setup_python_env.bat"
    if errorlevel 1 (
        pause
        exit /b 1
    )
)

set "GUI_SCRIPT="
for /f "usebackq delims=" %%F in (`powershell -NoProfile -ExecutionPolicy Bypass -Command "$latest = Get-ChildItem -LiteralPath '%~dp0' -Filter 'behavior_gui_v*.py' | Where-Object { $_.BaseName -match '^behavior_gui_v\d+$' } | Sort-Object { [int]($_.BaseName -replace '^behavior_gui_v', '') } -Descending | Select-Object -First 1; if ($latest) { $latest.FullName }"`) do set "GUI_SCRIPT=%%F"

if not defined GUI_SCRIPT (
    echo No behavior_gui_v*.py file found in %~dp0
    pause
    exit /b 1
)

echo Launching %GUI_SCRIPT%
"%~dp0.venv\Scripts\python.exe" "%GUI_SCRIPT%"
if errorlevel 1 pause
