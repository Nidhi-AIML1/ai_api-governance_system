@echo off
cd /d "%~dp0"
docker compose down
echo.
echo  Stopped. Your data is kept. To also delete the data volume run: docker compose down -v
pause