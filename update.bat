@echo off
REM Sports Betting Plus — One-click updater
REM Pull latest code from GitHub and restart Streamlit.

cd /d "%~dp0"
echo.
echo ============================================================
echo  Sports Betting Plus — Updater
echo ============================================================
echo.

REM 1. Pull latest code
echo [1/3] Pulling latest code from GitHub...
git pull origin claude/adoring-curie-I6KnD
if %errorlevel% neq 0 (
    echo [ERROR] git pull failed. Check your internet connection.
    pause
    exit /b 1
)
echo  Done.
echo.

REM 2. Kill any running Streamlit process
echo [2/3] Stopping old Streamlit instance...
taskkill /F /IM python.exe /FI "WINDOWTITLE eq streamlit*" >nul 2>&1
REM Broader kill in case window title doesn't match:
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8501"') do (
    taskkill /F /PID %%a >nul 2>&1
)
echo  Done.
echo.

REM 3. Start Streamlit fresh
echo [3/3] Starting Streamlit on port 8501...
if not exist logs mkdir logs
start "Streamlit" /B python -m streamlit run src\props_dashboard.py ^
    --server.address 0.0.0.0 ^
    --server.port 8501 ^
    --server.headless true ^
    --server.runOnSave false ^
    >> logs\streamlit.log 2>&1

echo.
echo ============================================================
echo  Update complete!
echo  App:     http://localhost:8501
echo  Logs:    logs\streamlit.log
echo ============================================================
echo.
echo  (Close this window — Streamlit is running in background)
timeout /t 5
