@echo off
rem Forward journal cycle (ADR-036/038): scan new signals (with backfill), then settle open ones. Paper only.
cd /d "%~dp0.."
echo ==== %date% %time% >> reports\journal_cycle.log
".venv\Scripts\python.exe" scripts\forward_journal.py scan >> reports\journal_cycle.log 2>&1
".venv\Scripts\python.exe" scripts\forward_journal.py settle >> reports\journal_cycle.log 2>&1
