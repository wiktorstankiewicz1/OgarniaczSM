# Testing Auto-Update

## How Auto-Update Works

Auto-update **only triggers when remote version > local version**

So if you have:
- Installed app: `0.5.1.6`
- Published version: `0.5.1.6`
- **Result:** No update (versions are equal)

You need:
- Installed app: `0.5.1.6`
- Published version: `0.5.1.7` (or higher)
- **Result:** Auto-update triggers! ✅

---

## Testing Steps

1. **Check current installed version:**
   ```powershell
   Get-Content "$env:LOCALAPPDATA\OgarniaczSM\version.json"
   ```

2. **Increment version.txt:**
   - If installed is `0.5.1.6`, change `version.txt` to `0.5.1.7`

3. **Publish:**
   ```bash
   publish.bat
   ```

4. **Restart the installed app:**
   - Close it completely
   - Reopen it
   - It should auto-update and show the new version!

---

## Why `fix_version.py` "Worked"

`fix_version.py` fixed the corrupted version.json (removed "hehe" part), but it set it to match `version.txt`. Since both are now the same version, auto-update won't trigger until you increment the version and publish again.

