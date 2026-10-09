@echo off
setlocal

set "VENV_DIR=%~dp0.venv"
set "REQUIREMENTS_FILE=%~dp0requirements.txt"

where py >nul 2>nul
if not errorlevel 1 (
    set "PYTHON_CMD=py -3"
) else (
    where python >nul 2>nul
    if not errorlevel 1 (
        set "PYTHON_CMD=python"
    ) else (
        echo ERROR: Python was not found. Install Python 3, then run this file again.
        exit /b 1
    )
)

if not exist "%VENV_DIR%\Scripts\python.exe" (
    echo Creating virtual environment in "%VENV_DIR%" ...
    %PYTHON_CMD% -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo ERROR: Failed to create the virtual environment.
        exit /b 1
    )
)

"%VENV_DIR%\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 (
    echo ERROR: Failed to upgrade pip.
    exit /b 1
)

"%VENV_DIR%\Scripts\python.exe" -m pip install -r "%REQUIREMENTS_FILE%"
if errorlevel 1 (
    echo ERROR: Failed to install requirements.
    exit /b 1
)

"%VENV_DIR%\Scripts\python.exe" -c "import tkinter, numpy, pandas, matplotlib, scipy, tqdm, h5py; print('Dependency check passed.')"
if errorlevel 1 (
    echo ERROR: Dependency check failed. Make sure your Python install includes tkinter.
    exit /b 1
)

echo.
echo Python environment is ready.
echo To start the GUI, run:
echo   "%VENV_DIR%\Scripts\python.exe" "%~dp0behavior_gui_v8.py"
echo.

endlocal
