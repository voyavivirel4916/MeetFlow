@echo off
setlocal
cd /d "%~dp0"
"Src\backend\.venv\Scripts\python.exe" "Src\scripts\run_showcase.py" %*
if errorlevel 1 pause
