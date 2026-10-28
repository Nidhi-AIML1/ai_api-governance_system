@echo off
setlocal EnableExtensions EnableDelayedExpansion
title Governance Engine launcher
cd /d "%~dp0" || goto :fail

if not exist "run_backend.bat" (
    echo ERROR: run_backend.bat was not found in "%~dp0".
    goto :fail
)
if not exist "run_frontend.bat" (
    echo ERROR: run_frontend.bat was not found in "%~dp0".
    goto :fail
)

echo Starting Governance Engine...
start "Backend - port 8000" /D "%~dp0" "%~dp0run_backend.bat"
if errorlevel 1 (
    echo ERROR: Could not start the backend window.
    goto :fail
)
start "Frontend - port 5173" /D "%~dp0" "%~dp0run_frontend.bat"
if errorlevel 1 (
    echo ERROR: Could not start the frontend window.
    goto :fail
)

echo Waiting for the frontend to respond...
set "FRONTEND_READY=0"
for /L %%i in (1,1,45) do (
    curl.exe --silent --fail http://127.0.0.1:5173/ >nul 2>&1
    if !errorlevel! equ 0 (
        set "FRONTEND_READY=1"
        goto :frontend_check_done
    )
    timeout /t 1 /nobreak >nul
)

:frontend_check_done
echo.
if "!FRONTEND_READY!"=="1" (
    echo Frontend is responding at http://127.0.0.1:5173
    start "" "http://127.0.0.1:5173"
) else (
    echo Frontend did not respond within 45 seconds.
    echo Check the Frontend window for the error message.
)
echo Backend API docs: http://127.0.0.1:8000/docs
echo Keep both server windows open while using the app.
pause
exit /b 0

:fail
echo.
echo Startup could not continue. Fix the error above and run this file again.
pause
exit /b 1
