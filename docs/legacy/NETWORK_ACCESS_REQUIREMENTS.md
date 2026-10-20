# Network Access Requirements

## Folders Other Computers Need Access To

For the app to work correctly (including auto-update), other computers need **READ access** to:

### 1. Auto-Update (Required)
```
Y:\Instalki\_SKRYPTY WIKT\OgarniaczSM\PROD\
```
**Why:** 
- Auto-update reads `PROD\manifest.json` to check for new versions
- Auto-update copies files from `PROD\latest\` when updating

**Minimum required:**
- `PROD\manifest.json` (read)
- `PROD\latest\` (read - entire directory)

---

### 2. App Configuration (Required)
```
Y:\Instalki\_SKRYPTY WIKT\OgarniaczSM\config.json
```
**Why:** The app reads its configuration from this file (tiles, icons, scripts folder, etc.)

---

### 3. Icons & Resources (Required)
```
Y:\Instalki\_SKRYPTY WIKT\OgarniaczSM\icons\
```
**Why:** `config.json` references icons from this folder (e.g., `Y:/instalki/_SKRYPTY WIKT/OgarniaczSM/icons/projects.png`)

---

## Summary

**Other computers need READ access to:**
1. ✅ `Y:\Instalki\_SKRYPTY WIKT\OgarniaczSM\PROD\` (entire folder)
2. ✅ `Y:\Instalki\_SKRYPTY WIKT\OgarniaczSM\config.json`
3. ✅ `Y:\Instalki\_SKRYPTY WIKT\OgarniaczSM\icons\` (entire folder)

**They do NOT need access to:**
- ❌ `dist/` (build output - not needed)
- ❌ `build/` (build artifacts - not needed)
- ❌ Source code (`.py` files - not needed)
- ❌ `version.txt` (only used during publishing)

---

## Setting Up Network Permissions

### Windows File Sharing:
1. Right-click on `Y:\Instalki\_SKRYPTY WIKT\OgarniaczSM\PROD\`
2. Properties → Sharing → Share
3. Add users/computers with **Read** permissions

Repeat for:
- `config.json` (or share the parent folder)
- `icons\` folder

### Or Share the Entire Project Folder:
If easier, you can share the entire `Y:\Instalki\_SKRYPTY WIKT\OgarniaczSM\` folder with **Read** access. The app will work fine, though other computers won't need access to source code.

---

## Testing Access

On another computer, verify access:
```powershell
# Test manifest access
Test-Path "Y:\Instalki\_SKRYPTY WIKT\OgarniaczSM\PROD\manifest.json"

# Test config access
Test-Path "Y:\Instalki\_SKRYPTY WIKT\OgarniaczSM\config.json"

# Test icons access
Test-Path "Y:\Instalki\_SKRYPTY WIKT\OgarniaczSM\icons\projects.png"
```

All should return `True` if access is configured correctly.


