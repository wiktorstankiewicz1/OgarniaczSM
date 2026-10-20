# Quick Guide - Publishing Updates

## Which Script to Use?

### ✅ `publish.bat` - USE THIS ONE!
**All-in-one script:** Builds + Publishes
- Use this for ALL regular updates
- Just run: `publish.bat`

### `publish_update.bat` - Don't use directly
- Internal helper used by `publish.bat`
- You don't need to run this separately

---

## Workflow for Publishing Updates

1. **Update version.txt** (e.g., `0.5.1.3` → `0.5.1.4`)
2. **Run `publish.bat`** - that's it!
3. **Restart the installed app** to trigger auto-update

---

## Do You Need to Reinstall?

**NO!** Auto-update handles everything:
- Just run `publish.bat` after updating `version.txt`
- Close and reopen the installed app
- It will auto-update to the new version

**Only reinstall if:**
- Installing on a NEW computer/user
- Version.json gets corrupted (use `fix_version.py` to fix it)

---

## Testing Auto-Update

1. Change `version.txt` to a higher version
2. Run `publish.bat`
3. Close the installed app completely
4. Reopen it - should show the new version!

---

## Fixing Invalid Version

If your installed app has an invalid version (like "0.5.1.3hehe"), run:
```bash
python fix_version.py
```
This fixes the version.json with the current version from `version.txt`.

