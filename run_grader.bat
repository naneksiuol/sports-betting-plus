@echo off
REM Sports Betting Plus — Auto Result Grader
REM Grades yesterday's pending bets via auto_grade.py (MLB/NBA/WNBA/NHL).
REM
REM One-time setup (run as Administrator):
REM   schtasks /Create /TN "SBP_AutoGrader" /TR "C:\Users\kenan\sports-betting-plus\run_grader.bat" /SC DAILY /ST 02:00 /RL HIGHEST /F

cd /d "%~dp0"
if not exist logs mkdir logs

echo [%date% %time%] Auto-grader started >> logs\grader.log
call venv\Scripts\activate.bat
python auto_grade.py >> logs\grader.log 2>&1
echo [%date% %time%] Auto-grader finished >> logs\grader.log
echo [%date% %time%] Model retrain started >> logs\grader.log
python train_models.py >> logs\grader.log 2>&1
echo [%date% %time%] Model retrain finished >> logs\grader.log
