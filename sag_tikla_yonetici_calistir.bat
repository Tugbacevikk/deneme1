@echo off
:: Yonetici Yetkisi Kontrolu ve Otomatik Yukseltme
net session >nul 2>&1
if %errorLevel% neq 0 (
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)

echo ========================================================
echo  PostgreSQL 5432 Portu Guvenlik Duvari Izni Ekleniyor...
echo ========================================================

netsh advfirewall firewall add rule name="PostgreSQL 5432 Portu" dir=in action=allow protocol=TCP localport=5432

echo.
echo ========================================================
echo  ISLEM TAMAMLANDI! 
echo  PostgreSQL 5432 portu dış bağlantılara açıldı.
echo  Raspberry Pi artık bu PC'ye sorunsuz bağlanabilir.
echo ========================================================
pause
