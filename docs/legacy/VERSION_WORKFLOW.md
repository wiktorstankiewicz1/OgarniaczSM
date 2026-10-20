# Version Management & Update Workflow

## Overview

Your app has **two ways to distribute updates**:
1. **Installer** - For NEW installations (first-time users)
2. **Auto-update** - For EXISTING installations (automatic updates)

---

## Two Update Paths

### 1. New Installer (For New Users)
**When:** Only when you need to distribute to completely new computers/users
- **Action:** Rebuild installer with new version
- **Users:** New installations get the latest version immediately
- **Workflow:**
  1. Update `version.txt`
  2. Build: `python GENERATE_OGARNIACZ_EXE.py`
  3. Build installer: `python GENERATE_INSTALLER_EXE.py`
  4. Distribute `dist/OgarniaczInstaller.exe` to new users

### 2. Auto-Update (For Existing Users) ⭐ RECOMMENDED
**When:** Most common - updating users who already have the app installed
- **Action:** Publish update to server
- **Users:** Automatically get updated within 15 minutes (or immediately on next launch)
- **Workflow:**
  1. Update `version.txt` (e.g., change `0.5.1.1` to `0.5.1.2`)
  2. Build: `python GENERATE_OGARNIACZ_EXE.py`
  3. Publish: `publish_update.bat`
  4. Done! Users auto-update automatically

---

## Complete Update Workflow (Recommended)

### Step 1: Update Version
Edit `version.txt` and change the version number:
```
0.5.1.1  →  0.5.1.2
```

### Step 2: Make Your Code Changes
Edit your Python files (`main.py`, `autoupdate.py`, etc.)

### Step 3: Build the Application
```bash
python GENERATE_OGARNIACZ_EXE.py
```
This creates `dist/ogarniacz/OgarniaczSM/` with your new code

### Step 4: Publish Update
```bash
publish_update.bat
```
This will:
- Read version from `version.txt`
- Copy build to network share `Y:\Ogarniacz\latest\`
- Create `latest.zip` for downloads
- Update `manifest.json` with new version and zip URL

### Step 5: Users Get Updated Automatically
- Running apps check every 15 minutes (900 seconds)
- New launches check immediately on startup
- If update found → app closes → updater downloads & installs → app restarts

---

## When to Create a New Installer

**Only rebuild the installer when:**
- Distributing to brand new computers/users
- The installer itself needs changes (installer script updates)
- You want a "fresh start" package

**You DON'T need a new installer for:**
- Regular app updates (use auto-update)
- Bug fixes and feature additions
- Version bumps

---

## Testing Auto-Update Locally

To test the update system:

1. **Install the app** (using installer) - gets initial version
2. **Make a change** and update `version.txt`
3. **Build & publish** using `publish_update.bat`
4. **Wait up to 15 minutes** or restart the app manually - it should update automatically

### Manual Update Check (Optional)

You can add a "Check for Updates" button if needed, but currently updates are:
- Checked on app startup
- Checked every 15 minutes while running
- Silent (no user interruption)

---

## Version Number Format

The version system uses semantic versioning (`packaging.version` module):
- Valid: `1.0.0`, `0.5.1.1`, `2.3.4`, `1.0.0-beta1`
- Invalid: `v1.0.0` (no "v" prefix), `1.0` (should be `1.0.0`)

**Current version:** `0.5.1.1` (in `version.txt`)

---

## Summary

**For regular updates:** 
```
Edit code → Update version.txt → Build → publish_update.bat → Done!
```

**For new installations:**
```
Update version.txt → Build → Build installer → Distribute installer.exe
```

**Auto-update happens automatically** - no user action required! 🎉

