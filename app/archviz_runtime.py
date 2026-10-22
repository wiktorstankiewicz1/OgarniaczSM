"""Build identity shared by the packaged Archviz view and its worker."""
import json
import os
from pathlib import Path
import sys


def build_identity():
    metadata = Path(__file__).resolve().parent / "build_info.json"
    data = json.loads(metadata.read_text(encoding="utf-8")) if metadata.is_file() else {}
    return {"mode": "frozen" if getattr(sys, "frozen", False) else "source",
            "version": data.get("version"), "commit": data.get("commit")}


def runtime_info():
    return {"build": build_identity(), "pid": os.getpid(), "executable": sys.executable}


def compatible_service(info):
    expected = build_identity()
    return bool(info and info.get("service") == "archviz-studio" and
                (expected["mode"] != "frozen" or
                 (expected.get("commit") and info.get("build") == expected)))
