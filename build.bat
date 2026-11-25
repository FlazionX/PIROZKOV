@echo off
cd /d %~dp0
py -m pip install -r requirements.txt pyinstaller
py -m PyInstaller --noconfirm --clean --onefile --windowed --name PIROZKOV main.py
pause
