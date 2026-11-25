@echo off
cd /d %~dp0
py -m pip install --upgrade pip
py -m pip install -r requirements.txt pyinstaller

REM Do not use --collect-all PySide6: it bundles every optional Qt module
REM (including modules this app never imports) and makes the EXE much larger.
py -m PyInstaller --noconfirm --clean --onefile --windowed --name PIROZKOV --hidden-import PySide6.QtMultimedia main.py

if not exist dist\assets\photos mkdir dist\assets\photos
if exist assets\README.txt copy /Y assets\README.txt dist\assets\README.txt >nul
if exist assets\samo_soboy.mp3 copy /Y assets\samo_soboy.mp3 dist\assets\samo_soboy.mp3 >nul
if exist assets\captions.srt copy /Y assets\captions.srt dist\assets\captions.srt >nul
if exist assets\photos xcopy assets\photos dist\assets\photos /E /I /Y >nul
echo.
echo EXE: dist\PIROZKOV.exe
echo Put samo_soboy.mp3 into dist\assets before running.
echo If the app fails to start, send the build log so the missing Qt plugin can be added.
pause
