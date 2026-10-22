@echo off
cd /d "%~dp0"
echo.
echo  Starting with Docker. The first build can take several minutes...
echo  (Stop any old servers on ports 8000 and 5173 first.)
echo.
docker compose up --build -d
if errorlevel 1 (
  echo.
  echo  Docker failed. Is Docker Desktop running?
  pause
  exit /b 1
)
echo.
echo  Dashboard : http://localhost:8080
echo  API docs  : http://localhost:8000/docs
timeout /t 5 /nobreak >nul
start http://localhost:8080
pause