@echo off
setlocal
cd /d %~dp0\..

set "NO_PAUSE=0"
if /I "%~1"=="--no-pause" set "NO_PAUSE=1"
if not exist release mkdir release
set "LOG_FILE=%cd%\release\installer_build.log"
echo ==== [%date% %time%] build_windows_installer start ==== > "%LOG_FILE%"

set "ISCC="
if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" set "ISCC=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if exist "C:\Program Files\Inno Setup 6\ISCC.exe" set "ISCC=C:\Program Files\Inno Setup 6\ISCC.exe"

if "%ISCC%"=="" (
    echo Inno Setup 6 not found.
    echo Please install Inno Setup first: https://jrsoftware.org/isdl.php
    echo ERROR: ISCC.exe not found >> "%LOG_FILE%"
    if "%NO_PAUSE%"=="0" pause
    exit /b 1
)

call scripts\build_windows_exe.bat --no-pause
if %errorlevel% neq 0 (
    echo.
    echo EXE build failed.
    echo ERROR: EXE build failed with code %errorlevel% >> "%LOG_FILE%"
    if "%NO_PAUSE%"=="0" pause
    exit /b %errorlevel%
)

set "LANG_NAME=english"
set "LANG_FILE=compiler:Default.isl"
if exist "%~dp0..\tools\ChineseSimplified.isl" (
    set "LANG_NAME=chinesesimp"
    set "LANG_FILE=%~dp0..\tools\ChineseSimplified.isl"
) else (
    if exist "C:\Program Files (x86)\Inno Setup 6\Languages\ChineseSimplified.isl" (
        set "LANG_NAME=chinesesimp"
        set "LANG_FILE=C:\Program Files (x86)\Inno Setup 6\Languages\ChineseSimplified.isl"
    ) else (
        if exist "C:\Program Files\Inno Setup 6\Languages\ChineseSimplified.isl" (
            set "LANG_NAME=chinesesimp"
            set "LANG_FILE=C:\Program Files\Inno Setup 6\Languages\ChineseSimplified.isl"
        )
    )
)

echo Using installer language: %LANG_NAME%
echo ISCC=%ISCC% >> "%LOG_FILE%"
echo LANG_NAME=%LANG_NAME% >> "%LOG_FILE%"
echo LANG_FILE=%LANG_FILE% >> "%LOG_FILE%"
"%ISCC%" /DLangName=%LANG_NAME% /DLangFile="%LANG_FILE%" installer\SportsCounter.iss >> "%LOG_FILE%" 2>&1
if %errorlevel% neq 0 (
    echo.
    echo Installer build failed.
    echo ERROR: Installer build failed with code %errorlevel% >> "%LOG_FILE%"
    echo See log: %LOG_FILE%
    if "%NO_PAUSE%"=="0" pause
    exit /b %errorlevel%
)

echo.
echo Installer build success:
echo %cd%\release
echo SUCCESS >> "%LOG_FILE%"
if "%NO_PAUSE%"=="0" pause
