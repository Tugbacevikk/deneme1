@echo off
chcp 65001 >nul
title Is Takip Sistemi ve Mobil Uygulama

REM --- UTF-8 Turkce Karakter Destegi ---
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
set "PATH=C:\flutter\bin;C:\Users\ADIL CEVIK\AppData\Local\gh\bin;%PATH%"

echo.
echo ============================================================
echo   IS TAKIP SISTEMI VE MOBIL UYGULAMA BASLATILIYOR
echo   1. Flask Web Sunucusu : http://localhost:5000
echo   2. Mobil Uygulama     : http://localhost:8080
echo ============================================================
echo.

cd /d "%~dp0"
start "Flask Sunucusu (Port 5000)" cmd /k "set PYTHONUTF8=1 && set PYTHONIOENCODING=utf-8 && python web/app.py"

cd /d "C:\Users\ADIL CEVIK\Desktop\istakipmobil"
start "Mobil Uygulama (Port 8080)" cmd /k "python -m http.server 8080 --directory build/web"
start "" http://localhost:8080

echo Hem Web Sunucusu (5000) hem Mobil Uygulama (8080) aninda baslatildi!
timeout /t 2 >nul

