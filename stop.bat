@echo off
setlocal
title Timo Server Stop
cd /d "%~dp0"

set "PORT=8000"
if not "%1"=="" set "PORT=%1"

set "PID="
for /f "tokens=5" %%p in ('netstat -ano ^| findstr "LISTENING" ^| findstr /c:":%PORT% "') do set "PID=%%p"
if not defined PID (
    echo No Timo server found on port %PORT%.
    exit /b 0
)

echo Stopping Timo server on port %PORT% ^(PID %PID%^)...
taskkill /F /T /PID %PID% >nul 2>&1
if errorlevel 1 (
    echo Failed to stop PID %PID%.
) else (
    echo Timo server stopped.
)
