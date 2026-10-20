@echo off
setlocal

REM --- odczytaj wersję z version.txt ---
set SCRIPT_DIR=%~dp0
set VERSION_FILE=%SCRIPT_DIR%version.txt
set VERSION=0.5.1.1
if exist "%VERSION_FILE%" (
    for /f "tokens=1" %%i in (%VERSION_FILE%) do set VERSION=%%i
    REM Strip any trailing whitespace
    set VERSION=%VERSION: =%
)
echo Using version: %VERSION%

REM --- ścieżki projektu ---
set DIST=%SCRIPT_DIR%dist\ogarniacz
set OUT_MAIN=%DIST%\OgarniaczSM
set OUT_UPD=%DIST%\OgarniaczUpdater.exe

REM --- katalog PROD w projekcie (shared drive) ---
set SHARE=%SCRIPT_DIR%PROD

if not exist "%OUT_MAIN%\OgarniaczSM.exe" (
  echo Brak zbudowanego OgarniaczSM.exe (onedir). Uruchom najpierw build.
  exit /b 1
)

if not exist "%OUT_UPD%" (
  echo Brak OgarniaczUpdater.exe. Uruchom najpierw build.
  exit /b 1
)

REM --- kopiowanie do latest (tylko najnowsza wersja) ---
rmdir /S /Q "%SHARE%\latest" >nul 2>nul
mkdir "%SHARE%\latest" >nul 2>nul
robocopy "%OUT_MAIN%" "%SHARE%\latest" /MIR
copy /Y "%OUT_UPD%" "%SHARE%\latest\OgarniaczUpdater.exe" >nul

REM manifest (z src_path dla autoupdate.py - używamy lokalnej ścieżki)
python "%SCRIPT_DIR%create_manifest.py"

echo.
echo Opublikowano %VERSION% -> %SHARE%
echo Gotowe.
