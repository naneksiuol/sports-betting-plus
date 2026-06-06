@echo off
REM Sports Betting Plus — Auto Result Grader
REM Run nightly via Windows Task Scheduler to grade all pending bets.
REM
REM Setup (run once as Administrator in Command Prompt):
REM   schtasks /Create /TN "SBP_AutoGrader" /TR "C:\Users\kenan\sports-betting-plus\run_grader.bat" /SC DAILY /ST 00:30 /RL HIGHEST /F

cd /d "%~dp0"
echo [%date% %time%] Running result grader... >> logs\grader.log
python -c "
import sys, os
sys.path.insert(0, 'src')
from result_grader import grade_pending_bets
from bet_tracker import load_bets
bets = load_bets()
pending = [b for b in bets if b.get('result') == 'pending']
print(f'Grading {len(pending)} pending bets...')
results = grade_pending_bets(bets)
graded = sum(1 for r in results if r.get('result') in ('win','loss','push'))
print(f'Graded: {graded} bets')
" >> logs\grader.log 2>&1
echo [%date% %time%] Done. >> logs\grader.log
