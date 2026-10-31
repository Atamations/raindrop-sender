@echo off
cd /d "%~dp0"

if exist "%~dp0RaindropMailSender.exe" (
  start "" "%~dp0RaindropMailSender.exe"
  exit /b 0
)

if exist "%~dp0.venv\Scripts\python.exe" (
  "%~dp0.venv\Scripts\python.exe" "%~dp0ui_app.py"
  exit /b %ERRORLEVEL%
)

echo RaindropMailSender.exe veya .venv bulunamadi.
exit /b 1
