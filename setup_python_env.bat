@echo off
setlocal
cd /d "%~dp0"

echo Creating a local Python environment for this project...

set "_SETUP_TMP=%CD%\.setup_tmp"
if not exist "%_SETUP_TMP%" mkdir "%_SETUP_TMP%"
set "TEMP=%_SETUP_TMP%"
set "TMP=%_SETUP_TMP%"

if exist ".venv" (
    echo Removing existing .venv copied from another machine...
    rmdir /s /q ".venv"
)

where py >nul 2>nul
if %errorlevel%==0 (
    py -3 -m venv ".venv"
) else (
    python -m venv ".venv"
)

if errorlevel 1 (
    echo Failed to create .venv. Install Python or check your PATH.
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo Failed to create .venv. Install Python or check your PATH.
    exit /b 1
)

".venv\Scripts\python.exe" -m ensurepip --upgrade
if errorlevel 1 (
    echo Failed to install pip inside .venv.
    exit /b 1
)

".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 (
    echo Failed to upgrade pip inside .venv.
    exit /b 1
)

if exist "requirements.txt" (
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
) else (
    echo No requirements.txt found. Skipping dependency install.
)

echo.
echo Done. Activate with:
echo .\.venv\Scripts\activate
echo.
echo Or run Python with:
echo .\.venv\Scripts\python.exe
if exist "%_SETUP_TMP%" rmdir /s /q "%_SETUP_TMP%"
endlocal
