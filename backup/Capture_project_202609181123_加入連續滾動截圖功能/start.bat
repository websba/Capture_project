@echo off
cd /d "%~dp0"
"%~dp0env\.venv\Scripts\python.exe" "%~dp0main.py"
if errorlevel 1 pause
