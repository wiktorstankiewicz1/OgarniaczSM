# Practical Solution for Synology Drive Sync

## The Real Issue

Since `Y:\` on your laptop is Synology Drive (syncing to NAS), and office PCs access `Y:\` directly from NAS, you need `PROD/` to sync. The `_internal/` folder (619 MB, 3713 files) is identical across versions but still syncs.

## The Problem with PyInstaller

PyInstaller's `--collect-all PySide6` includes **everything** - all Qt modules, even unused ones. Your app only uses:
- QtCore
- QtGui  
- QtWidgets

But PySide6 includes 50+ modules (QtQuick, QtWebEngine, Qt3D, etc.) that you don't use.

## Practical Solutions (Ranked by Ease)

### Option 1: Use Synology Drive's Delta Sync (Should Already Work)

Synology Drive **should** only sync changed files. Since `_internal/` is identical across versions:
- First sync: Slow (619 MB)
- Subsequent syncs: Should be fast (only changed files)

**Test this:**
1. Publish version 1.0
2. Note sync time
3. Publish version 1.1 (same code, just version bump)
4. Check sync time - should be much faster

If sync time is the same, Synology Drive might not be using delta sync properly.

---

### Option 2: Optimize Build with Spec File (Moderate Impact)

Create a spec file that excludes unused Qt modules. This won't remove everything (PyInstaller's limitation), but may reduce files by 20-40%.

**Limitation:** `--collect-all PySide6` still includes most files, but we can exclude some modules from analysis.

**Impact:** Moderate (20-40% reduction, not 90%)

---

### Option 3: Exclude _internal from Sync + Shared Runtime (Complex)

1. Exclude `PROD/*/_internal/` from sync
2. Create `PROD/runtime/` with PySide6 (sync once)
3. Modify app to use shared runtime

**Problem:** Requires major changes to PyInstaller build and app structure.

**Impact:** High (90%+ reduction), but complex

---

### Option 4: Use On-Demand Sync (Synology Drive Feature)

Enable Synology Drive's "On-Demand Sync" for `PROD/`:
- Files sync only when accessed
- Office PCs access via NAS directly (no sync needed)
- Your laptop only syncs what you access

**Impact:** High (no sync overhead), but requires configuring on-demand sync

---

## Recommended Approach

1. **First:** Test if delta sync is working (Option 1)
   - If sync is fast for unchanged files, you're done!
   
2. **If not:** Try Option 2 (spec file optimization)
   - Moderate improvement, easy to implement
   
3. **If still problematic:** Consider Option 4 (on-demand sync)
   - Or accept the sync time (it's only 619 MB, should sync in minutes)

---

## Quick Win: Try On-Demand Sync First

Since office PCs access `Y:\` directly from NAS (not synced), you might be able to use On-Demand Sync:

1. In Synology Drive Client → Settings → Sync Rules
2. Enable "On-Demand Sync" for `PROD/`
3. Your laptop only downloads files when you access them
4. Office PCs access directly from NAS (no sync needed)

This might be the easiest solution!

