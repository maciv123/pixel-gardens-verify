@echo off
title Pixel Gardens Bot
echo.
echo === Pixel Gardens Verify Bot ===
echo.
echo Stopping any old bot copies...
taskkill /F /FI "WINDOWTITLE eq Pixel Gardens Bot" >nul 2>&1
for /f "tokens=2" %%a in ('tasklist /fi "imagename eq python.exe" /fo list ^| find "PID:"') do (
    taskkill /PID %%a /F >nul 2>&1
)
timeout /t 3 /nobreak >nul
echo Starting bot (keep this window open!)...
echo.
cd /d "%~dp0bot"
python main.py
echo.
echo Bot stopped. Press any key to close.
pause >nul
