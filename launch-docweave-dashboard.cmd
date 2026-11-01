@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\docweave-desktop.exe" (
    echo Install DocWeave using the instructions in README.md first.
    pause
    exit /b 1
)
".venv\Scripts\docweave-desktop.exe"
