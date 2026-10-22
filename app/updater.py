"""Verified staged OgarniaczSM installation with a retained rollback directory."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import subprocess
import tempfile
import time
import urllib.request
import uuid
import zipfile


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_relative(name):
    path = PurePosixPath(str(name).replace("\\", "/"))
    if path.is_absolute() or not path.parts or any(p in {".", ".."} or ":" in p for p in path.parts):
        raise ValueError("Unsafe package path")
    return Path(*path.parts)


def is_userdata(relative):
    parts = relative.as_posix().casefold().split("/")
    return parts[0] == "archvizstudio" or "/".join(parts) in {
        "config.json", "autoupdate.log", "installation_receipt.json"}


def verify_release(src, expected_manifest_sha=None, allow_userdata=False):
    src = Path(src).resolve()
    manifest_path = src / "file_manifest.json"
    if expected_manifest_sha and sha256(manifest_path) != expected_manifest_sha:
        raise ValueError("Release manifest SHA256 mismatch")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != 1 or not manifest.get("version") or not manifest.get("commit"):
        raise ValueError("Invalid release manifest")
    expected = set()
    for item in manifest["files"]:
        relative = safe_relative(item["path"])
        key = relative.as_posix().casefold()
        if key in expected or key == "file_manifest.json":
            raise ValueError("Duplicate package path")
        expected.add(key)
        path = src / relative
        if path.is_symlink() or not path.resolve().is_relative_to(src) or not path.is_file():
            raise ValueError("Missing or unsafe package file: " + relative.as_posix())
        if path.stat().st_size != item["size"] or sha256(path) != item["sha256"]:
            raise ValueError("Package SHA256 mismatch: " + relative.as_posix())
    if "ogarniaczsm.exe" not in expected or "version.json" not in expected:
        raise ValueError("Package has no application or version")
    version = json.loads((src / "version.json").read_text(encoding="utf-8"))["version"]
    if version != manifest["version"]:
        raise ValueError("Package version mismatch")
    for path in src.rglob("*"):
        relative = path.relative_to(src)
        if path.is_symlink():
            raise ValueError("Symlink in package")
        if path.is_file() and relative.as_posix().casefold() not in expected | {"file_manifest.json"}:
            if not (allow_userdata and is_userdata(relative)):
                raise ValueError("Unlisted package file: " + relative.as_posix())
    return manifest


def extract_zip_to(zip_path, dst):
    dst = Path(dst).resolve()
    if dst.exists() and any(dst.iterdir()):
        raise ValueError("Extraction requires an empty directory")
    dst.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as archive:
        for item in archive.infolist():
            relative = safe_relative(item.filename)
            target = dst / relative
            if not target.resolve().is_relative_to(dst) or stat.S_ISLNK(item.external_attr >> 16):
                raise ValueError("Unsafe ZIP member")
        archive.extractall(dst)


def copy_dir(src, dst, expected_manifest_sha=None, version=None):
    src, dst = Path(src).resolve(), Path(dst).resolve()
    if src == dst or src.is_relative_to(dst) or dst.is_relative_to(src) or len(dst.parts) < 3:
        raise ValueError("Unsafe installation paths")
    manifest = verify_release(src, expected_manifest_sha)
    if version is not None and manifest["version"] != version:
        raise ValueError("Requested version differs from package")
    dst.parent.mkdir(parents=True, exist_ok=True)
    suffix = uuid.uuid4().hex
    staging = dst.with_name(dst.name + ".staging-" + suffix)
    backup = dst.with_name(dst.name + ".previous-" + suffix)
    moved_old = False
    try:
        shutil.copytree(src, staging)
        verify_release(staging, expected_manifest_sha)
        for name in ["config.json", "ArchvizStudio", "autoupdate.log"]:
            existing, target = dst / name, staging / name
            if existing.is_dir():
                shutil.copytree(existing, target, dirs_exist_ok=True)
            elif existing.is_file():
                shutil.copy2(existing, target)
        verify_release(staging, expected_manifest_sha, allow_userdata=True)
        if dst.exists():
            dst.rename(backup)
            moved_old = True
        try:
            staging.rename(dst)
        except Exception:
            if moved_old:
                backup.rename(dst)
            raise
        return {"version": manifest["version"], "commit": manifest["commit"],
                "destination": str(dst), "backup": str(backup) if moved_old else None}
    finally:
        # Only this freshly created staging directory may be removed.
        if staging.exists() and staging.parent == dst.parent and staging.name == dst.name + ".staging-" + suffix:
            shutil.rmtree(staging)


def wait_for_process(pid, timeout=45):
    if not pid:
        return
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x100000, False, pid)
        if not handle:
            if ctypes.get_last_error() == 87:
                return
            raise RuntimeError("Cannot verify old application shutdown")
        try:
            if kernel.WaitForSingleObject(handle, int(timeout * 1000)) != 0:
                raise RuntimeError("Old application is still running")
        finally:
            kernel.CloseHandle(handle)
    else:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                return
            time.sleep(.2)
        raise RuntimeError("Old application is still running")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--src")
    source.add_argument("--zip")
    parser.add_argument("--dst", required=True)
    parser.add_argument("--launch", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--manifest-sha256")
    parser.add_argument("--wait-pid", type=int)
    args = parser.parse_args(argv)
    dst = Path(args.dst).resolve()
    if Path(args.launch).resolve() != dst / "OgarniaczSM.exe":
        raise ValueError("Launch target must be the installed application")
    wait_for_process(args.wait_pid)
    with tempfile.TemporaryDirectory(prefix="ogarniacz-update-") as temporary:
        if args.zip:
            package = Path(temporary) / "package.zip"
            urllib.request.urlretrieve(args.zip, package)
            src = Path(temporary) / "unpacked"
            extract_zip_to(package, src)
        else:
            src = Path(args.src)
        receipt = copy_dir(src, dst, args.manifest_sha256, args.version)
    (dst / "installation_receipt.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    subprocess.Popen([args.launch], cwd=dst)
    return receipt


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        # No failed copy can mark a version installed or launch mixed files.
        error_path = Path(tempfile.gettempdir()) / "OgarniaczSM-update-error.txt"
        error_path.write_text(str(error), encoding="utf-8")
        raise SystemExit(1)
