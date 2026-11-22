@echo off
rem Hourly forward journal cycle (ADR-036/038/045): scan, settle, dashboard, notify - each step under a watchdog.
rem Paper only: nothing here places an order.
cd /d "%~dp0.."
echo ==== %date% %time% >> reports\journal_cycle.log
".venv\Scripts\python.exe" scripts\journal_cycle.py >> reports\journal_cycle.log 2>&1
