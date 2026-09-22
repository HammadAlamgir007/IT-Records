@echo off
setlocal
title IT Records - setup data
set "APP_DB=%USERPROFILE%\ITRecords\employees.db"

mkdir "%USERPROFILE%\ITRecords" 2>nul
copy /Y "%~dp0YOUR-DATA\employees.db" "%APP_DB%" >nul
echo.
echo  OK - the real data is now on this PC (replaces anything already here).
echo  Opening IT Records...
start "" "%~dp0IT Records.exe"
endlocal