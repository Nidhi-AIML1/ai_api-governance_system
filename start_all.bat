@echo off
title Governance Engine launcher
cd /d "%~dp0"

echo.
echo  Starting Governance Engine (backend + frontend)...
echo  Close the two new windows to stop everything.
echo.

start "Backend - port 8000" cmd /k run_backend.bat
start "Frontend - port 5173" cmd /k "cd /d %~dp0frontend && (if not exist node_modules npm install) && npm run dev -- --port 5173 --strictPort"

echo  Waiting for the servers to start (15 seconds)...
timeout /t 15 /nobreak >nul
start http://localhost:5173

echo.
echo  Dashboard : http://localhost:5173
echo  API docs  : http://127.0.0.1:8000/docs
echo.
echo  If the page is blank, wait a few seconds and press Ctrl+F5.
echo  If a window shows "port already in use", close your old terminals and run this again.
pause