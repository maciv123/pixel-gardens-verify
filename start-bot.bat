@echo off
title Pixel Gardens Bot
echo.
echo === Pixel Gardens Verify Bot ===
echo.
echo Stopping any old bot copies...
taskkill /F /FI "WINDOWTITLE eq Pixel Gardens Bot" >nul 2>&1
for /f "tokens=2 delims=," %%a in ('wmic process where "name='python.exe' and CommandLine like '%%pixel-gardens-verify%%main.py%%'" get ProcessId /format:csv 2^>nul ^| findstr /r "[0-9]"') do (
    taskkill /PID %%~a /F >nul 2>&1
)
timeout /t 3 /nobreak >nul
echo Starting bot (keep this window open!)...
echo.
cd /d "%~dp0bot"
python main.py
echo.
echo Bot stopped. Press any key to close.
pause >nul
