@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo =======================================================
echo   Canteen Hub - Online Ordering & Reservation System
echo =======================================================
echo.

REM Determine the available Python command (py or python)
set "PYCMD="
where py >nul 2>nul
if %errorlevel% equ 0 (
    set "PYCMD=py"
) else (
    where python >nul 2>nul
    if %errorlevel% equ 0 (
        set "PYCMD=python"
    )
)

if "%PYCMD%"=="" (
    echo [ERROR] Python was not found on your system!
    echo Please install Python 3.10+ from https://www.python.org/downloads/
    echo Make sure to check "Add python.exe to PATH" during installation.
    pause
    exit /b 1
)

REM Create virtual environment if it doesn't exist
if not exist "venv\Scripts\activate.bat" (
    echo Creating virtual environment with %PYCMD%...
    %PYCMD% -m venv venv
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
)

echo Activating virtual environment...
call venv\Scripts\activate.bat

echo Checking and installing dependencies...
python -m pip install -r requirements.txt --quiet

echo.
echo =======================================================
echo   Launching server at http://localhost:5000
echo   Admin Login: admin@canteen.com (password: admin123)
echo   Student Login: student@canteen.com (password: student123)
echo   Keep this window open while using the app.
echo   Press CTRL+C or close this window to stop.
echo =======================================================
echo.

REM Open browser after 2 seconds
start "" cmd /c "timeout /t 2 >nul && start http://localhost:5000"

python app.py

pause
