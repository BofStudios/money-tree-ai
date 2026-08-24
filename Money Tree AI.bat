@echo off
rem Double-click this to start Money Tree AI.
rem No build step needed — it runs straight from the project.
cd /d "%~dp0"

if not exist ".venv\Scripts\pythonw.exe" (
  echo Could not find .venv - run this once to set the project up:
  echo     python -m venv .venv
  echo     .venv\Scripts\pip install -r requirements.txt
  pause
  exit /b 1
)

rem pythonw runs it without leaving a console window behind.
start "" ".venv\Scripts\pythonw.exe" -m app.main
