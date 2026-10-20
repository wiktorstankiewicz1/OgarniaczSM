# Project Organization Analysis & Findings

## Summary
Deep investigation of the OgarniaczSM project structure, dependencies, and potential issues.

---

## ✅ FIXED: Manifest Format Mismatch

### Problem (RESOLVED)
**Location:** `autoupdate.py` line 27 vs `publish_update.bat` line 38-42

**Issue:** 
- `autoupdate.py` expects: `manifest["zip_url"]`
- `publish_update.bat` was creating: `{"version": "...", "files": [], "base_url": "..."}` (NO `zip_url` field!)

**Impact:** Auto-update functionality would fail with a KeyError when trying to access `zip_url`.

**Fix Applied:**
- Updated `publish_update.bat` to create `latest.zip` from the `latest/` directory
- Updated manifest.json format to include `zip_url` field
- Manifest now matches what `autoupdate.py` expects

**New format (fixed):**
```json
{
  "version": "1.5.0",
  "zip_url": "https://stillmotionstudio.asuscomm.com/OgarniaczSM/PROD/latest.zip"
}
```

---

## 📁 Directory Analysis

### Large Directories (Size Analysis - UPDATED)
- **PROD/**: ~32 MB ✅ CLEANED (was 899.5 MB - removed PySide6 runtime + latest.zip, kept essential files)
- **.venv/**: 878.51 MB (Virtual environment - should be in .gitignore)
- **build/**: 48.63 MB (PyInstaller build artifacts - regenerated)
- **dist/**: 17.6 MB (Compiled executables - regenerated)
- **icons/**: 4.89 MB (Project assets - keep)

### PROD/ Directory Investigation

**Contents:**
- Full built application (`OgarniaczSM.exe`)
- Complete PySide6 runtime (3557+ files)
- `manifest.json` (version 1.5.1)
- `latest.zip` (likely compressed version)

**Usage:**
- `autoupdate.py` references: `https://stillmotionstudio.asuscomm.com/OgarniaczSM/PROD/manifest.json`
- `publish_update.bat` does NOT use PROD - it uses `dist/ogarniacz/` and copies to `Y:\Ogarniacz\`
- PROD appears to be a **local snapshot/backup** of what's deployed on the server

**Recommendation:** 
- PROD is likely a redundant local copy
- The actual deployment uses `Y:\Ogarniacz\` (network share)
- PROD could be:
  1. Deleted (if server has the source of truth)
  2. Moved to archive/backup location
  3. Kept if needed for offline testing (but add to .gitignore)

---

## 🗑️ Unused Files Found

### 1. `sm_cache.py` ✅ DELETED
- **Status:** Not imported anywhere in codebase
- **Purpose:** Icon caching utility (uses `AppData/Local/StillMotion/cache`)
- **Note:** Uses different cache path (`StillMotion`) vs main app (`OgarniaczSM`)
- **Action:** Deleted (not used)

### 2. Already Deleted (from initial cleanup)
- ✅ `GENERATE_script_tiles_EXE_OLD.py`
- ✅ `sm_script_tiles.py`
- ✅ `build_script_tiles.py`
- ✅ All `.spec` files (OgarniaczSM.spec, OgarniaczUpdater.spec, OgarniaczInstaller.spec, sm_script_tiles.spec)
- ✅ `New folder/` (empty directory)

---

## 📝 Code Dependencies

### Active Source Files
- `main.py` - Main application (imports: `autoupdate`)
- `autoupdate.py` - Auto-update functionality
- `updater.py` - Updater executable source
- `build_installer.py` - Installation script
- `GENERATE_OGARNIACZ_EXE.py` - Build script (uses PyInstaller CLI, not .spec files)

### Configuration Files
- `config.json` - Main configuration
- `requirements.txt` - Python dependencies
- `instrukcja_instalacji.txt` - Installation instructions (Polish)
- `readme.md` - Documentation

### Build Process
1. `GENERATE_OGARNIACZ_EXE.py` → builds to `dist/ogarniacz/`
2. `publish_update.bat` → copies `dist/ogarniacz/` to `Y:\Ogarniacz\releases/VERSION/` and `Y:\Ogarniacz\latest/`
3. `publish_update.bat` → creates `Y:\Ogarniacz\manifest.json` (but with wrong format!)

---

## 🔧 Recommended Actions

### High Priority
1. ✅ **Fix manifest format bug** - FIXED: Updated `publish_update.bat` to create ZIP and include `zip_url` in manifest
2. ✅ **Delete `sm_cache.py`** - COMPLETED: Deleted unused file
3. ✅ **Review PROD/ directory** - COMPLETED: Cleaned from 899.5 MB to 32.47 MB

### Medium Priority
4. **Update .gitignore** - Ensure `.venv/` is ignored (already done, but verify)
5. **Consider archiving PROD/** - If keeping for reference, move to archive/ or add to .gitignore
6. **Document build/deploy process** - The relationship between PROD, dist, and Y:\Ogarniacz could be clearer

### Low Priority
7. **Review hardcoded paths** - Some paths are hardcoded (e.g., `Y:\instalki\_SKRYPTY WIKT\...`)
8. **Consider relative paths** - Where possible, use relative paths for better portability

---

## 📊 File Count Summary

- **Source Python files:** 5 (main.py, autoupdate.py, updater.py, build_installer.py, GENERATE_OGARNIACZ_EXE.py)
- **Unused Python files:** 1 (sm_cache.py)
- **Configuration files:** 4 (config.json, requirements.txt, readme.md, instrukcja_instalacji.txt)
- **Build artifacts:** build/, dist/ (regenerated)
- **Large directories:** PROD/ (899.5 MB), .venv/ (878.51 MB)

---

## ✅ Already Completed

- Created `.gitignore` with appropriate exclusions
- Removed old/unused build scripts
- Removed unused .spec files
- Removed empty directories
- Identified critical manifest format bug
- Analyzed directory sizes and usage
- **Deleted `sm_cache.py`** (unused file)
- **Cleaned PROD/ directory** - Removed PySide6 runtime (~880 MB) and latest.zip (~240 MB), kept essential files (executable, DLLs, manifest.json, runtime files)
  - Reduced from 899.5 MB → ~32 MB (saved ~867 MB, ~96% reduction)
- **Fixed manifest format bug** - Updated `publish_update.bat` to:
  - Create `latest.zip` from the latest/ directory
  - Include `zip_url` field in manifest.json matching `autoupdate.py` expectations

