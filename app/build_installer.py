from pathlib import Path
import shutil, os, sys, subprocess, ctypes, json
import tempfile
import winreg

APP_NAME   = "OgarniaczSM"

# Używamy ścieżek względnych - dla PyInstaller onefile, sys.executable wskazuje na EXE
# Dla zwykłego skryptu, __file__ wskazuje na .py
def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        # Jesteśmy w PyInstaller EXE - EXE jest w dist/, szukaj plików obok EXE
        # Installer EXE: dist/OgarniaczInstaller.exe
        # App folder: dist/ogarniacz/OgarniaczSM/
        return Path(sys.executable).resolve().parent
    # Jako skrypt Python: __file__ jest w project root
    return Path(__file__).resolve().parent

BASE_DIR = get_base_dir()

# Determine source folder - prefer PROD/latest (synced to all PCs) over dist/ogarniacz (local only)
def get_source_folder():
    if getattr(sys, "frozen", False):
        # Running as EXE - check for PROD/latest first (in project root = parent of dist)
        project_root = BASE_DIR.parent
        prod_latest = project_root / "PROD" / "latest"
        if prod_latest.exists() and (prod_latest / "OgarniaczSM.exe").exists():
            return prod_latest
        # Fallback to dist/ogarniacz/OgarniaczSM
        return BASE_DIR / "ogarniacz" / "OgarniaczSM"
    else:
        # Running as script - check for PROD/latest first
        prod_latest = BASE_DIR / "PROD" / "latest"
        if prod_latest.exists() and (prod_latest / "OgarniaczSM.exe").exists():
            return prod_latest
        # Fallback to dist/ogarniacz/OgarniaczSM
        return BASE_DIR / "dist" / "ogarniacz" / "OgarniaczSM"

SRC_ONEDIR = get_source_folder()
if getattr(sys, "frozen", False):
    SRC_ICON = BASE_DIR.parent / "icon.ico"  # Jeden poziom wyżej (project root)
else:
    SRC_ICON = BASE_DIR / "icon.ico"

TARGET_DIR = Path(os.environ["LOCALAPPDATA"]) / APP_NAME
START_MENU = Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
SHORTCUT   = START_MENU / f"{APP_NAME}.lnk"

def msg(t, title="OgarniaczSM Installer", icon=0x40):
    try: ctypes.windll.user32.MessageBoxW(0, str(t), str(title), icon)
    except: print(f"[{title}] {t}")

def check_vcredist_installed() -> bool:
    """Check if Visual C++ 2015-2022 Redistributable (x64) is installed"""
    try:
        # Check registry for VC++ Redistributables
        # Common registry keys for VC++ Redistributables
        reg_paths = [
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\VisualStudio\14.0\VC\Runtimes\x64"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\VisualStudio\15.0\VC\Runtimes\x64"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\VisualStudio\15.0\VC\Runtimes\x64"),
        ]
        
        for hkey, path in reg_paths:
            try:
                with winreg.OpenKey(hkey, path):
                    return True
            except FileNotFoundError:
                continue
        
        # Also try to load VCRUNTIME140.dll directly (more reliable)
        try:
            ctypes.windll.LoadLibrary("VCRUNTIME140.dll")
            return True
        except OSError:
            pass
        
        return False
    except Exception:
        # If we can't check, assume it's not installed to be safe
        return False

def install_vcredist() -> bool:
    """Install Visual C++ Redistributable if bundled, or download and install"""
    # When frozen (PyInstaller), bundled files are extracted to a temp directory
    # PyInstaller stores them in sys._MEIPASS
    if getattr(sys, "frozen", False):
        # Check in the temp extraction directory first (bundled file)
        if hasattr(sys, "_MEIPASS"):
            vcredist_path = Path(sys._MEIPASS) / "vc_redist.x64.exe"
            if vcredist_path.exists():
                # Extract to temp directory and run from there
                temp_dir = Path(tempfile.gettempdir()) / "OgarniaczSM_Installer"
                temp_dir.mkdir(exist_ok=True)
                temp_vcredist = temp_dir / "vc_redist.x64.exe"
                shutil.copy2(vcredist_path, temp_vcredist)
                vcredist_path = temp_vcredist
            else:
                # Try in the same directory as the installer EXE
                vcredist_path = BASE_DIR / "vc_redist.x64.exe"
        else:
            vcredist_path = BASE_DIR / "vc_redist.x64.exe"
    else:
        vcredist_path = BASE_DIR / "vc_redist.x64.exe"
    
    if not vcredist_path.exists():
        # Try to download it
        msg(
            "Visual C++ Redistributables are required but not found.\n\n"
            "Please download and install:\n"
            "https://aka.ms/vs/17/release/vc_redist.x64.exe\n\n"
            "The app will not work without this.",
            title="Missing Prerequisites", icon=0x30
        )
        return False
    
    try:
        msg(
            "Installing Visual C++ Redistributables...\n"
            "This is required for the app to run.\n\n"
            "Please wait...",
            title="Installing Prerequisites", icon=0x40
        )
        
        # Run the installer silently
        # /install /quiet /norestart = silent install, no restart prompt
        result = subprocess.run(
            [str(vcredist_path), "/install", "/quiet", "/norestart"],
            timeout=300,  # 5 minute timeout
            capture_output=True
        )
        
        if result.returncode == 0 or result.returncode == 3010:  # 3010 = success, restart recommended
            return True
        else:
            msg(
                f"Visual C++ Redistributable installation may have failed.\n"
                f"Return code: {result.returncode}\n\n"
                f"You may need to install it manually:\n"
                f"{vcredist_path}",
                title="Installation Warning", icon=0x30
            )
            return False
    except subprocess.TimeoutExpired:
        msg(
            "Visual C++ Redistributable installation timed out.\n"
            "Please install manually and try again.",
            title="Installation Timeout", icon=0x30
        )
        return False
    except Exception as e:
        msg(
            f"Error installing Visual C++ Redistributables:\n{e}\n\n"
            f"Please install manually: {vcredist_path}",
            title="Installation Error", icon=0x30
        )
        return False

def create_shortcut(target: Path, shortcut_path: Path, icon: Path | None = None):
    try:
        import win32com.client  # pip install pywin32
        shell = win32com.client.Dispatch("WScript.Shell")
        sc = shell.CreateShortcut(str(shortcut_path))
        sc.TargetPath = str(target)
        sc.WorkingDirectory = str(target.parent)
        sc.IconLocation = str(icon or target)
        sc.Save()
    except Exception as e:
        msg(f"Nie udało się utworzyć skrótu:\n{e}", icon=0x30)

def install():
    # Show diagnostic info to help debug sync issues
    try:
        import datetime
        exe_time = datetime.datetime.fromtimestamp(Path(sys.executable).stat().st_mtime) if getattr(sys, "frozen", False) else None
        src_exe = SRC_ONEDIR / "OgarniaczSM.exe"
        src_time = datetime.datetime.fromtimestamp(src_exe.stat().st_mtime) if src_exe.exists() else None
        
        # Read version from manifest.json (most accurate)
        project_root = BASE_DIR.parent if getattr(sys, "frozen", False) else BASE_DIR
        manifest_path = project_root / "PROD" / "manifest.json"
        version = "unknown"
        if manifest_path.exists():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                version = str(manifest.get("version", "unknown"))
            except:
                pass
        if version == "unknown":
            version_txt = project_root / "version.txt"
            if version_txt.exists():
                try:
                    version = version_txt.read_text(encoding="utf-8").strip()
                except:
                    pass
        
        # Detect source type
        src_type = "PROD/latest" if "PROD" in str(SRC_ONEDIR) else "dist/ogarniacz"
        
        diag = f"Installing OgarniaczSM v{version}\n\n"
        diag += f"Source: {src_type}\n"
        diag += f"Path: {SRC_ONEDIR}\n"
        if src_time:
            diag += f"Build date: {src_time.strftime('%Y-%m-%d %H:%M:%S')}\n"
        else:
            diag += "Build: NOT FOUND!\n"
        if exe_time:
            diag += f"\nInstaller date: {exe_time.strftime('%Y-%m-%d %H:%M:%S')}"
        diag += f"\n\nTarget: {TARGET_DIR}"
        
        msg(diag, title="OgarniaczSM Installer - Info", icon=0x40)
    except Exception as e:
        pass  # Don't fail installation due to diagnostic errors
    
    # Check and install Visual C++ Redistributables first
    if not check_vcredist_installed():
        if not install_vcredist():
            # User chose not to install or installation failed
            # We'll continue anyway, but warn them
            response = ctypes.windll.user32.MessageBoxW(
                0,
                "Visual C++ Redistributables are not installed.\n\n"
                "The app may not work correctly.\n\n"
                "Continue with installation anyway?",
                "OgarniaczSM Installer - Warning",
                0x30 | 0x01  # Warning icon + Yes/No buttons
            )
            if response != 6:  # 6 = IDYES
                sys.exit(1)
    
    if not SRC_ONEDIR.exists():
        msg(
          "Brak builda ONEDIR:\n"
          f"{SRC_ONEDIR}\n\nUruchom: python GENERATE_OGARNIACZ_EXE.py",
          title="OgarniaczSM Installer – błąd", icon=0x10
        )
        sys.exit(1)

    # W PyInstaller 6 biblioteki są w 'OgarniaczSM\\_internal\\...'
    # więc sprawdzamy istnienie tego folderu:
    if not (SRC_ONEDIR / "_internal").exists():
        msg(
          "Nie widzę folderu _internal w buildzie. To podejrzane dla PyInstaller 6.\n"
          "Zbuduj ponownie (onedir).",
          title="OgarniaczSM Installer – ostrzeżenie", icon=0x30
        )

    if TARGET_DIR.exists():
        shutil.rmtree(TARGET_DIR)

    # Kopiujemy CAŁY katalog (exe + _internal + reszta)
    shutil.copytree(SRC_ONEDIR, TARGET_DIR)

    # po skopiowaniu folderu aplikacji: copy updater
    # Check PROD first, then dist
    if getattr(sys, "frozen", False):
        project_root = BASE_DIR.parent
        updater_candidates = [
            project_root / "PROD" / "latest" / "OgarniaczUpdater.exe",
            BASE_DIR / "ogarniacz" / "OgarniaczUpdater.exe",
        ]
    else:
        updater_candidates = [
            BASE_DIR / "PROD" / "latest" / "OgarniaczUpdater.exe",
            BASE_DIR / "dist" / "ogarniacz" / "OgarniaczUpdater.exe",
        ]
    updater_src = next((p for p in updater_candidates if p.exists()), None)
    if updater_src:
        shutil.copy2(updater_src, TARGET_DIR / "OgarniaczUpdater.exe")


    if SRC_ICON.exists():
        shutil.copy2(SRC_ICON, TARGET_DIR / "icon.ico")

    # Utwórz plik version.json z wersją aplikacji (jeśli nie istnieje)
    version_file = TARGET_DIR / "version.json"
    if not version_file.exists():
        # Próbuj odczytać wersję z version.txt lub manifest.json
        project_root = BASE_DIR.parent if getattr(sys, "frozen", False) else BASE_DIR
        app_version = "1.5.0"  # domyślna wersja
        
        # Try manifest.json first (most accurate after publish)
        manifest_path = project_root / "PROD" / "manifest.json"
        if manifest_path.exists():
            try:
                import json as js
                manifest = js.loads(manifest_path.read_text(encoding="utf-8"))
                app_version = str(manifest.get("version", app_version))
            except:
                pass
        else:
            # Fallback to version.txt
            version_txt = project_root / "version.txt"
            if version_txt.exists():
                try:
                    app_version = version_txt.read_text(encoding="utf-8").strip()
                except:
                    pass
        version_file.write_text(json.dumps({"version": app_version}), encoding="utf-8")

    exe = TARGET_DIR / f"{APP_NAME}.exe"
    START_MENU.mkdir(parents=True, exist_ok=True)
    create_shortcut(exe, SHORTCUT, TARGET_DIR / "icon.ico")

    # Opcjonalne „pin to taskbar” (best-effort)
    try:
        ps = f"$s=(New-Object -ComObject Shell.Application).NameSpace('{START_MENU}');" \
             f"$i=$s.ParseName('{APP_NAME}.lnk');" \
             "foreach($v in $i.Verbs()){ if($v.Name -match 'Pin to taskbar|Przypnij do paska zadań'){ $v.DoIt(); break }}"
        subprocess.run(["powershell","-NoProfile","-ExecutionPolicy","Bypass","-Command",ps], capture_output=True)
    except: 
        pass

    try: subprocess.Popen([str(exe)], cwd=str(TARGET_DIR))
    except: pass

    msg(f"Zainstalowano w:\n{TARGET_DIR}\n\nSkrót: Menu Start → {APP_NAME}", title="OgarniaczSM Installer – zakończono")

if __name__ == "__main__":
    install()
