from pathlib import Path
import sys
import os
import ctypes
import traceback

def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent

# ---------------- paths & config ----------------


BASE_DIR: Path = get_base_dir()

def find_config_path() -> Path:
    env = os.environ.get("OGARNIACZSM_CONFIG")
    if env and Path(env).exists():
        return Path(env)

    candidates = [
        BASE_DIR / "config.json",
        BASE_DIR.parent / "config.json",
        Path(r"Y:\instalki\_SKRYPTY WIKT\OgarniaczSM\config.json"),
    ]

    for p in candidates:
        if p.exists():
            return p

    # fallback – zwróć pierwszego kandydata, a błąd pokażemy już w GUI
    return candidates[0]

try:
    CONFIG_PATH: Path = find_config_path()
except Exception as e:
    msg = "Cannot locate config.json:\n\n" + str(e) + "\n\n" + traceback.format_exc()
    try:
        ctypes.windll.user32.MessageBoxW(0, msg, "OgarniaczSM – config error", 0x10)
    except Exception:
        pass
    sys.exit(1)



def resolve_rel_to_config(p: str) -> str:
    if not p:
        return ""
    P = Path(p)
    if P.is_absolute():
        return str(P)
    return str((CONFIG_PATH.parent / P).resolve())