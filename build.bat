@echo off
setlocal
cd /d "%~dp0"

echo [1/3] Installing build dependencies...
py -m pip install -r requirements.txt pyinstaller
if errorlevel 1 goto error

echo.
echo [2/3] Building fast-start EXE...
REM onedir avoids unpacking a huge one-file archive every time the app starts.
REM Only collect Qt Multimedia, not every optional PySide6 module.
py -m PyInstaller --noconfirm --clean --onedir --windowed --name PIROZKOV --hidden-import PySide6.QtMultimedia --collect-all PySide6.QtMultimedia main.py
if errorlevel 1 goto error

echo.
echo [3/3] Preparing assets...
if not exist "dist\PIROZKOV\assets\photos" mkdir "dist\PIROZKOV\assets\photos"
if exist "assets\README.txt" copy /Y "assets\README.txt" "dist\PIROZKOV\assets\README.txt" >nul
if exist "assets\samo_soboy.mp3" copy /Y "assets\samo_soboy.mp3" "dist\PIROZKOV\assets\samo_soboy.mp3" >nul
if exist "assets\captions.srt" copy /Y "assets\captions.srt" "dist\PIROZKOV\assets\captions.srt" >nul
if exist "assets\photos" xcopy "assets\photos\*" "dist\PIROZKOV\assets\photos\" /E /I /Y >nul

echo.
echo Build complete!
echo Run: dist\PIROZKOV\PIROZKOV.exe
echo Keep the _internal folder and assets folder beside the EXE.
pause
exit /b 0

:error
echo.
echo BUILD FAILED. Copy the error text above and send it.
pause
exit /b 1
