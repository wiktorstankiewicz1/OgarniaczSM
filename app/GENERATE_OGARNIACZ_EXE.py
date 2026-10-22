import subprocess
import sys
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent

APP_NAME = "OgarniaczSM"
MAIN     = HERE / "main.py"
ICON     = HERE / "icon.ico"

UPDATER_NAME = "OgarniaczUpdater"
UPDATER      = HERE / "updater.py"   # jeśli nie masz – ten krok się pominie

# Oddzielne ścieżki, żeby nic się nie nadpisywało
DIST  = HERE / "dist"  / "ogarniacz"
BUILD = HERE / "build" / "ogarniacz"

def run(cmd: list[str]) -> None:
    print("»", " ".join(cmd))
    subprocess.check_call(cmd)

def clean():
    if DIST.exists():
        shutil.rmtree(DIST)
    if BUILD.exists():
        shutil.rmtree(BUILD)
    DIST.mkdir(parents=True, exist_ok=True)
    BUILD.mkdir(parents=True, exist_ok=True)

def remove_unused_qt_folders():
    """Remove QML, translations, and docs folders from the built application"""
    pyside6_path = DIST / APP_NAME / "_internal" / "PySide6"
    if not pyside6_path.exists():
        return
    
    folders_to_remove = ['qml', 'translations', 'doc', 'docs']
    total_files = 0
    total_size = 0
    
    for folder_name in folders_to_remove:
        folder_path = pyside6_path / folder_name
        if folder_path.exists():
            # Count files and size before removal
            files_count = 0
            size_bytes = 0
            for item in folder_path.rglob('*'):
                if item.is_file():
                    files_count += 1
                    try:
                        size_bytes += item.stat().st_size
                    except:
                        pass
            total_files += files_count
            total_size += size_bytes
            
            # Remove the folder
            try:
                shutil.rmtree(folder_path)
                size_mb = size_bytes / 1024 / 1024
                print(f"  Removed {folder_name}/: {files_count} files, {size_mb:.2f} MB")
            except Exception as e:
                print(f"  Warning: Could not remove {folder_name}/: {e}")
    
    if total_files > 0:
        print(f"\n  Total removed: {total_files} files, {total_size / 1024 / 1024:.2f} MB")

def build_app_onedir():
    # Use optimized spec file if it exists, otherwise use default build
    spec_file = HERE / "OgarniaczSM_optimized.spec"
    if spec_file.exists():
        print("Using optimized spec file (will remove QML, translations, unused Qt modules)")
        args = [
            sys.executable, "-m", "PyInstaller",
            "--clean",
            "--distpath", str(DIST),
            "--workpath", str(BUILD),
            str(spec_file),
        ]
    else:
        print("Using default build (all PySide6 modules included)")
        args = [
            sys.executable, "-m", "PyInstaller",
            "--noconsole",
            "--onedir",                   # klasyczny folder (PyInstaller 6 użyje _internal)
            "--clean",
            "--name", APP_NAME,
            "--collect-all", "PySide6",
            "--collect-all", "shiboken6",
            "--distpath", str(DIST),
            "--workpath", str(BUILD),
            "--specpath", str(HERE),      # zapisz .spec w katalogu projektu
            "--add-data", str(HERE / "archviz_studio.html") + ";.",
            "--add-data", str(HERE / "archviz_studio.png") + ";.",
            "--add-data", str(HERE / "archviz_studio_widget.png") + ";.",
            str(MAIN),
        ]
        if ICON.exists():
            args += ["--icon", str(ICON)]
    run(args)
    
    # Post-process: Remove unused Qt folders
    print("\nPost-processing: Removing unused Qt folders...")
    remove_unused_qt_folders()
    
    print("\nOK ->", DIST / APP_NAME / f"{APP_NAME}.exe")

def build_updater_onefile_if_exists():
    if not UPDATER.exists():
        print("Updater pominięty (brak updater.py).")
        return
    args = [
        sys.executable, "-m", "PyInstaller",
        "--noconsole",
        "--onefile",                 # updater może być single exe
        "--clean",
        "--name", UPDATER_NAME,
        "--distpath", str(DIST),
        "--workpath", str(BUILD),
        "--specpath", str(HERE),     # zapisz .spec w katalogu projektu
        str(UPDATER),
    ]
    run(args)
    print("OK ->", DIST / f"{UPDATER_NAME}.exe")

def main():
    clean()
    build_app_onedir()
    build_updater_onefile_if_exists()

if __name__ == "__main__":
    main()
