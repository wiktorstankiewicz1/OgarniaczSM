# Build Instructions for OgarniaczSM

## Quick Start

### 1. Build the Application
```bash
python GENERATE_OGARNIACZ_EXE.py
```

This creates:
- `dist/ogarniacz/OgarniaczSM/` - Main application (onedir)
- `dist/ogarniacz/OgarniaczUpdater.exe` - Updater executable

### 2. Build the Installer
```bash
python GENERATE_INSTALLER_EXE.py
```

This creates:
- `dist/OgarniaczInstaller.exe` - Standalone installer executable

### 3. Using the Installer

Run `dist/OgarniaczInstaller.exe` on any Windows machine. It will:
- Copy the application to `%LOCALAPPDATA%\OgarniaczSM\`
- Copy the updater executable
- Create a Start Menu shortcut
- Optionally pin to taskbar
- Launch the application

**Note:** The installer expects `dist/ogarniacz/OgarniaczSM/` to exist (from step 1).

---

## Complete Build & Publish Workflow

### Development Build
1. Build application: `python GENERATE_OGARNIACZ_EXE.py`
2. Build installer: `python GENERATE_INSTALLER_EXE.py`
3. Test installer: Run `dist/OgarniaczInstaller.exe`

### Publish New Version (for auto-updates)
1. Update version in `publish_update.bat` (line 5: `set VERSION=X.Y.Z`)
2. Build application: `python GENERATE_OGARNIACZ_EXE.py`
3. Publish: `publish_update.bat`
   - Copies to network share `Y:\Ogarniacz\`
   - Creates `latest.zip`
   - Updates `manifest.json`

---

## Requirements

### Python Packages
- `PyInstaller` - for building executables
- `PySide6` - Qt framework (already in requirements.txt)
- `pywin32` - for Windows COM (needed by installer for shortcuts)

Install with:
```bash
pip install pyinstaller pywin32
```

---

## File Structure After Build

```
dist/
├── ogarniacz/
│   ├── OgarniaczSM/           # Main app (onedir)
│   │   ├── OgarniaczSM.exe
│   │   └── _internal/         # PyInstaller runtime
│   └── OgarniaczUpdater.exe   # Updater (onefile)
└── OgarniaczInstaller.exe      # Installer (onefile)
```

---

## Troubleshooting

### Installer fails with "Brak builda ONEDIR"
- Make sure you ran `GENERATE_OGARNIACZ_EXE.py` first
- Check that `dist/ogarniacz/OgarniaczSM/` exists

### Installer fails to create shortcut
- Ensure `pywin32` is installed: `pip install pywin32`
- The installer will continue even if shortcut creation fails

### Installer EXE not created
- Check that PyInstaller is installed: `pip install pyinstaller`
- Verify `build_installer.py` exists in the project root

