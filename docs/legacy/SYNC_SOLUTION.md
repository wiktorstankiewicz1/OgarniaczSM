# Solution for Synology Drive Sync with PROD Folder

## Your Setup
- **Your laptop:** Synology Drive syncs to `Y:\` (mapped drive)
- **Office PCs:** `Y:\` mapped directly to Synology NAS
- **Problem:** `PROD/_internal/` is 619 MB (3713 files) that syncs every time

## Best Solution: Exclude _internal from Sync + Shared Runtime

Since `_internal/` is identical across all versions, we can:

1. **Exclude `PROD/*/` from Synology Drive sync** (use pattern matching)
2. **Create a shared runtime folder** that syncs once: `PROD/runtime/`
3. **Build app to reference shared runtime** (requires PyInstaller changes)

**BUT** - This requires significant changes to how PyInstaller works. Not practical.

---

## Practical Solution: Selective Sync for _internal Only

Since you need PROD to sync, but _internal is the problem:

### Option A: Exclude _internal from Sync (Recommended)

Use Synology Drive's selective sync to exclude `_internal/` folders:

**In Synology Drive Client:**
1. Settings → Advanced → Selective Sync
2. Add exclusion pattern: `**/_internal/`

**Problem:** App won't work if _internal is missing!

**Solution:** This won't work - we need _internal for the app to run.

---

## Actual Best Solution: Accept the Sync + Optimize Build

Since PyInstaller's `--collect-all PySide6` includes everything, and we can't easily exclude parts of it, the most practical solutions are:

### 1. Use Synology Drive's Incremental Sync (Should Already Work)
- Synology Drive should only sync changed files
- If _internal is identical, it should detect this
- **But** it still scans all files, which can be slow

### 2. Optimize Build Process (Limited Impact)
- Create spec file with `--exclude-module` for unused Qt modules
- May reduce files by 10-30%, not 90%
- Worth trying, but won't solve the core problem

### 3. Change Architecture (Complex but Best Long-term)
- Separate runtime package (sync once)
- App executable only (syncs frequently)
- Requires restructuring updater and build process

---

## Recommended: Hybrid Approach

1. **Short-term:** Try build optimization (spec file)
   - May reduce files by 20-40%
   - Easy to implement
   - Low risk

2. **Accept the sync time:**
   - Since _internal is identical, Synology Drive should use delta sync
   - First sync is slow, subsequent syncs should be faster
   - Consider syncing PROD only during off-hours

3. **Long-term consideration:** 
   - If sync becomes unbearable, consider restructuring to separate runtime
   - Or use a different deployment method (HTTP download instead of SMB copy)

---

## Quick Test: Check if Delta Sync is Working

Check if Synology Drive is actually re-syncing unchanged files:

1. Note the sync time for a new version
2. Publish another version with NO code changes (just version number)
3. Check sync time - should be much faster if delta sync works

If sync time is the same, Synology Drive might not be using delta sync properly, which is a separate issue.

