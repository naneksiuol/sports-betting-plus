@echo off
title Sports Betting Plus
cd /d "%~dp0"
echo Starting Sports Betting Plus...
echo.
echo App will open at http://localhost:8501
echo Remote access: use your Tailscale IP at http://YOUR-TAILSCALE-IP:8501
echo Close this window to stop the app.
echo.
python -m streamlit run src/props_dashboard.py --server.address 0.0.0.0 --server.headless false
pause
