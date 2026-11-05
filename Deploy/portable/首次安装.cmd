@echo off
setlocal
cd /d "%~dp0"
py -3.11 "%~dp0install_demo.py"
if errorlevel 1 (
  echo Install 64-bit Python 3.11 with the Python launcher, then try again.
  pause
  exit /b 1
)
pause
