@echo off
echo ============================================================
echo   Snail Avatar - Start Backend + Frontend
echo ============================================================
echo.

REM --- kill leftovers (only ports 8000 / 5173, do NOT touch other python/node) ---
echo [0/3] free ports 8000 / 5173 if occupied...
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":8000 " ^| findstr LISTENING') do taskkill /F /PID %%p >nul 2>nul
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":5173 " ^| findstr LISTENING') do taskkill /F /PID %%p >nul 2>nul
timeout /t 2 /nobreak >nul

REM --- backend in new window ---
echo [1/3] start FastAPI (port 8000)...
start "SnailAvatar-Backend" cmd /k "%~dp0start_backend.bat"

REM --- frontend in new window ---
echo [2/3] start Vite (port 5173)...
start "SnailAvatar-Frontend" cmd /k "%~dp0start_frontend.bat"

REM --- wait then open browser ---
echo [3/3] waiting (8s)...
timeout /t 8 /nobreak >nul

echo.
echo Opening browser...
start "" "http://127.0.0.1:5173"

echo.
echo ============================================================
echo   Backend:  http://127.0.0.1:8000
echo   Frontend: http://127.0.0.1:5173
echo.
echo   Close this window does NOT stop services.
echo   Close the two popup cmd windows to stop.
echo ============================================================
echo.
pause
