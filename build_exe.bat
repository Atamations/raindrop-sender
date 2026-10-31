@echo off
cd /d "%~dp0"
call .venv\Scripts\activate.bat
python -m pip install -q pyinstaller
pyinstaller --noconfirm --clean --windowed --name RaindropMailSender ^
  --paths . ^
  --add-data "ui;ui" ^
  --add-data "run_mailer.bat;." ^
  --add-data ".env.example;." ^
  --hidden-import mailer ^
  --hidden-import mailer.config ^
  --hidden-import mailer.send ^
  --hidden-import mailer.schedule ^
  --hidden-import mailer.report ^
  --collect-all clr_loader ^
  --collect-all pythonnet ^
  ui_app.py

if errorlevel 1 exit /b 1
echo.
echo Build OK: dist\RaindropMailSender\
exit /b 0
