@echo off
rem NMOS portable: start Postgres, the sidecar and the worker. Close this window or press Ctrl+C to stop.
cd /d "%~dp0"
python\python.exe nmos_launcher.py
pause
