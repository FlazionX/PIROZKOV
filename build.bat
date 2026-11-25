@echo off
setlocal
cd /d "%~dp0"

echo [1/4] Installing build dependencies...
py -m pip install -r requirements.txt pyinstaller
if errorlevel 1 goto error

echo.
echo [2/4] Building native desktop icon helper when MSVC is available...
if exist "desktop_icons.dll" del /Q "desktop_icons.dll"
where cl >nul 2>nul
if errorlevel 1 (
    echo MSVC compiler not found. This local build will use the visual effects without real desktop-icon movement.
    echo The GitHub Actions build includes the native icon helper automatically.
    py -m PyInstaller --noconfirm --clean --onedir --windowed --hidden-import PySide6.QtMultimedia --collect-all PySide6.QtMultimedia --name PIROZKOV main.py
) else (
    cl /nologo /O2 /EHsc /LD desktop_icons.cpp /Fe:desktop_icons.dll /link ole32.lib oleaut32.lib shell32.lib
    if errorlevel 1 goto error
    py -m PyInstaller --noconfirm --clean --onedir --windowed --hidden-import PySide6.QtMultimedia --collect-all PySide6.QtMultimedia --add-binary "desktop_icons.dll;." --name PIROZKOV main.py
)
if errorlevel 1 goto error

echo.
echo [3/4] Preparing assets...
if not exist "dist\PIROZKOV\assets\photos" mkdir "dist\PIROZKOV\assets\photos"
if not exist "dist\PIROZKOV\assets\gifs" mkdir "dist\PIROZKOV\assets\gifs"
if exist "assets\README.txt" copy /Y "assets\README.txt" "dist\PIROZKOV\assets\README.txt" >nul
if exist "assets\samo_soboy.mp3" copy /Y "assets\samo_soboy.mp3" "dist\PIROZKOV\assets\samo_soboy.mp3" >nul
if exist "assets\captions.srt" copy /Y "assets\captions.srt" "dist\PIROZKOV\assets\captions.srt" >nul
if exist "assets\photos" xcopy "assets\photos\*" "dist\PIROZKOV\assets\photos\" /E /I /Y >nul
if exist "assets\gifs" xcopy "assets\gifs\*" "dist\PIROZKOV\assets\gifs\" /E /I /Y >nul

echo.
echo [4/4] Build complete!
echo Run: dist\PIROZKOV\PIROZKOV.exe
echo Keep the _internal folder and assets folder beside the EXE.
pause
exit /b 0

:error
echo.
echo BUILD FAILED. Copy the error text above and send it.
pause
exit /b 1
