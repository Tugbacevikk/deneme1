@echo off
rem Otomatik PostgreSQL Gunluk Yedekleme Bat Betigi
set PGPASSWORD=admin123
set BACKUP_DIR=c:\Users\ADIL CEVIK\Desktop\istakip\istakip\backups
if not exist "%BACKUP_DIR%" mkdir "%BACKUP_DIR%"

set CURR_DATE=%date:~-4%%date:~3,2%%date:~0,2%_%time:~0,2%%time:~3,2%%time:~6,2%
set CURR_DATE=%CURR_DATE: =0%

"C:\Program Files\PostgreSQL\18\bin\pg_dump.exe" -h 127.0.0.1 -p 5432 -U takip_user -F c -b -v -f "%BACKUP_DIR%\fabrika_takip_%CURR_DATE%.dump" fabrika_takip
