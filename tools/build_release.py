"""Build an auditable local OgarniaczSM release; never publish or install it.

Run with the repository virtual environment after committing every source change::

    python tools/build_release.py --output releases/0.5.2.29

The output must be a new or empty directory. PyInstaller's ordinary Qt hooks
collect WebEngine dependencies; no blanket collect-all or post-build pruning is
used. A failed build is retained with its log for diagnosis.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import time
import zipfile


REPO = Path(__file__).resolve().parents[1]
APP_NAME = "OgarniaczSM"
UPDATER_NAME = "OgarniaczUpdater"
RESOURCE_SUFFIXES = {".png", ".ico", ".svg", ".html", ".qss"}
# These are callable application modules, including entry points that can be
# selected through configuration rather than a statically visible import.
RUNTIME_MODULES = (
    "archviz_core", "archviz_server", "archviz_cli", "archviz_studio_widget",
    "people_enhancer_pipeline", "people_enhancer_widget", "zeus_workflows_api",
    "zeus_workflows_widget", "deps_manager", "ui_components", "utils", "pdftojpg",
)


def _git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True,
                                   encoding="utf-8").strip()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")


def source_info(repo: Path) -> tuple[dict, list[Path]]:
    version = (repo / "app/version.txt").read_text(encoding="utf-8-sig").strip()
    if not re.fullmatch(r"\d+\.\d+\.\d+\.\d+", version):
        raise ValueError("app/version.txt must contain a four-component release version.")
    dirty = _git(repo, "status", "--porcelain", "--untracked-files=normal")
    commit = _git(repo, "rev-parse", "HEAD")
    tracked = _git(repo, "ls-files", "-z", "--", "app").split("\0")
    resources = sorted(repo / name for name in tracked if name and
                       Path(name).suffix.lower() in RESOURCE_SUFFIXES)
    for required in ["app/main.py", "app/updater.py", "app/icon.ico",
                     "app/archviz_studio.html", "app/archviz_studio_widget.png"]:
        if not (repo / required).is_file():
            raise ValueError(f"Required source is missing: {required}")
    info = {
        "schema_version": 1, "version": version, "commit": commit,
        "source_date_epoch": int(_git(repo, "show", "-s", "--format=%ct", "HEAD")),
        "python": platform.python_version(), "platform": platform.platform(),
        "PyInstaller": importlib.metadata.version("PyInstaller"),
        "PySide6": importlib.metadata.version("PySide6"),
        "dirty": bool(dirty),
    }
    return info, resources


def validate_output(repo: Path, output: Path) -> None:
    output = output.resolve()
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError("--output must be a new or empty directory; nothing is deleted.")
    if str(output).startswith("\\\\"):
        raise ValueError("Build locally first; a network share cannot be the staging directory.")
    if os.name == "nt":
        import ctypes
        if ctypes.windll.kernel32.GetDriveTypeW(str(output.anchor)) == 4:
            raise ValueError("Build locally first; mapped network drives cannot be staging directories.")
    if output == repo or output in repo.parents:
        raise ValueError("The source repository or its parents cannot be output directories.")
    if output.is_relative_to(repo):
        probe = (output / ".build-output-probe").relative_to(repo).as_posix()
        check = subprocess.run(["git", "-C", str(repo), "check-ignore", "--quiet", probe])
        if check.returncode:
            raise ValueError("An output within the repository must be ignored (releases/, build/ or dist/).")


def _pyinstaller_command(repo: Path, output: Path, name: str, entry: str,
                         *, onefile: bool, datas: list[tuple[Path, str]] = ()) -> list[str]:
    command = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
               "--noupx", "--windowed", "--onefile" if onefile else "--onedir",
               "--name", name, "--distpath", str(output / "dist"),
               "--workpath", str(output / "build" / name),
               "--specpath", str(output / "build/spec"),
               "--paths", str(repo / "app"), "--icon", str(repo / "app/icon.ico")]
    for path, destination in datas:
        command += ["--add-data", str(path) + os.pathsep + destination]
    if not onefile:
        for module in RUNTIME_MODULES:
            command += ["--hidden-import", module]
    return command + [str(repo / "app" / entry)]


def _run(command: list[str], repo: Path, log, env: dict) -> None:
    log.write("\nCOMMAND " + json.dumps(command, ensure_ascii=False) + "\n")
    log.flush()
    subprocess.run(command, cwd=repo, env=env, stdout=log, stderr=subprocess.STDOUT,
                   check=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def freeze_source(repo: Path, destination: Path, commit: str) -> None:
    """Build from committed bytes, never from a concurrently changing checkout."""
    archive = destination.parent / "source.tar"
    subprocess.run(["git", "-C", str(repo), "archive", "--format=tar",
                    "--output", str(archive), commit], check=True)
    destination.mkdir()
    with tarfile.open(archive, "r") as source:
        source.extractall(destination, filter="data")


def verify_bundle(bundle: Path) -> dict:
    """Read-only validation; does not execute the application or its updater."""
    required = ["OgarniaczSM.exe", "OgarniaczUpdater.exe", "version.json",
                "build_info.json", "archviz_studio.html", "archviz_studio_widget.png",
                "icon.ico", "_internal/archviz_studio.html",
                "_internal/archviz_studio_widget.png", "_internal/build_info.json"]
    missing = [path for path in required if not (bundle / path).is_file()]
    for filename in ["QtWebEngineProcess.exe", "en-US.pak", "icudtl.dat",
                     "qtwebengine_resources.pak"]:
        if not any((bundle / "_internal").rglob(filename)):
            missing.append("QtWebEngine dependency: " + filename)
    if missing:
        raise ValueError("Incomplete runnable bundle: " + ", ".join(missing))
    configs = [str(p.relative_to(bundle)) for p in bundle.rglob("config.json")]
    if configs:
        raise ValueError("Machine configuration must not be bundled: " + ", ".join(configs))
    inner = json.loads((bundle / "_internal/build_info.json").read_text(encoding="utf-8"))
    outer = json.loads((bundle / "build_info.json").read_text(encoding="utf-8"))
    version = json.loads((bundle / "version.json").read_text(encoding="utf-8"))
    if inner != outer or version["version"] != outer["version"]:
        raise ValueError("Inner/outer build metadata or release versions differ.")
    return {"status": "PASS", "resources": required, "version": outer["version"],
            "commit": outer["commit"], "qt_webengine_resources_preserved": True,
            "machine_config_bundled": False}


def file_inventory(bundle: Path, info: dict) -> dict:
    entries = []
    for path in sorted(bundle.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"Release contains a symlink: {path}")
        if path.is_file() and path != bundle / "file_manifest.json":
            entries.append({"path": path.relative_to(bundle).as_posix(),
                            "sha256": _sha256(path), "size": path.stat().st_size})
    return {"schema_version": 1, "version": info["version"], "commit": info["commit"],
            "files": entries}


def package_bundle(bundle: Path, destination: Path, epoch: int) -> None:
    # The ZIP root is the runnable bundle root, matching updater --zip semantics.
    stamp = time.gmtime(max(315532800, min(epoch, 4354819198)))[:6]
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED,
                         compresslevel=6, allowZip64=True) as archive:
        for path in sorted(bundle.rglob("*")):
            if path.is_file():
                entry = zipfile.ZipInfo(path.relative_to(bundle).as_posix(), stamp)
                entry.compress_type = zipfile.ZIP_DEFLATED
                entry.create_system = 3
                entry.external_attr = 0o100644 << 16
                with path.open("rb") as source, archive.open(entry, "w", force_zip64=True) as target:
                    shutil.copyfileobj(source, target, length=1024 * 1024)


def build(repo: Path, output: Path, info: dict, resources: list[Path]) -> dict:
    if os.name != "nt":
        raise ValueError("Production Windows executables must be built on Windows.")
    if info["dirty"]:
        raise ValueError("Commit all source changes before a release build (working tree is dirty).")
    validate_output(repo, output)
    output.mkdir(parents=True, exist_ok=True)
    (output / "build/spec").mkdir(parents=True)
    generated = output / "build/generated"
    generated.mkdir()
    build_info = {k: v for k, v in info.items() if k != "dirty"}
    _json(generated / "build_info.json", build_info)
    _json(output / "build_state.json", {"status": "building", **build_info})
    env = os.environ.copy()
    env["SOURCE_DATE_EPOCH"] = str(info["source_date_epoch"])
    # PDF Magician is also an external-script tile. Retain its script and helper
    # beside the executable for configurations that resolve these local paths.
    log_path = output / "build.log"
    try:
        source = output / "build/source"
        freeze_source(repo, source, info["commit"])
        resources = [source / path.relative_to(repo) for path in resources]
        datas = [(path, str(path.relative_to(source / "app").parent)) for path in resources]
        datas += [(source / "app/version.txt", "."), (generated / "build_info.json", "."),
                  (source / "app/pdftojpg.py", "."), (source / "app/deps_manager.py", ".")]
        with log_path.open("w", encoding="utf-8", buffering=1) as log:
            print("Building application with ordinary PyInstaller/Qt hooks...", flush=True)
            _run(_pyinstaller_command(source, output, APP_NAME, "main.py", onefile=False,
                                      datas=datas), source, log, env)
            print("Building standalone updater...", flush=True)
            _run(_pyinstaller_command(source, output, UPDATER_NAME, "updater.py", onefile=True),
                 source, log, env)
        current, _ = source_info(repo)
        if current["dirty"] or current["commit"] != info["commit"]:
            raise ValueError("Source changed during build; this staging release cannot be published.")
        bundle = output / "dist" / APP_NAME
        shutil.copy2(output / "dist" / (UPDATER_NAME + ".exe"), bundle / (UPDATER_NAME + ".exe"))
        for path in resources:
            target = bundle / path.relative_to(source / "app")
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
        for name in ["pdftojpg.py", "deps_manager.py", "version.txt"]:
            shutil.copy2(source / "app" / name, bundle / name)
        _json(bundle / "build_info.json", build_info)
        _json(bundle / "version.json", {"version": info["version"], "commit": info["commit"]})
        validation = verify_bundle(bundle)
        _json(output / "bundle_validation.json", validation)
        inventory = file_inventory(bundle, info)
        _json(bundle / "file_manifest.json", inventory)
        package = output / "package.zip"
        print("Hashing and packaging verified staging bundle...", flush=True)
        package_bundle(bundle, package, info["source_date_epoch"])
        release = {"schema_version": 1, "version": info["version"], "commit": info["commit"],
                   "bundle_path": str(bundle.relative_to(output)).replace("\\", "/"),
                   "file_manifest_sha256": _sha256(bundle / "file_manifest.json"),
                   "package": package.name, "package_sha256": _sha256(package),
                   "package_size": package.stat().st_size, "file_count": len(inventory["files"]),
                   "unpacked_size": sum(item["size"] for item in inventory["files"]),
                   "build_info": build_info, "validation": validation,
                   "configuration": "External config.json is preserved and is not bundled."}
        _json(output / "release_manifest.json", release)
        (output / (package.name + ".sha256")).write_text(
            release["package_sha256"] + "  " + package.name + "\n", encoding="ascii")
        _json(output / "build_state.json", {"status": "complete", **release})
        return release
    except Exception as error:
        _json(output / "build_state.json", {"status": "failed", **build_info,
                                            "error": str(error), "log": str(log_path)})
        raise


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output", type=Path, required=True,
                        help="New/empty local staging directory (e.g. releases/0.5.2.29).")
    parser.add_argument("--plan", action="store_true", help="Read-only preflight; do not start PyInstaller.")
    args = parser.parse_args(argv)
    output = args.output.resolve()
    try:
        info, resources = source_info(REPO)
        validate_output(REPO, output)
        if args.plan:
            print(json.dumps({"source": info, "output": str(output),
                              "resources": [p.relative_to(REPO).as_posix() for p in resources],
                              "runtime_modules": RUNTIME_MODULES,
                              "build_allowed": not info["dirty"]}, ensure_ascii=False, indent=2))
            return 0 if not info["dirty"] else 2
        release = build(REPO, output, info, resources)
        print(json.dumps(release, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print("Build stopped: " + str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
