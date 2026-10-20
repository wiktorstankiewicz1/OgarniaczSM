# Quick Setup: Bundle VC++ Redistributable

## One-Time Setup (5 minutes)

1. **Download VC++ Redistributable:**
   - Go to: https://aka.ms/vs/17/release/vc_redist.x64.exe
   - Save it in your project root as `vc_redist.x64.exe`

2. **Rebuild Installer:**
   ```bash
   python GENERATE_INSTALLER_EXE.py
   ```

That's it! The installer will now automatically install VC++ Redistributables if needed.

## What Happens Now

When someone runs `OgarniaczInstaller.exe`:

1. ✅ Checks if VC++ Redistributables are installed
2. ✅ If missing → automatically installs them silently
3. ✅ Installs the app
4. ✅ App works immediately (no DLL errors!)

## File Location

```
OgarniaczSM/
├── vc_redist.x64.exe    ← Download and place here
├── build_installer.py
├── GENERATE_INSTALLER_EXE.py
└── ...
```

## Size Impact

- VC++ Redistributable: ~25 MB
- Installer EXE will be ~25 MB larger
- **Worth it:** Eliminates DLL errors on all PCs

## Optional: Skip Bundling

If you don't want to bundle it:
- Don't place `vc_redist.x64.exe` in project root
- Installer will prompt users to install manually
- They'll need to download it themselves

**Recommendation:** Bundle it for the best user experience.













