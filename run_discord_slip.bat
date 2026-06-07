@echo off
REM Sports Betting Plus — Scheduled Discord Daily Slip
REM Scrapes live props and posts top plays + parlays to Discord each morning.
REM
REM One-time setup (run as Administrator):
REM   schtasks /Create /TN "SBP_DiscordSlip" /TR "C:\Users\kenan\sports-betting-plus\run_discord_slip.bat" /SC DAILY /ST 09:00 /RL HIGHEST /F

cd /d "%~dp0"
if not exist logs mkdir logs

echo [%date% %time%] Discord slip started >> logs\discord_slip.log
call venv\Scripts\activate.bat
python run_discord_slip.py >> logs\discord_slip.log 2>&1
echo [%date% %time%] Discord slip finished >> logs\discord_slip.log
