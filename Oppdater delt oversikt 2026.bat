@echo off
cd /d "%~dp0"
python "scripts\build_shared_weekly_results_2026.py"
python "scripts\build_site_2026.py"
pause
