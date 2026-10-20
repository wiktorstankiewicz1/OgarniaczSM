# Quick Build Guide

## Build the Installer (After Code Changes)

After making changes to `build_installer.py`, you need to rebuild the installer EXE:

### Step 1: Build the Application
```bash
python GENERATE_OGARNIACZ_EXE.py
```
This creates `dist/ogarniacz/OgarniaczSM/` (required by installer)

### Step 2: Rebuild the Installer
```bash
python GENERATE_INSTALLER_EXE.py
```
This creates `dist/OgarniaczInstaller.exe` with the updated code

### Step 3: Test the Installer
Run `dist/OgarniaczInstaller.exe`

The installer will look for files in `dist/ogarniacz/` relative to where the installer EXE is located.

---

## Important Notes

- The installer EXE must be in the same directory structure as the built app
- Recommended distribution structure:
  ```
  OgarniaczInstaller.exe
  ogarniacz/
    OgarniaczSM/
      OgarniaczSM.exe
      _internal/
    OgarniaczUpdater.exe
  ```
- The installer finds files relative to its own location
- When running the installer EXE, make sure the `ogarniacz/` folder is in the same directory

