@echo off
setlocal
cd /d %~dp0\..

set NO_PAUSE=0
if /I "%~1"=="--no-pause" set NO_PAUSE=1

python -m pip install --upgrade pip
python -m pip install pyinstaller

if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

python -m PyInstaller --noconfirm --clean --windowed --onefile --name SportsCounter ^
  --distpath dist --workpath build --specpath build src\windows_counter.py

if %errorlevel% neq 0 (
    echo.
    echo Build failed.
    if "%NO_PAUSE%"=="0" pause
    exit /b %errorlevel%
)

echo.
echo Build success: %cd%\dist\SportsCounter.exe
if "%NO_PAUSE%"=="0" pause
