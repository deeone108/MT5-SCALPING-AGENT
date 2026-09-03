@echo off
cd /d C:\Users\derek\Desktop\Vcodeee
.venv\Scripts\python.exe scripts\run_chronological_validation.py --window-days 28 --strategies new_york_reversal new_york_bollinger_rsi_reversal --spread-points 2 --slippage-points 1 --report-path reports\chronological_validation\new_york_candidates_moderate_cost.json
if errorlevel 1 exit /b %errorlevel%
.venv\Scripts\python.exe scripts\run_chronological_validation.py --window-days 28 --strategies new_york_reversal new_york_bollinger_rsi_reversal --spread-points 5 --slippage-points 2 --report-path reports\chronological_validation\new_york_candidates_severe_cost.json
exit /b %errorlevel%