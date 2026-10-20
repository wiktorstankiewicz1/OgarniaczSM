import argparse, os, shutil, tempfile, urllib.request, zipfile, json, subprocess
from pathlib import Path

def extract_zip_to(zip_path: Path, dst: Path):
    if dst.exists():
        shutil.rmtree(dst)
    dst.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, 'r') as z:
        z.extractall(dst)

def copy_dir(src: Path, dst: Path):
    # Copy files one by one to handle Windows file locking (can't delete running exe)
    if not dst.exists():
        dst.mkdir(parents=True, exist_ok=True)
    
    # Copy/overwrite all files from src to dst
    for item in src.rglob('*'):
        if item.is_file():
            rel_path = item.relative_to(src)
            dst_item = dst / rel_path
            dst_item.parent.mkdir(parents=True, exist_ok=True)
            try:
                # Try to remove existing file first
                if dst_item.exists():
                    dst_item.unlink()
            except (PermissionError, OSError):
                # File is locked (running executable), that's okay - copy will overwrite
                pass
            try:
                shutil.copy2(item, dst_item)
            except Exception as e:
                # If copy fails, try again after a brief delay (file might be unlocking)
                import time
                time.sleep(0.1)
                try:
                    shutil.copy2(item, dst_item)
                except Exception:
                    pass  # Skip this file if it still fails
    
    # Remove files in dst that don't exist in src
    for item in dst.rglob('*'):
        if item.is_file():
            rel_path = item.relative_to(dst)
            src_item = src / rel_path
            if not src_item.exists():
                try:
                    item.unlink()
                except Exception:
                    pass
    
    # Remove directories in dst that don't exist in src
    for item in reversed(list(dst.rglob('*'))):  # Reverse to delete children first
        if item.is_dir():
            rel_path = item.relative_to(dst)
            src_item = src / rel_path
            if not src_item.exists():
                try:
                    item.rmdir()
                except Exception:
                    pass

def main():
    p = argparse.ArgumentParser(description="OgarniaczSM Updater")
    p.add_argument("--src", help="Źródło katalogu ONEDIR (tryb SMB)")
    p.add_argument("--zip", help="URL do ZIP (tryb HTTP)")
    p.add_argument("--dst", required=True, help="Katalog docelowy (LOCALAPPDATA\\OgarniaczSM)")
    p.add_argument("--launch", required=True, help="Ścieżka do EXE po update")
    p.add_argument("--version", required=True, help="Numer wersji do zapisania w version.json")
    args = p.parse_args()

    dst = Path(args.dst)

    if args.zip:
        # pobierz ZIP po HTTPS i rozpakuj do dst
        with tempfile.TemporaryDirectory() as td:
            tmp_zip = Path(td) / "latest.zip"
            urllib.request.urlretrieve(args.zip, tmp_zip)
            extract_zip_to(tmp_zip, dst)
    elif args.src:
        copy_dir(Path(args.src), dst)
    else:
        raise SystemExit("Provide --zip or --src")

    # zapisz lokalną wersję
    (dst / "version.json").write_text(json.dumps({"version": args.version}), encoding="utf-8")

    # uruchom aplikację
    subprocess.Popen([args.launch], cwd=str(dst))

if __name__ == "__main__":
    main()
