@echo off
REM Backend starter — run inside snail_avatar/
cd /d "%~dp0..\"
python -m uvicorn snail_avatar.backend.fastapi_app.main:app --host 127.0.0.1 --port 8000
pause
