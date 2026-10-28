@echo off
setlocal
cd /d "%~dp0backend" || (
    echo ERROR: Could not find the backend directory.
    goto :fail
)

if not exist "venv\Scripts\python.exe" (
    echo Creating the backend virtual environment...
    py -3 -m venv venv
    if errorlevel 1 goto :fail
)

echo Checking backend dependencies...
"venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :fail

echo Starting the backend at http://127.0.0.1:8000
"venv\Scripts\python.exe" -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
if errorlevel 1 goto :fail

exit /b 0

:fail
echo.
echo Backend startup failed. Read the error above before closing this window.
pause
exit /b 1