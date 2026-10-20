@echo off

REM --- Test build (local only) ---
REM Builds and copies to C:\Ogarniacz Tests (no PROD publish)

echo ========================================
echo OgarniaczSM - Test Build (Local Only)
echo ========================================
echo.

REM --- use fixed test version (don't modify production version.txt) ---
set "SCRIPT_DIR=%~dp0"
set "VERSION_FILE=%SCRIPT_DIR%version.txt"
set VERSION=0.0.0.1

REM Read current production version for display only (don't modify it)
if exist "%VERSION_FILE%" (
    for /f "tokens=1" %%i in ('type "%VERSION_FILE%"') do (
        echo Production version: %%i
    )
)

echo Test Version: %VERSION%
echo.

REM --- Step 1: Build ---
echo [1/2] Building application...
python "%SCRIPT_DIR%GENERATE_OGARNIACZ_EXE.py"
if errorlevel 1 (
    echo.
    echo ERROR: Build failed!
    pause
    exit /b 1
)
echo.

REM --- Step 2: Copy to local test folder ---
echo [2/2] Copying to C:\Ogarniacz Tests...

set DIST=%SCRIPT_DIR%dist\ogarniacz
set OUT_MAIN=%DIST%\OgarniaczSM
set OUT_UPD=%DIST%\OgarniaczUpdater.exe
set TEST_ROOT=C:\Ogarniacz Tests

if not exist "%OUT_MAIN%\OgarniaczSM.exe" (
  echo ERROR: Build not found. Run build first.
  pause
  exit /b 1
)

if not exist "%OUT_UPD%" (
  echo ERROR: Updater not found. Run build first.
  pause
  exit /b 1
)

mkdir "%TEST_ROOT%\releases\%VERSION%" >nul 2>nul
robocopy "%OUT_MAIN%" "%TEST_ROOT%\releases\%VERSION%" /MIR >nul
copy /Y "%OUT_UPD%" "%TEST_ROOT%\releases\%VERSION%\OgarniaczUpdater.exe" >nul

REM latest = kopia najnowszej wersji testowej
rmdir /S /Q "%TEST_ROOT%\latest" >nul 2>nul
mkdir "%TEST_ROOT%\latest" >nul 2>nul
robocopy "%TEST_ROOT%\releases\%VERSION%" "%TEST_ROOT%\latest" /MIR >nul

echo.
echo ========================================
echo Done! Test Version %VERSION% in %TEST_ROOT%
echo.
echo Tip: Run OgarniaczSM.exe from:
echo   %TEST_ROOT%\latest\OgarniaczSM.exe
echo ========================================
pause

