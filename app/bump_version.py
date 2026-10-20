#!/usr/bin/env python3
"""
Increment version.txt by the smallest step (0.0.0.1).
Supports 1-4 numeric segments; increments the last segment.
"""
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parent
VERSION_FILE = ROOT / "version.txt"


def parse_version(text: str) -> list[int]:
    text = text.strip().split()[0] if text.strip() else ""
    if not text:
        return [0, 0, 0, 0]
    if not re.fullmatch(r"\d+(?:\.\d+){0,3}", text):
        return [0, 0, 0, 0]
    parts = [int(p) for p in text.split(".")]
    while len(parts) < 4:
        parts.append(0)
    return parts[:4]


def main() -> int:
    current = "0.0.0.0"
    if VERSION_FILE.exists():
        try:
            current = VERSION_FILE.read_text(encoding="utf-8").strip()
        except Exception:
            current = "0.0.0.0"

    parts = parse_version(current)
    parts[-1] += 1
    new_version = ".".join(str(p) for p in parts)

    try:
        VERSION_FILE.write_text(new_version + "\n", encoding="utf-8")
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    print(new_version)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

