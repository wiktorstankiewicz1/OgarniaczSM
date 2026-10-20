# autoupdate.py
from __future__ import annotations

import json
import sys
import time
import subprocess
from pathlib import Path
from threading import Thread
from urllib.request import Request, urlopen

try:
    from packaging import version as pkg_version
except Exception:
    class _V:
        @staticmethod
        def parse(s: str):
            parts = []
            for x in str(s).replace("-", ".").split("."):
                if x.isdigit():
                    parts.append(int(x))
                else:
                    # obetnij np. "1rc1" -> 1
                    n = "".join([c for c in x if c.isdigit()])
                    if n:
                        parts.append(int(n))
            return tuple(parts)
    pkg_version = _V()

APP_NAME = "OgarniaczSM"
DEFAULT_MANIFEST_URL = "https://stillmotionstudio.asuscomm.com/OgarniaczSM/PROD/latest/manifest.json"

def _base_dir() -> Path:
    # działa i w .py i w exe (PyInstaller)
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent

BASE_DIR = _base_dir()

# gdzie trzymamy lokalną wersję (obok exe)
LOCAL_VERSION_FILE = BASE_DIR / "version.json"

# updater.exe musi być obok exe (instalator ma go kopiować)
UPDATER_EXE = BASE_DIR / "OgarniaczUpdater.exe"

def _read_local_version() -> str:
    if LOCAL_VERSION_FILE.exists():
        try:
            return json.loads(LOCAL_VERSION_FILE.read_text(encoding="utf-8")).get("version", "0.0.0")
        except Exception:
            return "0.0.0"
    return "0.0.0"

def _write_local_version(v: str) -> None:
    try:
        LOCAL_VERSION_FILE.write_text(json.dumps({"version": v}), encoding="utf-8")
    except Exception:
        pass

def _fetch_json(url: str, timeout: int = 10) -> dict:
    req = Request(url, headers={"User-Agent": f"{APP_NAME}-Updater"})
    with urlopen(req, timeout=timeout) as r:
        data = r.read().decode("utf-8", errors="replace")
    return json.loads(data)

def _launch_updater_and_exit(manifest_url: str) -> None:
    if not UPDATER_EXE.exists():
        return

    # Uruchamiamy updater i zamykamy aplikację.
    # Updater sam pobierze ZIP i podmieni pliki.
    try:
        subprocess.Popen(
            [
                str(UPDATER_EXE),
                "--manifest-url", manifest_url,
                "--install-dir", str(BASE_DIR),
                "--launch", str(BASE_DIR / f"{APP_NAME}.exe"),
            ],
            close_fds=True
        )
    except Exception:
        return

    # zamykamy bieżący proces, żeby updater mógł nadpisać pliki
    raise SystemExit(0)

def check_for_updates_once(manifest_url: str = DEFAULT_MANIFEST_URL) -> None:
    try:
        man = _fetch_json(manifest_url)
        remote_v = str(man.get("version", "0.0.0"))
        local_v = _read_local_version()

        if pkg_version.parse(remote_v) > pkg_version.parse(local_v):
            _launch_updater_and_exit(manifest_url)
    except Exception:
        # nie blokujemy startu apki
        return

def start_periodic_update_check(interval_seconds: int = 900, manifest_url: str = DEFAULT_MANIFEST_URL) -> None:
    def worker():
        # mała zwłoka po starcie, żeby UI się pojawił szybko
        time.sleep(5)
        while True:
            try:
                check_for_updates_once(manifest_url=manifest_url)
            except Exception:
                pass
            time.sleep(interval_seconds)

    Thread(target=worker, daemon=True).start()
