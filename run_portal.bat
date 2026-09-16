@echo off
echo =========================================================================
echo   DELIVERY READINESS PORTAL EXECUTIVE DASHBOARD (ONIX)
echo =========================================================================
echo.
echo Starting Web Portal on http://127.0.0.1:4000 ...
echo Mode: Local Native Gmail Delivery (No Yellow Warning Box, Official Photo)
echo.
timeout /t 2 /nobreak >nul
start http://127.0.0.1:4000/campaigns
python app.py
pause
