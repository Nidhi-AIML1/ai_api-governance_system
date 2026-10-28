@echo off
setlocal
cd /d "%~dp0frontend" || goto :fail

where node >nul 2>&1
if errorlevel 1 (
    echo ERROR: Node.js was not found. Install the current Node.js LTS release, then reopen this file.
    goto :fail
)
where npm >nul 2>&1
if errorlevel 1 (
    echo ERROR: npm was not found. Reinstall Node.js with npm included, then reopen this file.
    goto :fail
)

if not exist "node_modules\vite\bin\vite.js" (
    echo Installing frontend dependencies...
    call npm install
    if errorlevel 1 goto :fail
)

echo Starting the frontend at http://127.0.0.1:5173
call npm run dev -- --host 127.0.0.1 --port 5173 --strictPort
if errorlevel 1 goto :fail

exit /b 0

:fail
echo.
echo Frontend startup failed. Read the error above before closing this window.
pause
exit /b 1
