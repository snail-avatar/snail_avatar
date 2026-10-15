@echo off
REM Frontend starter — run inside snail_avatar/frontend/vue_app/
cd /d "%~dp0frontend\vue_app"
npx vite --host 127.0.0.1 --port 5173
pause
