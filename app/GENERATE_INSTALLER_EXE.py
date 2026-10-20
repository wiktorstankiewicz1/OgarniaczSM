import subprocess
import sys
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent

INSTALLER_NAME = "OgarniaczInstaller"
INSTALLER_SCRIPT = HERE / "build_installer.py"
ICON = HERE / "icon.ico"

# Oddzielne ścieżki, żeby nic się nie nadpisywało
DIST  = HERE / "dist"
BUILD = HERE / "build" / "installer"

def run(cmd: list[str]) -> None:
    print("»", " ".join(cmd))
    subprocess.check_call(cmd)

def clean():
    installer_exe = DIST / f"{INSTALLER_NAME}.exe"
    if installer_exe.exists():
        try:
            installer_exe.unlink()
        except PermissionError:
            print(f"⚠️  Nie można usunąć {installer_exe.name} - plik jest w użyciu.")
            print(f"   Zamknij {installer_exe.name} i spróbuj ponownie.")
            sys.exit(1)
        except Exception as e:
            print(f"⚠️  Błąd przy usuwaniu {installer_exe.name}: {e}")
            sys.exit(1)
    if BUILD.exists():
        shutil.rmtree(BUILD)
    BUILD.mkdir(parents=True, exist_ok=True)

def build_installer_onefile():
    if not INSTALLER_SCRIPT.exists():
        print(f"Brak pliku: {INSTALLER_SCRIPT}")
        sys.exit(1)
    
    args = [
        sys.executable, "-m", "PyInstaller",
        "--noconsole",
        "--onefile",                 # installer jako single exe
        "--clean",
        "--name", INSTALLER_NAME,
        "--distpath", str(DIST),
        "--workpath", str(BUILD),
        "--specpath", str(HERE),     # zapisz .spec w katalogu projektu
        str(INSTALLER_SCRIPT),
    ]
    if ICON.exists():
        args += ["--icon", str(ICON)]
    
    # Bundle VC++ Redistributable if it exists
    vcredist = HERE / "vc_redist.x64.exe"
    if vcredist.exists():
        print(f"Found VC++ Redistributable: {vcredist}")
        args += ["--add-data", f"{vcredist};."]
    else:
        print("⚠️  VC++ Redistributable not found (vc_redist.x64.exe)")
        print("   Installer will check for it, but won't auto-install.")
        print("   Download from: https://aka.ms/vs/17/release/vc_redist.x64.exe")
        print("   Place it in project root and rebuild installer.")
    
    run(args)
    print("\nOK ->", DIST / f"{INSTALLER_NAME}.exe")

def main():
    clean()
    build_installer_onefile()

if __name__ == "__main__":
    main()

