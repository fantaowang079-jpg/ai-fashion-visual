@echo off
setlocal
cd /d "%~dp0"

echo ============================================
echo   Yijing Studio - AI Fashion Workbench
echo ============================================
echo.
echo URL: http://127.0.0.1:8000
echo Press Ctrl+C to stop the server.
echo.

set "PY=python"
where python >nul 2>nul
if errorlevel 1 (
  where py >nul 2>nul
  if errorlevel 1 (
    echo [ERROR] Python not found.
    echo Install Python 3.10+ and check "Add python.exe to PATH".
    pause
    exit /b 1
  )
  set "PY=py -3"
)

%PY% -c "import fastapi, uvicorn, PIL, openai" >nul 2>nul
if errorlevel 1 (
  echo [INFO] Installing dependencies from requirements.txt ...
  %PY% -m pip install -r requirements.txt
  if errorlevel 1 (
    echo [ERROR] pip install failed.
    echo Run manually: %PY% -m pip install -r requirements.txt
    pause
    exit /b 1
  )
)

netstat -ano | findstr ":8000" | findstr "LISTENING" >nul
if not errorlevel 1 (
  echo [INFO] Port 8000 is already in use. Another server may be running.
  echo.
  echo Run "netstat -ano" to find the PID listening on port 8000,
  echo then stop it with: taskkill /PID PID /F
  echo.
  pause
  exit /b 1
)

%PY% app.py
echo.
echo Server exited with code %errorlevel%
pause
