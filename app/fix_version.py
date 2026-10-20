#!/usr/bin/env python3
"""
Quick script to fix invalid version.json in installed app.
Run this if your installed app has an invalid version format.
"""
import json
import sys
from pathlib import Path

APP_DIR = Path.home() / "AppData" / "Local" / "OgarniaczSM"
VERSION_FILE = APP_DIR / "version.json"

# Read version from version.txt in project root
PROJECT_ROOT = Path(__file__).parent
VERSION_TXT = PROJECT_ROOT / "version.txt"

if not VERSION_TXT.exists():
    print(f"ERROR: version.txt not found at {VERSION_TXT}")
    sys.exit(1)

# Read current version from version.txt
try:
    version = VERSION_TXT.read_text(encoding="utf-8").strip().splitlines()[0].strip()
    # Only take the first token (in case there's extra text)
    version = version.split()[0] if version else "0.0.0"
except Exception as e:
    print(f"ERROR reading version.txt: {e}")
    sys.exit(1)

# Ensure version.json exists
if not APP_DIR.exists():
    print(f"ERROR: App directory not found: {APP_DIR}")
    print("Make sure the app is installed first!")
    sys.exit(1)

# Write clean version.json
VERSION_FILE.write_text(json.dumps({"version": version}), encoding="utf-8")
print(f"OK - Fixed version.json with version: {version}")
print(f"  Location: {VERSION_FILE}")

