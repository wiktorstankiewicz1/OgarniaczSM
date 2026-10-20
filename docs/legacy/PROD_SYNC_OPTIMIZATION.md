# PROD Folder Sync Optimization

## Problem
The `PROD/_internal/` folder contains PySide6 (619.73 MB, 3713 files) which is identical across all versions. This causes Synology Drive to sync thousands of files for each new release, potentially crashing or slowing down sync.

## Solution: Exclude PROD from Synology Drive Sync

Since `Y:\` is a **network share** (not a synced folder), other computers access `PROD/` directly over the network. **You don't need Synology Drive to sync it!**

### Steps to Exclude PROD from Synology Drive:

1. **Open Synology Drive Client**
2. **Go to Settings → Advanced → Selective Sync**
3. **Add exclusion rule:**
   ```
   PROD/
   ```
   Or use pattern:
   ```
   **/PROD/**
   ```

### Why This Works:
- ✅ `Y:\Instalki\_SKRYPTY WIKT\OgarniaczSM\PROD\` is on a network share
- ✅ Other computers access it directly via `Y:\` drive mapping
- ✅ Auto-update reads from the network path (no sync needed)
- ✅ Synology Drive doesn't need to sync it

---

## Alternative: Manual Sync Script (if needed)

If you need to copy PROD to another location that IS synced, create a script to sync only when publishing:

### `sync_prod_only.bat` (optional)
```batch
@echo off
REM Only sync PROD folder (not the entire project)
robocopy "Y:\Instalki\_SKRYPTY WIKT\OgarniaczSM\PROD" "C:\Synced\OgarniaczSM\PROD" /MIR /R:3 /W:5
```

**But this is NOT necessary** - just exclude PROD from Synology Drive sync!

---

## Why PySide6 Can't Be Shared Separately

PyInstaller bundles PySide6 into the `_internal/` folder as part of the executable. The app expects all dependencies in `_internal/`. We can't easily:
- Share PySide6 from a common location (breaks PyInstaller's model)
- Download PySide6 during updates (complex, error-prone)
- Split dependencies from the app (requires major restructuring)

**The `_internal` folder is required** for the app to run. However, since it's on a network share, other computers can access it directly without syncing.

---

## Expected Result

After excluding `PROD/` from Synology Drive:
- ✅ Synology Drive only syncs source code, config, icons (small files)
- ✅ No more sync crashes from thousands of files
- ✅ Auto-update still works (other computers access PROD via network)
- ✅ New versions publish faster (no sync overhead)

---

## What SHOULD Be Synced

Keep syncing:
- ✅ Source code (`.py` files)
- ✅ `config.json`
- ✅ `icons/` folder
- ✅ `version.txt`
- ✅ Build scripts (`GENERATE_*.py`, `publish.bat`, etc.)
- ✅ Documentation

**Don't sync:**
- ❌ `PROD/` (network accessible, no sync needed)
- ❌ `dist/` (build output, regeneratable)
- ❌ `build/` (build artifacts, regeneratable)
- ❌ `*.spec` (PyInstaller spec files, auto-generated)

---

## Verification

After excluding PROD, verify auto-update still works:
1. On another computer, check access:
   ```powershell
   Test-Path "Y:\Instalki\_SKRYPTY WIKT\OgarniaczSM\PROD\manifest.json"
   ```
   Should return `True`

2. Run the installed app - auto-update should work normally (it reads from network path)

---

## Summary

**Best solution:** Exclude `PROD/` from Synology Drive sync. Other computers access it directly via the network share, so sync is unnecessary.

This is the simplest and most reliable solution - no code changes needed!

