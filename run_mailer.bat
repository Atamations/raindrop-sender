@echo off
cd /d "%~dp0"

REM Paketlenmiş exe (Task Scheduler / otomasyon)
if exist "%~dp0RaindropMailSender.exe" (
  "%~dp0RaindropMailSender.exe" --send
  exit /b %ERRORLEVEL%
)

REM Geliştirme ortamı
if exist "%~dp0.venv\Scripts\python.exe" (
  "%~dp0.venv\Scripts\python.exe" "%~dp0main.py"
  exit /b %ERRORLEVEL%
)

echo RaindropMailSender.exe veya .venv bulunamadi.
exit /b 1
