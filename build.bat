@echo off
cd /d %~dp0
py -m pip install -r requirements.txt pyinstaller
py -m PyInstaller --noconfirm --clean --onefile --windowed --name PIROZKOV main.py
if not exist dist\assets mkdir dist\assets
if exist assets xcopy assets dist\assets /E /I /Y >nul
echo.
echo EXE: dist\PIROZKOV.exe
echo Media folder: dist\assets
pause
