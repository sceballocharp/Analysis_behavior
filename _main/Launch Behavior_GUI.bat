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
"%~dp0.venv\Scripts\python.exe" "%~dp0behavior_gui_v8.py"
if errorlevel 1 pause
