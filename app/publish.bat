@echo off

REM --- Simple one-command publish script ---
REM This builds the app and publishes it - no installer needed for updates!

echo ========================================
echo OgarniaczSM - Build ^& Publish
echo ========================================
echo.

REM --- Locate Python (bypasses Windows Store alias) ---
set PYTHON_EXE=
set "USERNAME_VAR=%USERNAME%"

REM Try py launcher first (most reliable on Windows)
where py >nul 2>&1
if not errorlevel 1 (
    py -c "print('ok')" >nul 2>&1
    if not errorlevel 1 ( set "PYTHON_EXE=py" & goto :python_found )
)

REM Try common install paths
for %%P in (
    "C:\Python313\python.exe"
    "C:\Python312\python.exe"
    "C:\Python311\python.exe"
    "C:\Python310\python.exe"
    "C:\Program Files\Python313\python.exe"
    "C:\Program Files\Python312\python.exe"
    "C:\Program Files\Python311\python.exe"
) do (
    if exist %%P ( set "PYTHON_EXE=%%~P" & goto :python_found )
)

for %%P in (
    "%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python310\python.exe"
) do (
    if exist %%P ( set "PYTHON_EXE=%%~P" & goto :python_found )
)

REM Python not found - install via winget
echo Python not found. Installing Python 3.12 via winget...
where winget >nul 2>&1
if errorlevel 1 (
    echo ERROR: Neither Python nor winget found. Please install Python from https://python.org
    pause
    exit /b 1
)
winget install --id Python.Python.3.12 -e --silent --accept-source-agreements --accept-package-agreements
if errorlevel 1 (
    echo ERROR: winget install failed. Please install Python manually from https://python.org
    pause
    exit /b 1
)
REM Refresh PATH and try again
for %%P in (
    "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    "C:\Python312\python.exe"
    "C:\Program Files\Python312\python.exe"
) do (
    if exist %%P ( set "PYTHON_EXE=%%~P" & goto :python_found )
)
echo ERROR: Python installed but still not found. Please restart and try again.
pause
exit /b 1

:python_found
echo Python: %PYTHON_EXE%
echo.

REM --- Ensure build dependencies are installed for this account ---
echo Checking build dependencies...
%PYTHON_EXE% -c "import PyInstaller" >nul 2>&1
if errorlevel 1 (
    echo PyInstaller not found - installing build dependencies...
    %PYTHON_EXE% -m pip install --upgrade pip >nul
    %PYTHON_EXE% -m pip install pyinstaller PySide6 pywin32
    if errorlevel 1 (
        echo ERROR: Failed to install build dependencies.
        pause
        exit /b 1
    )
    echo Build dependencies installed OK.
) else (
    echo Build dependencies OK.
)
echo.

REM --- auto-bump version (0.0.0.1) ---
set "SCRIPT_DIR=%~dp0"
set "VERSION_FILE=%SCRIPT_DIR%version.txt"
set VERSION=0.0.0.1
if exist "%SCRIPT_DIR%bump_version.py" (
    for /f "delims=" %%i in ('%PYTHON_EXE% "%SCRIPT_DIR%bump_version.py"') do set VERSION=%%i
    if errorlevel 1 (
        echo ERROR: Failed to bump version via bump_version.py
        pause
        exit /b 1
    )
) else (
    if exist "%VERSION_FILE%" (
        for /f "tokens=1" %%i in ('type "%VERSION_FILE%"') do (
            set VERSION=%%i
            goto :version_done
        )
    )
)
:version_done
echo Version: %VERSION%
echo.

REM --- Step 1: Build ---
echo [1/2] Building application...
%PYTHON_EXE% "%SCRIPT_DIR%GENERATE_OGARNIACZ_EXE.py"
if errorlevel 1 (
    echo.
    echo ERROR: Build failed!
    pause
    exit /b 1
)
echo.

REM --- Step 2: Publish ---
echo [2/2] Publishing to PROD...

REM --- ścieżki projektu ---
set DIST=%SCRIPT_DIR%dist\ogarniacz
set OUT_MAIN=%DIST%\OgarniaczSM
set OUT_UPD=%DIST%\OgarniaczUpdater.exe
set SHARE=%SCRIPT_DIR%PROD

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

REM --- kopiowanie do latest (tylko najnowsza wersja) ---
rmdir /S /Q "%SHARE%\latest" >nul 2>nul
mkdir "%SHARE%\latest" >nul 2>nul
robocopy "%OUT_MAIN%" "%SHARE%\latest" /MIR >nul
copy /Y "%OUT_UPD%" "%SHARE%\latest\OgarniaczUpdater.exe" >nul

REM manifest (z src_path dla autoupdate.py - używamy lokalnej ścieżki)
%PYTHON_EXE% "%SCRIPT_DIR%create_manifest.py"

echo.
echo ========================================
echo Done! Version %VERSION% published.
echo.
echo IMPORTANT: The installer must be rebuilt to include this new version!
echo (The installer copies from dist\ogarniacz, which was just updated)
echo.
echo Rebuilding installer now...
%PYTHON_EXE% "%SCRIPT_DIR%GENERATE_INSTALLER_EXE.py"
if errorlevel 1 (
    echo.
    echo WARNING: Installer rebuild failed!
    echo You can rebuild it manually: python GENERATE_INSTALLER_EXE.py
    echo.
) else (
    echo.
    echo Installer rebuilt successfully!
    echo Location: %SCRIPT_DIR%dist\OgarniaczInstaller.exe
    echo.
    echo Next steps:
    echo   1. Run installer on PCs that need the new version: dist\OgarniaczInstaller.exe
    echo   2. After installing once, future updates will auto-update via shared drive
    echo.
)
echo ========================================
pause
