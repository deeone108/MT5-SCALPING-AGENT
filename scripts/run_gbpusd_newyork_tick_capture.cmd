@echo off
cd /d C:\Users\derek\Desktop\Vcodeee
C:\Users\derek\Desktop\Vcodeee\.venv\Scripts\python.exe scripts\capture_mt5_ticks.py --symbol GBPUSD --samples 3600 --interval-seconds 1 --output-dir data\mt5_ticks\roboforex_ecn_cross_pair
