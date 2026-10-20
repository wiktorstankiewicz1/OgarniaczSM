#!/usr/bin/env python3
"""Helper script to create manifest.json correctly"""
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
VERSION_FILE = SCRIPT_DIR / "version.txt"
SHARE = SCRIPT_DIR / "PROD"
MANIFEST_FILE = SHARE / "manifest.json"

# Read version
version = "0.5.1.1"
if VERSION_FILE.exists():
    try:
        version = VERSION_FILE.read_text(encoding="utf-8").strip().splitlines()[0].strip().split()[0]
    except Exception:
        pass

# Create manifest with forward slashes for paths (JSON standard)
src_path = str(SHARE / "latest").replace("\\", "/")
manifest = {
    "version": version,
    "src_path": src_path
}

# Ensure PROD directory exists
SHARE.mkdir(parents=True, exist_ok=True)

# Write manifest
MANIFEST_FILE.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
print(f"Created manifest.json: {MANIFEST_FILE}")
print(f"Version: {version}")
print(f"Source path: {src_path}")

