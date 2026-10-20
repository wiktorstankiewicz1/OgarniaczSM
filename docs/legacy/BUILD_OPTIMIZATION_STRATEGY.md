# Build Optimization Strategy for Synology Drive Sync

## Problem
- Your laptop: Synology Drive syncs to `Y:\` (mapped drive)
- Office PCs: `Y:\` mapped directly to Synology NAS
- `PROD/_internal/` contains PySide6 (619.73 MB, 3713 files)
- Every new version syncs all files, causing sync issues

## Strategy Options

### Option 1: Exclude _internal from Sync (Recommended but Complex)
**Concept:** Sync only the executable and version files, share _internal once via a separate mechanism.

**Pros:**
- Dramatically reduces sync load
- _internal folder is identical across versions

**Cons:**
- Requires restructuring the update mechanism
- Complex to implement

---

### Option 2: Optimize PyInstaller Build (Partially Effective)
**Concept:** Exclude unused Qt modules using PyInstaller spec file.

**Limitations:**
- `--collect-all PySide6` includes everything by default
- Can exclude some modules, but not all
- Might save 10-30% of files, not 90%

**Implementation:** Create custom spec file with excludes for:
- QtQuick, QtQml, QtWebEngine (if not used)
- Qt3D modules
- QtMultimedia (if not used)
- QtCharts, QtLocation, etc.

---

### Option 3: Use Symlinks/Hardlinks (Not Practical)
**Concept:** Create symlinks/hardlinks between versions to share _internal.

**Limitations:**
- Windows/SMB doesn't support cross-directory hardlinks well
- Symlinks require special permissions
- Synology Drive may not handle them correctly

---

### Option 4: Separate Dependencies Package (Best Long-term)
**Concept:**
1. Create a "runtime" package with PySide6 once (sync once)
2. Build app executable separately (small, changes frequently)
3. Installer/updater references shared runtime

**Pros:**
- Only sync executable + small files for updates
- Runtime syncs once, then rarely

**Cons:**
- Requires significant restructuring
- Need to modify updater to handle shared runtime

---

### Option 5: Incremental Sync (Synology Drive Feature)
**Concept:** Use Synology Drive's "block-level sync" if available.

**Reality:**
- Synology Drive should only sync changed files
- But with thousands of files, it still scans everything
- May not solve the core problem

---

## Recommended Approach: Hybrid

1. **Short-term:** Try Option 2 (spec file optimization)
   - Create spec file to exclude unused Qt modules
   - May reduce files by 20-40%
   - Easy to implement

2. **Long-term:** Consider Option 4 (separate runtime)
   - Create `PROD/runtime/` with PySide6 (sync once)
   - Build executable separately
   - Update mechanism references shared runtime
   - Only sync executable for updates

---

## Next Steps

Let's try Option 2 first (spec file optimization) - it's the quickest win with minimal risk.

