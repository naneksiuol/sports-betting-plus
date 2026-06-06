@echo off
echo Setting up Sports Betting Plus — Nightly Auto-Grader (2 AM Central)...

:: 2 AM Central = 8 AM UTC (CST) or 7 AM UTC (CDT). Using 08:00 UTC covers both.
schtasks /create /tn "SportsBettingPlusAutoGrade" /tr "python C:\Users\kenan\sports-betting-plus\auto_grade.py" /sc daily /st 02:00 /f /rl HIGHEST

if %errorlevel% == 0 (
    echo.
    echo SUCCESS! Task scheduled:
    echo   Name:    SportsBettingPlusAutoGrade
    echo   Runs:    Every day at 2:00 AM
    echo   Script:  C:\Users\kenan\sports-betting-plus\auto_grade.py
    echo.
    echo The grader will automatically:
    echo   1. Fetch yesterday's MLB results from MLB Stats API
    echo   2. Grade all pending bets as Win / Loss / Push
    echo   3. Email you a summary report
) else (
    echo.
    echo ERROR: Could not create task. Try running as Administrator.
)

pause
