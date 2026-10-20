from __future__ import annotations

import ast
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Set, Tuple

POPPLER_URL = "https://github.com/oschwartz10612/poppler-windows/releases/download/v24.07.0-0/Release-24.07.0-0.zip"


@dataclass(frozen=True)
class DepCheckResult:
    python_exe: Optional[str]
    missing_python: bool
    required_pip_packages: List[str]
    poppler_ok: Optional[bool]  # None if not needed/unknown


def _now_ts() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def find_python_exe() -> Optional[str]:
    """
    Best-effort discovery of a system python suitable for running external scripts.
    Priority:
    - PATH
    - common per-user installs
    - py launcher (Windows)
    - sys.executable if not frozen
    """
    py = shutil.which("python") or shutil.which("python3")
    if py:
        return py

    username = os.getenv("USERNAME", "")
    candidates = [
        rf"C:\Users\{username}\AppData\Local\Programs\Python\Python312\python.exe",
        rf"C:\Users\{username}\AppData\Local\Programs\Python\Python311\python.exe",
        rf"C:\Users\{username}\AppData\Local\Programs\Python\Python310\python.exe",
        r"C:\Program Files\Python312\python.exe",
        r"C:\Program Files\Python311\python.exe",
        r"C:\Program Files\Python310\python.exe",
        r"C:\Python312\python.exe",
        r"C:\Python311\python.exe",
        r"C:\Python310\python.exe",
    ]
    for c in candidates:
        if Path(c).exists():
            return c

    # Windows py launcher can give us a real python path; still return "py" as executable
    if shutil.which("py"):
        return "py"

    if not getattr(sys, "frozen", False) and sys.executable and Path(sys.executable).exists():
        return sys.executable

    return None


def infer_pip_packages_from_script(script_path: str) -> Tuple[Set[str], Set[str]]:
    """
    Returns (pip_packages, external_tools) inferred from imports and light heuristics.
    external_tools currently may include: {"poppler"}.
    """
    p = Path(script_path)
    if not p.exists():
        return set(), set()

    try:
        src = p.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return set(), set()

    try:
        tree = ast.parse(src)
    except Exception:
        return set(), set()

    imported: Set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for n in node.names:
                if n.name:
                    imported.add(n.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imported.add(node.module.split(".")[0])

    # Map common import names -> pip packages
    import_to_pip = {
        "pdf2image": "pdf2image",
        "PIL": "Pillow",
        "win32com": "pywin32",
        "numpy": "numpy",
        "cv2": "opencv-python",
    }

    pip: Set[str] = set()
    for mod in imported:
        if mod in import_to_pip:
            pip.add(import_to_pip[mod])

    external: Set[str] = set()
    # pdf2image requires poppler (pdftoppm) on Windows unless user configured otherwise
    if "pdf2image" in imported:
        external.add("poppler")

    return pip, external


def get_poppler_install_dir() -> Path:
    """Standard user-level install dir — no admin rights required."""
    return Path(os.environ.get("LOCALAPPDATA", Path.home())) / "StillMotion" / "poppler"


def _poppler_bin_usable(bin_dir: Path) -> bool:
    """
    Check that pdftoppm.exe in bin_dir actually exists AND can be executed
    by the current user. Catches PermissionError / access-denied errors that
    arise when the directory was installed by a different account.
    """
    try:
        exe = bin_dir / "pdftoppm.exe"
        if not exe.exists():
            return False
        result = subprocess.run(
            [str(exe), "-v"],
            capture_output=True,
            timeout=5,
        )
        return True  # ran without PermissionError regardless of exit code
    except (PermissionError, OSError):
        return False


def find_poppler_bin() -> Optional[str]:
    """
    Return the path to the directory containing a usable pdftoppm.exe, or None.
    Checks PATH first, then our managed AppData install, then common locations.
    Skips any path that is inaccessible to the current user.
    """
    if shutil.which("pdftoppm"):
        return None  # already in PATH — no explicit path needed

    managed = get_poppler_install_dir()
    candidates = [
        managed / "Library" / "bin",
        managed / "bin",
        Path(r"C:\modues\poppler\Library\bin"),
        Path(r"C:\modues\poppler\bin"),
        Path(r"C:\poppler\Library\bin"),
        Path(r"C:\poppler\bin"),
        Path.home() / "poppler" / "Library" / "bin",
        Path.home() / "poppler" / "bin",
        Path(r"C:\Program Files\poppler\bin"),
        Path(r"C:\Program Files (x86)\poppler\bin"),
    ]
    for d in candidates:
        try:
            if d.exists() and _poppler_bin_usable(d):
                return str(d)
        except (PermissionError, OSError):
            continue  # inaccessible — skip silently
    return None


def poppler_available() -> bool:
    """pdftoppm presence check — checks PATH and all known install locations."""
    try:
        if shutil.which("pdftoppm"):
            return True
    except (PermissionError, OSError):
        pass
    return find_poppler_bin() is not None


def install_poppler_silent(log_cb) -> Optional[str]:
    """
    Download and install Poppler automatically to %LOCALAPPDATA%\\StillMotion\\poppler.
    No admin rights required. Adds the bin dir to the user PATH via setx.
    Returns the bin dir path on success, None on failure.
    """
    install_dir = get_poppler_install_dir()
    log_cb(f"[{_now_ts()}] Downloading Poppler for Windows (~30 MB)...")
    log_cb(f"[{_now_ts()}]   {POPPLER_URL}")

    temp_dir = Path(tempfile.gettempdir())
    zip_path = temp_dir / "poppler_temp.zip"

    try:
        urllib.request.urlretrieve(POPPLER_URL, zip_path)
        log_cb(f"[{_now_ts()}] Download complete. Extracting...")

        extract_temp = temp_dir / "poppler_extract"
        if extract_temp.exists():
            shutil.rmtree(extract_temp)
        extract_temp.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(zip_path, "r") as z:
            z.extractall(extract_temp)

        # Locate the root of the extracted tree
        extracted_dirs = list(extract_temp.glob("poppler-*"))
        if not extracted_dirs:
            extracted_dirs = [d for d in extract_temp.iterdir() if d.is_dir()]
        if not extracted_dirs:
            log_cb(f"[{_now_ts()}] [!] Could not locate extracted poppler directory.")
            return None

        source_dir = extracted_dirs[0]

        # Install
        if install_dir.exists():
            shutil.rmtree(install_dir)
        install_dir.mkdir(parents=True, exist_ok=True)
        for item in source_dir.iterdir():
            shutil.move(str(item), str(install_dir / item.name))

        # Clean up
        shutil.rmtree(extract_temp, ignore_errors=True)
        try:
            zip_path.unlink()
        except Exception:
            pass

        # Find the bin dir
        bin_dir: Optional[Path] = None
        for candidate in (install_dir / "Library" / "bin", install_dir / "bin"):
            if candidate.exists() and (candidate / "pdftoppm.exe").exists():
                bin_dir = candidate
                break

        if bin_dir is None:
            log_cb(f"[{_now_ts()}] [!] pdftoppm.exe not found after extraction. Check {install_dir}")
            return None

        log_cb(f"[{_now_ts()}] Poppler installed: {bin_dir}")

        # Persist to user PATH via setx (takes effect in new processes / after re-login)
        try:
            current_path = os.environ.get("PATH", "")
            bin_str = str(bin_dir)
            if bin_str.lower() not in current_path.lower():
                result = subprocess.run(
                    ["setx", "PATH", f"{current_path};{bin_str}"],
                    capture_output=True, text=True, check=False
                )
                if result.returncode == 0:
                    log_cb(f"[{_now_ts()}] Added to user PATH (effective on next login).")
                else:
                    log_cb(f"[{_now_ts()}] Note: setx PATH failed — Poppler path not persisted to PATH.")
                # Update current process immediately so pdftojpg.py can find it right away
                os.environ["PATH"] = f"{current_path};{bin_str}"
        except Exception as e:
            log_cb(f"[{_now_ts()}] Note: Could not update PATH: {e}")

        return str(bin_dir)

    except Exception as e:
        log_cb(f"[{_now_ts()}] [!] Poppler auto-install failed: {e}")
        return None


def ensure_python_installed(log_cb) -> Optional[str]:
    """
    If python is missing, attempt to install via winget (best-effort).
    Returns python executable identifier/path or None.
    """
    py = find_python_exe()
    if py:
        return py

    if not shutil.which("winget"):
        log_cb(f"[{_now_ts()}] Python not found and winget is not available.")
        return None

    log_cb(f"[{_now_ts()}] Python not found. Attempting install via winget (Python 3.12)...")
    try:
        # User-level install is typically OK. Keep it fully non-interactive.
        cmd = [
            "winget", "install",
            "--id", "Python.Python.3.12",
            "-e",
            "--silent",
            "--accept-source-agreements",
            "--accept-package-agreements",
        ]
        subprocess.run(cmd, check=False, capture_output=True, text=True)
    except Exception as e:
        log_cb(f"[{_now_ts()}] winget install failed: {e}")
        return None

    time.sleep(1.0)
    py2 = find_python_exe()
    if py2:
        log_cb(f"[{_now_ts()}] Python detected after install: {py2}")
    else:
        log_cb(f"[{_now_ts()}] Python still not detected after winget install.")
    return py2


def pip_install(python_exe: str, packages: Iterable[str], log_cb) -> bool:
    pkgs = [p for p in packages if p]
    if not pkgs:
        return True

    # Use -m pip; if python_exe == "py" it's still valid.
    cmd = [python_exe, "-m", "pip", "install", "--upgrade", "pip"]
    log_cb(f"[{_now_ts()}] Running: {' '.join(cmd)}")
    r1 = subprocess.run(cmd, capture_output=True, text=True)
    if r1.returncode != 0:
        log_cb(f"[{_now_ts()}] pip upgrade failed:\n{r1.stdout}\n{r1.stderr}")
        # continue; sometimes pip is fine anyway

    cmd2 = [python_exe, "-m", "pip", "install", *pkgs]
    log_cb(f"[{_now_ts()}] Running: {' '.join(cmd2)}")
    r2 = subprocess.run(cmd2, capture_output=True, text=True)
    if r2.returncode != 0:
        log_cb(f"[{_now_ts()}] pip install failed:\n{r2.stdout}\n{r2.stderr}")
        return False

    log_cb(f"[{_now_ts()}] pip install OK: {', '.join(pkgs)}")
    return True

