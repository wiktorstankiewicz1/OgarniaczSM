# updater.py
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path
from urllib.request import Request, urlopen

APP_NAME = "OgarniaczSM"

def _fetch_json(url: str, timeout: int = 20) -> dict:
    req = Request(url, headers={"User-Agent": f"{APP_NAME}-Updater"})
    with urlopen(req, timeout=timeout) as r:
        data = r.read().decode("utf-8", errors="replace")
    return json.loads(data)

def _download(url: str, dst: Path, timeout: int = 60) -> None:
    req = Request(url, headers={"User-Agent": f"{APP_NAME}-Updater"})
    with urlopen(req, timeout=timeout) as r, open(dst, "wb") as f:
        shutil.copyfileobj(r, f)

def _safe_rmtree(p: Path, retries: int = 20, delay: float = 0.25) -> None:
    for i in range(retries):
        try:
            if p.exists():
                shutil.rmtree(p)
            return
        except Exception:
            time.sleep(delay)
    # jeśli się nie udało – zostaw (nie zabijamy update całkiem)
    return

def _copy_tree(src: Path, dst: Path) -> None:
    # python 3.8+ : dirs_exist_ok
    shutil.copytree(src, dst, dirs_exist_ok=True)

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest-url", required=True)
    ap.add_argument("--install-dir", required=True)
    ap.add_argument("--launch", required=True)
    args = ap.parse_args()

    manifest_url = args.manifest_url
    install_dir = Path(args.install_dir).resolve()
    launch_exe = Path(args.launch).resolve()

    tmp_root = Path(os.environ.get("TEMP", str(install_dir))) / f"{APP_NAME}_update_tmp"
    zip_path = tmp_root / "latest.zip"
    extract_dir = tmp_root / "extract"

    tmp_root.mkdir(parents=True, exist_ok=True)
    _safe_rmtree(extract_dir)
    extract_dir.mkdir(parents=True, exist_ok=True)

    # 1) pobierz manifest
    man = _fetch_json(manifest_url)
    remote_v = str(man.get("version", "0.0.0"))
    zip_url = man.get("zip_url")
    if not zip_url:
        sys.exit(2)

    # 2) pobierz zip
    try:
        if zip_path.exists():
            zip_path.unlink()
    except Exception:
        pass
    _download(str(zip_url), zip_path)

    # 3) rozpakuj
    with zipfile.ZipFile(zip_path, "r") as z:
        z.extractall(extract_dir)

    # 4) oczekiwany format ZIP:
    #    extract_dir/
    #       OgarniaczSM.exe
    #       _internal/...
    # albo extract_dir/ OgarniaczSM/ (jeśli zip spakował folder nadrzędny)
    candidate = extract_dir
    if (extract_dir / APP_NAME).is_dir() and (extract_dir / APP_NAME / f"{APP_NAME}.exe").exists():
        candidate = extract_dir / APP_NAME

    if not (candidate / f"{APP_NAME}.exe").exists():
        sys.exit(3)

    # 5) Zamiana plików
    #    najpierw usuń _internal, bo to największy syf przy nadpisach
    _safe_rmtree(install_dir / "_internal")

    # kopiuj wszystko z paczki do install_dir
    for item in candidate.iterdir():
        dst = install_dir / item.name
        try:
            if item.is_dir():
                _copy_tree(item, dst)
            else:
                shutil.copy2(item, dst)
        except Exception:
            # retry na zablokowanych plikach
            time.sleep(0.5)
            try:
                if item.is_dir():
                    _copy_tree(item, dst)
                else:
                    shutil.copy2(item, dst)
            except Exception:
                pass

    # 6) zapisz lokalną wersję
    try:
        (install_dir / "version.json").write_text(json.dumps({"version": remote_v}), encoding="utf-8")
    except Exception:
        pass

    # 7) uruchom nową wersję
    try:
        subprocess.Popen([str(launch_exe)], cwd=str(install_dir), close_fds=True)
    except Exception:
        sys.exit(4)

if __name__ == "__main__":
    main()
