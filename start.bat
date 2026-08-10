@echo off
setlocal
title Timo Interview Prep Server
cd /d "%~dp0"

set "PORT=8000"
if not "%1"=="" set "PORT=%1"

rem If something is already listening on this port, tell the user instead of a confusing traceback.
set "EXISTING="
for /f "tokens=5" %%p in ('netstat -ano ^| findstr "LISTENING" ^| findstr /c:":%PORT% "') do set "EXISTING=%%p"
if defined EXISTING (
    echo Timo is already running on port %PORT% ^(PID %EXISTING%^).
    echo Open http://127.0.0.1:%PORT% in your browser.
    echo Close that window or run "stop.bat %PORT%" to stop it.
    exit /b 0
)

echo Starting Timo server: http://127.0.0.1:%PORT%
echo Stop it by closing this window or running "stop.bat %PORT%".
echo.
python -m uvicorn backend.main:app --reload --port %PORT%
