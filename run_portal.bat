@echo off
cd /d "%~dp0"
echo =========================================================================
echo   DELIVERY READINESS PORTAL EXECUTIVE DASHBOARD (ONIX)
echo =========================================================================
echo.
echo Starting Web Portal on http://127.0.0.1:4000 ...
echo.
timeout /t 2 /nobreak >nul
start http://127.0.0.1:4000/priority_dashboard
"C:\Users\nikhil.shelke\AppData\Local\Programs\Python\Python311\python.exe" app.py
pause
