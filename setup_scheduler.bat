@echo off
echo ============================================================
echo  Sports Betting Plus — Windows Task Scheduler Setup
echo ============================================================
echo.
echo This will create two daily scheduled tasks:
echo   1. Auto-Grader     — 2:00 AM (grades yesterday's bets)
echo   2. Discord Slip    — 9:00 AM (posts today's top plays)
echo.
echo Run as Administrator for best results.
echo.

:: ── Task 1: Auto-Grader at 2 AM ──────────────────────────────────────────────
echo [1/2] Scheduling Auto-Grader at 2:00 AM...
schtasks /create /tn "SBP_AutoGrader" /tr "\"C:\Users\kenan\sports-betting-plus\run_grader.bat\"" /sc daily /st 02:00 /f /rl HIGHEST

if %errorlevel% == 0 (
    echo       OK — SBP_AutoGrader scheduled at 2:00 AM daily.
) else (
    echo       WARNING: Could not schedule grader. Try running as Administrator.
)

echo.

:: ── Task 2: Discord Slip at 9 AM ─────────────────────────────────────────────
echo [2/2] Scheduling Discord Slip at 9:00 AM...
schtasks /create /tn "SBP_DiscordSlip" /tr "\"C:\Users\kenan\sports-betting-plus\run_discord_slip.bat\"" /sc daily /st 09:00 /f /rl HIGHEST

if %errorlevel% == 0 (
    echo       OK — SBP_DiscordSlip scheduled at 9:00 AM daily.
) else (
    echo       WARNING: Could not schedule Discord slip. Try running as Administrator.
)

echo.
echo ============================================================
echo  Setup complete. Tasks will run automatically each day:
echo    2:00 AM — Grade yesterday's pending bets ^(all sports^)
echo    9:00 AM — Post today's top plays to Discord
echo.
echo  Logs saved to:  logs\grader.log
echo                  logs\discord_slip.log
echo.
echo  To view tasks:   Task Scheduler ^> Task Scheduler Library
echo  To remove:       schtasks /delete /tn "SBP_AutoGrader" /f
echo                   schtasks /delete /tn "SBP_DiscordSlip" /f
echo ============================================================
pause
