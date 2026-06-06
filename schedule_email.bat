@echo off
REM Sports Betting Plus — Daily Email Auto-Sender
REM Sends the full multi-sport betting slip every morning at 8:00 AM.
REM
REM ── SETUP (run once as Administrator) ────────────────────────────────────────
REM   schedule_email.bat --install
REM
REM ── MANUAL RUN ───────────────────────────────────────────────────────────────
REM   schedule_email.bat

if "%1"=="--install" goto install

:run
cd /d "%~dp0"
if not exist logs mkdir logs
echo [%date% %time%] Sending daily email slip... >> logs\email_sender.log
python send_daily_bets.py >> logs\email_sender.log 2>&1
echo [%date% %time%] Done. >> logs\email_sender.log
goto end

:install
echo Registering daily email task (8:00 AM)...
schtasks /Create /TN "SBP_DailyEmail" /TR "\"%~dp0schedule_email.bat\"" /SC DAILY /ST 08:00 /RL HIGHEST /F
if %errorlevel%==0 (
    echo [OK] Task registered. Email will send every morning at 8:00 AM.
    echo      To remove: schtasks /Delete /TN "SBP_DailyEmail" /F
    echo      To run now: schtasks /Run /TN "SBP_DailyEmail"
) else (
    echo [ERROR] Failed. Try running as Administrator.
)

:end
