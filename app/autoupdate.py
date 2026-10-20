import json, os, subprocess, threading, time
from packaging import version as pkg_version
from pathlib import Path

# Manifest z shared drive (Y: jest dostępny dla wszystkich komputerów)
MANIFEST_PATH = Path(r"Y:\Instalki\_SKRYPTY WIKT\OgarniaczSM\PROD\manifest.json")

APP_DIR = Path(os.getenv("LOCALAPPDATA")) / "OgarniaczSM"
LOCAL_VERSION = APP_DIR / "version.json"
UPDATER_EXE = APP_DIR / "OgarniaczUpdater.exe"
APP_EXE = APP_DIR / "OgarniaczSM.exe"
LOG_FILE = APP_DIR / "autoupdate.log"

def _log(msg: str):
    try:
        APP_DIR.mkdir(parents=True, exist_ok=True)
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(f"[{ts}] {msg}\n")
    except Exception:
        pass

def _get_local_version() -> str:
    try:
        return json.loads(LOCAL_VERSION.read_text(encoding="utf-8")).get("version", "0.0.0")
    except Exception:
        return "0.0.0"

def _get_remote_manifest() -> dict:
    if not MANIFEST_PATH.exists():
        _log(f"manifest path not found: {MANIFEST_PATH}")
        raise FileNotFoundError(f"Manifest not found: {MANIFEST_PATH}")
    try:
        content = MANIFEST_PATH.read_text(encoding="utf-8")
        manifest = json.loads(content)
        _log(f"manifest loaded successfully from {MANIFEST_PATH}")
        return manifest
    except Exception as e:
        _log(f"failed to read/parse manifest: {e}")
        raise

def check_for_updates_once(silent: bool = True):
    try:
        manifest = _get_remote_manifest()
        remote_ver = str(manifest["version"]).strip()
        src_path_raw = str(manifest.get("src_path", "")).strip()  # lokalna ścieżka do katalogu latest
        # Normalize path: convert forward slashes to backslashes, handle case
        src_path = str(Path(src_path_raw.replace("/", "\\"))) if src_path_raw else ""
        local_ver = _get_local_version()
        _log(f"manifest version={remote_ver} src_path={src_path}")
        _log(f"local version={local_ver} updater_exists={UPDATER_EXE.exists()} app_dir={APP_DIR}")

        remote_parsed = pkg_version.parse(remote_ver)
        local_parsed = pkg_version.parse(local_ver)
        _log(f"version comparison: remote={remote_ver} ({remote_parsed}) > local={local_ver} ({local_parsed}) = {remote_parsed > local_parsed}")

        if remote_parsed > local_parsed:
            src_path_obj = Path(src_path) if src_path else None
            if not src_path or not src_path_obj or not src_path_obj.exists():
                _log(f"src_path missing or not accessible: {src_path} (exists={src_path_obj.exists() if src_path_obj else False})")
                if not silent:
                    raise FileNotFoundError(f"Source path not found: {src_path}")
                return

            updater_to_use = UPDATER_EXE if UPDATER_EXE.exists() else (src_path_obj / "OgarniaczUpdater.exe")
            if not updater_to_use.exists():
                _log(f"updater missing: {updater_to_use} (exists={updater_to_use.exists()})")
                if not silent:
                    raise FileNotFoundError(f"Updater not found: {updater_to_use}")
                return

            args = [
                str(updater_to_use),
                "--src", str(src_path_obj),  # Use normalized Path object
                "--dst", str(APP_DIR),
                "--launch", str(APP_EXE),
                "--version", remote_ver
            ]
            _log(f"launching updater: {args}")
            subprocess.Popen(args, cwd=str(updater_to_use.parent))
            os._exit(0)  # natychmiast kończymy proces aplikacji – updater przejmie ster
        else:
            _log(f"no update needed: local version ({local_ver}) >= remote version ({remote_ver})")
    except Exception as e:
        import traceback
        _log(f"update check failed: {e}\n{traceback.format_exc()}")
        # cicho ignorujemy – sprawdzimy ponownie cyklicznie
        if not silent:
            raise

def _loop(interval_seconds: int):
    while True:
        check_for_updates_once(silent=True)
        time.sleep(interval_seconds)

def start_periodic_update_check(interval_seconds: int = 900):
    t = threading.Thread(target=_loop, args=(interval_seconds,), daemon=True)
    t.start()
