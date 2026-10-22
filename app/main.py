from pathlib import Path
import sys
import os
import json
import subprocess
import ctypes
import shutil
import threading
import time
import traceback
import autoupdate
try:
    from packaging import version as pkg_version
except Exception:
    pkg_version = None


from PySide6.QtWidgets import QSplashScreen
from PySide6.QtGui import QPainter, QFont
from PySide6.QtCore import Qt, QTimer, QSize, QPoint, QRect
from PySide6.QtGui import QIcon, QPixmap, QMouseEvent
from PySide6.QtWidgets import (
    QApplication, QWidget, QPushButton, QScrollArea, QVBoxLayout, QHBoxLayout,
    QMessageBox, QLabel, QTextEdit, QDialog, QSizePolicy, QLayout, QFrame,
    QStackedLayout, QFileDialog, QMenu, QInputDialog, QLineEdit
)
from deps_manager import (
    ensure_python_installed,
    find_python_exe,
    infer_pip_packages_from_script,
    install_poppler_silent,
    pip_install,
    poppler_available,
)
from utils import BASE_DIR, CONFIG_PATH, resolve_rel_to_config
from people_enhancer_widget import PeopleEnhancerWidget
from zeus_workflows_widget import ZeusWorkflowsWidget
from ui_components import (
    FlowLayout, MarkdownDialog, TileWidget, ScriptTile, FavAppTile
)

def _force_repaint_by_resize(widget: QWidget):
    """
    Forces a widget (usually the main window) to repaint by resizing it
    back and forth by one pixel. This is a workaround for persistent
    UI refresh bugs.
    """
    if not widget:
        return
    
    def do_resize():
        current_size = widget.size()
        # Resize slightly, then immediately back to original size
        widget.resize(current_size.width() + 1, current_size.height())
        widget.resize(current_size)

    # Schedule the resize to happen after the current event loop finishes
    QTimer.singleShot(1, do_resize)

# ---------------- embedded scripts panel ----------------

class ScriptsGridWidget(QWidget):
    def __init__(self, folder: str, parent=None, go_home_callback=None):
        super().__init__(parent)
        self.folder = folder
        self.history = []
        self.go_home_callback = go_home_callback
        top = QHBoxLayout()
        self.back_btn = QPushButton("← Back"); self.folder_btn = QPushButton("Change folder")
        for b in (self.back_btn, self.folder_btn):
            b.setFixedHeight(26)
            b.setStyleSheet("QPushButton { padding:4px 8px; border-radius:6px; border:1px solid #3f3f3f; background:#2a2a2a; color:#f0f0f0; font-size:12px;} QPushButton:hover{background:#333}")
        top.addWidget(self.back_btn); top.addStretch(1); top.addWidget(self.folder_btn)
        self.flow_widget = QWidget(); self.flow_layout = FlowLayout(self.flow_widget, margin=12, hspacing=12, vspacing=12)
        self.flow_widget.setLayout(self.flow_layout)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setWidget(self.flow_widget)
        root = QVBoxLayout(self); root.addLayout(top); root.addWidget(self.scroll)
        self.folder_btn.clicked.connect(self.choose_folder)
        self.back_btn.clicked.connect(self.go_back)
        self.refresh()

    def go_back(self):
        if self.history:
            self.folder = self.history.pop()
            self.refresh()
        elif self.go_home_callback:
            self.go_home_callback()

    def open_subfolder(self, payload):
        path = payload.get("path")
        if path and Path(path).is_dir():
            self.history.append(self.folder)
            self.folder = path
            self.refresh()
    
    def list_items(self):
        p = Path(self.folder)
        if not p.is_dir():
            return [], []
        
        files = sorted([f for f in p.glob("*.ms") if f.is_file()])
        folders = []

        # Special logic: only show the 'advanced' subfolder when in the main scripts directory.
        try:
            main_scripts_dir_str = self.window().config.get("scripts_folder")
            if main_scripts_dir_str:
                main_scripts_dir = Path(resolve_rel_to_config(main_scripts_dir_str)).resolve()
                
                # Check if the current folder is the main scripts folder
                if p.resolve() == main_scripts_dir:
                    advanced_folder = p / "advanced"
                    if advanced_folder.is_dir():
                        folders.append(advanced_folder)
        except Exception:
            # Fallback or error, don't show any folders.
            pass
            
        return files, folders

    def refresh(self):
        # Iterate backwards to safely remove items
        for i in range(self.flow_layout.count() - 1, -1, -1):
            item = self.flow_layout.takeAt(i)
            w = item.widget()
            if w is not None:
                w.setParent(None); w.deleteLater()
        
        files, folders = self.list_items()
        
        if not files and not folders:
            lbl = QLabel("No .ms files or subfolders found"); lbl.setStyleSheet("color:#bbb;")
            self.flow_layout.addWidget(lbl); return

        # Add folder tiles first
        for folder_path in folders:
            payload = {"path": str(folder_path)}
            # Use a relative path; TileWidget will resolve it against the config path
            icon_path = "icons/folder.png"
            tile = TileWidget(folder_path.name, icon_path, payload, self.open_subfolder, self.flow_widget)
            self.flow_layout.addWidget(tile)

        for f in files:
            self.flow_layout.addWidget(ScriptTile(f, self.flow_widget))

        # Explicitly calculate and set the required height for the content.
        # This is the definitive fix for the "disappearing first tile" bug.
        viewport_width = self.scroll.viewport().width()
        margins = self.flow_layout.contentsMargins()
        effective_width = viewport_width - margins.left() - margins.right()
        required_height = self.flow_layout.heightForWidth(effective_width)
        self.flow_widget.setMinimumHeight(required_height)
        _force_repaint_by_resize(self.window())

    def choose_folder(self):
        dlg = QFileDialog(self); dlg.setFileMode(QFileDialog.Directory); dlg.setOption(QFileDialog.ShowDirsOnly, True)
        if dlg.exec():
            folders = dlg.selectedFiles()
            if folders:
                self.history.clear() # Start fresh history
                self.folder = folders[0]
                self.refresh()


# ---------------- fav apps panel (embedded) ----------------

class FavAppsWidget(QWidget):
    def __init__(self, parent=None, launcher=None):
        super().__init__(parent)
        self.launcher = launcher  # funkcja do odpalania ścieżek (sync_and_run_app)
        self.data = {}  # dict: {section_name: [ {label, path, icon?}, ... ]}

        top = QHBoxLayout()
        self.back_btn = QPushButton("← Back")
        for b in (self.back_btn,):
            b.setFixedHeight(26)
            b.setStyleSheet("QPushButton { padding:4px 8px; border-radius:6px; border:1px solid #3f3f3f; background:#2a2a2a; color:#f0f0f0; font-size:12px;} QPushButton:hover{background:#333}")
        top.addWidget(self.back_btn)
        top.addStretch(1)

        self.content = QWidget()
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(12, 12, 12, 12)
        self.content_layout.setSpacing(16)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.content)

        root = QVBoxLayout(self)
        root.addLayout(top)
        root.addWidget(scroll)

    def set_data(self, fav_apps: dict):
        self.data = fav_apps or {}
        self.rebuild()

    def clear_content(self):
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()

    def rebuild(self):
        self.clear_content()
        if not self.data:
            lbl = QLabel("No apps defined. Add entries under \"fav_apps\" in config.json.")
            lbl.setStyleSheet("color:#bbb;")
            self.content_layout.addWidget(lbl)
            return

        for section, items in self.data.items():
            # nagłówek sekcji
            h = QLabel(section.capitalize())
            h.setStyleSheet("color:#eaeaea; font-weight:700; font-size:14px;")
            self.content_layout.addWidget(h)

            # grid kafelków
            grid_wrap = QWidget()
            grid = FlowLayout(grid_wrap, margin=0, hspacing=12, vspacing=12)
            for it in (items or []):
                label = it.get("label", "App")
                path = it.get("path") or ""
                icon = it.get("icon") or ""
                tile = FavAppTile(label, path, icon, launcher=self._launch_app, parent=grid_wrap)
                grid.addWidget(tile)
            self.content_layout.addWidget(grid_wrap)

        self.content_layout.addStretch(1)

    def _launch_app(self, path: str):
        if not self.launcher:
            raise RuntimeError("No launcher connected")
        self.launcher(path)


LOCAL_VERSION_FILE = BASE_DIR / "version.json"

def read_local_version() -> str:
    try:
        with open(LOCAL_VERSION_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return str(data.get("version") or "")
    except Exception:
        return ""

def read_prod_version() -> str:
    try:
        manifest_path = getattr(autoupdate, "MANIFEST_PATH", None)
        if not manifest_path:
            return ""
        mp = Path(str(manifest_path))
        if not mp.exists():
            return ""
        data = json.loads(mp.read_text(encoding="utf-8"))
        return str(data.get("version") or "").strip()
    except Exception:
        return ""

def is_beta_version(local_ver: str) -> bool:
    local_ver = (local_ver or "").strip()
    if not local_ver:
        return False

    # If running from test folder, treat as beta immediately
    exe_path = str(Path(sys.executable).resolve()).lower()
    if "ogarniacz tests" in exe_path:
        return True

    prod_ver = read_prod_version()
    if not prod_ver:
        return False

    if pkg_version:
        try:
            return pkg_version.parse(local_ver) > pkg_version.parse(prod_ver)
        except Exception:
            return False

    # Fallback: string comparison (best effort)
    return local_ver > prod_ver


# ---------------- main window ----------------

class OgarniaczWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Ogarniacz SM")
        self.resize(1100, 760)
        self.config = {}; self.config_mtime = None; self.always_on_top = False
        top = QHBoxLayout(); self.title_label = QLabel("Ogarniacz SM"); self.title_label.setStyleSheet("color:#ddd; font-weight:600;"); top.addWidget(self.title_label, 1)
        self.refresh_btn = QPushButton("Refresh"); self.refresh_btn.clicked.connect(self.load_config_and_rebuild)
        self.refresh_btn.setContextMenuPolicy(Qt.CustomContextMenu)
        self.refresh_btn.customContextMenuRequested.connect(self.show_refresh_context_menu)
        self.update_btn = QPushButton("Update"); self.update_btn.clicked.connect(self.force_check_update)
        self.deps_btn = QPushButton("Deps"); self.deps_btn.clicked.connect(self.open_deps_dialog)
        self.aot_btn = QPushButton("Always on Top: OFF"); self.aot_btn.setCheckable(True); self.aot_btn.toggled.connect(self.toggle_always_on_top)
        for b in (self.refresh_btn, self.update_btn, self.deps_btn, self.aot_btn):
            b.setStyleSheet("QPushButton { padding:4px 8px; border-radius:6px; border:1px solid #3f3f3f; background:#242424; color:#f0f0f0; font-size:12px;} QPushButton:hover{background:#2c2c2c} QPushButton:pressed{background:#1f1f1f}"); b.setFixedHeight(28)
        top.addWidget(self.refresh_btn, 0); top.addWidget(self.update_btn, 0); top.addWidget(self.deps_btn, 0); top.addWidget(self.aot_btn, 0)
        self.stack = QStackedLayout()
        self.home_widget = QWidget()
        self.flow_widget = QWidget(self.home_widget)
        self.flow_layout = FlowLayout(self.flow_widget, margin=12, hspacing=12, vspacing=12)
        self.flow_widget.setLayout(self.flow_layout)
        self.scroll = QScrollArea(); self.scroll.setWidgetResizable(True); self.scroll.setWidget(self.flow_widget)
        home_root = QVBoxLayout(self.home_widget); home_root.addWidget(self.scroll)

        self.scripts_widget = ScriptsGridWidget(folder="", parent=None, go_home_callback=lambda: self.stack.setCurrentIndex(0))
        self.stack.addWidget(self.home_widget)
        self.stack.addWidget(self.scripts_widget)

        # --- Fav Apps panel (dodajemy teraz, PRZED root layoutem) ---
        self.favapps_widget = FavAppsWidget(parent=None, launcher=lambda p: self.sync_and_run_app(p))
        self.favapps_widget.back_btn.clicked.connect(lambda: self.stack.setCurrentIndex(0))
        self.stack.addWidget(self.favapps_widget)

        # --- People Enhancer panel ---
        self.people_enhancer_widget = PeopleEnhancerWidget(parent=None)
        self.people_enhancer_widget.set_back_callback(lambda: self.stack.setCurrentIndex(0))
        self.stack.addWidget(self.people_enhancer_widget)

        # --- Generic image workflows processed by Zeus ---
        self.zeus_workflows_widget = ZeusWorkflowsWidget(parent=None)
        self.zeus_workflows_widget.set_back_callback(lambda: self.stack.setCurrentIndex(0))
        self.stack.addWidget(self.zeus_workflows_widget)

        # The editor starts its independent service only when opened.
        self.archviz_studio_widget = None

        # --- layout główny ---
        root = QVBoxLayout(self)
        root.addLayout(top)
        root.addLayout(self.stack)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.check_config_update)
        self.apply_palette()
        self.load_config_and_rebuild()



    def apply_palette(self):
        self.setStyleSheet("QWidget { background-color: #1a1a1a; color: #e6e6e6; } QScrollArea { border: none; }")

    def read_config(self):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)

    def load_config_and_rebuild(self):
        try:
            cfg = self.read_config()
            self.config = cfg
            self.config_mtime = os.path.getmtime(CONFIG_PATH)

            app_icon = resolve_rel_to_config(cfg.get("app_icon"))
            if app_icon and Path(app_icon).exists():
                self.setWindowIcon(QIcon(app_icon))

            ver_local = read_local_version()
            ver_cfg = str(cfg.get("version", "")).strip()
            ver = ver_local or ver_cfg or "?"
            beta_suffix = " (beta - not published)" if is_beta_version(ver_local or ver) else ""
            self.title_label.setText(f"Ogarniacz SM — v{ver}{beta_suffix}")


            secs = int(cfg.get("auto_refresh_seconds", 180))
            self.timer.stop()
            if secs > 0:
                self.timer.start(secs * 1000)

            scripts_folder = cfg.get("scripts_folder") or r"Y:\\Instalki\\_SKRYPTY WIKT\\Still Motion Scripts"
            self.scripts_widget.folder = resolve_rel_to_config(scripts_folder)
            self.scripts_widget.refresh()

            # <<< to jest właściwe miejsce, żeby odświeżyć dane Fav Apps >>>
            self.favapps_widget.set_data(cfg.get("fav_apps", {}))

            self.rebuild_home_tiles()
        except Exception as e:
            QMessageBox.critical(self, "Config error", f"Failed to load config.json:\n{e}")



    def show_refresh_context_menu(self, pos):
        menu = QMenu(self)
        post_action = menu.addAction("Post ogarniacz update (wiktor only)")
        test_action = menu.addAction("Test ogarniacz changes (wiktor only)")
        menu.addSeparator()
        deps_action = menu.addAction("Install/Repair python deps (all modules)")
        post_action.triggered.connect(self.open_post_update_dialog)
        test_action.triggered.connect(self.open_test_update_dialog)
        deps_action.triggered.connect(self.open_deps_dialog)
        menu.exec(self.refresh_btn.mapToGlobal(pos))

    def open_deps_dialog(self):
        """
        Installs/repairs dependencies for python-based modules referenced by config.json.
        Best-effort:
        - ensure python exists (tries winget if missing)
        - pip install required packages inferred from scripts
        - checks Poppler availability for pdf2image-based scripts
        """
        dlg = QDialog(self)
        dlg.setWindowTitle("Dependencies")
        dlg.setModal(True)
        dlg.resize(760, 520)

        layout = QVBoxLayout(dlg)
        info = QLabel(
            "This will try to install/repair Python + pip packages required by python modules (tiles of type 'python').\n"
            "It installs system dependencies on THIS PC.\n\n"
            "Notes:\n"
            "- PDF conversion needs Poppler (pdftoppm). If missing, PDF->JPG may fail until Poppler is installed/added to PATH.\n"
            "- Scanner features may require device drivers on this PC."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        log_box = QTextEdit()
        log_box.setReadOnly(True)
        log_box.setStyleSheet("QTextEdit { background:#111; border:1px solid #333; }")
        layout.addWidget(log_box, 1)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        run_btn = QPushButton("Install / Repair")
        close_btn = QPushButton("Close")
        btn_row.addWidget(run_btn)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

        close_btn.clicked.connect(dlg.reject)

        def log(msg: str):
            log_box.append(msg)
            log_box.ensureCursorVisible()

        def worker():
            try:
                log(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Starting dependency check...")

                # Load config fresh (in case UI has stale config)
                try:
                    cfg = self.read_config()
                except Exception as e:
                    log(f"[!] Failed to read config.json: {e}")
                    return

                python_tiles = []
                for t in (cfg.get('tiles') or []):
                    if str(t.get('type') or '').strip().lower() == 'python' and t.get('path'):
                        python_tiles.append(resolve_rel_to_config(t.get('path')))

                if not python_tiles:
                    log("[i] No python tiles found in config.json. Nothing to install.")
                    return

                log(f"[i] Python tiles found: {len(python_tiles)}")
                for p in python_tiles:
                    log(f"    - {p}")

                py = find_python_exe()
                if not py:
                    py = ensure_python_installed(log)
                else:
                    log(f"[i] Python detected: {py}")

                if not py:
                    log("[!] Python not available. Install Python 3.12+ and try again.")
                    return

                # Infer package set
                pip_pkgs = set()
                needs_poppler = False
                for script in python_tiles:
                    pkgs, external = infer_pip_packages_from_script(script)
                    pip_pkgs |= set(pkgs)
                    if 'poppler' in external:
                        needs_poppler = True

                if pip_pkgs:
                    log(f"[i] Installing pip packages: {', '.join(sorted(pip_pkgs))}")
                    ok = pip_install(py, sorted(pip_pkgs), log)
                    if not ok:
                        log("[!] Some pip packages failed to install. See output above.")
                        return
                else:
                    log("[i] No pip packages inferred from scripts.")

                if needs_poppler:
                    if poppler_available():
                        log("[i] Poppler OK (pdftoppm found).")
                    else:
                        log("[i] Poppler not found — installing automatically...")
                        bin_path = install_poppler_silent(log)
                        if bin_path:
                            log(f"[OK] Poppler ready: {bin_path}")
                        else:
                            log("[!] Poppler auto-install failed. PDF Magician may not work.")
                            log("    Manual install: https://github.com/oschwartz10612/poppler-windows/releases/")

                log(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Done.")
            except Exception as e:
                log(f"[!] Dependency installer crashed: {e}\n{traceback.format_exc()}")

        def start():
            run_btn.setEnabled(False)
            self.deps_btn.setEnabled(False)
            log_box.clear()

            th = threading.Thread(target=worker, daemon=True)
            th.start()

            # Re-enable after a short delay (best-effort; avoids UI getting stuck if worker errors early)
            def reenable():
                run_btn.setEnabled(True)
                self.deps_btn.setEnabled(True)
            QTimer.singleShot(2000, reenable)

        run_btn.clicked.connect(start)
        dlg.exec()

    def open_post_update_dialog(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Post ogarniacz update (wiktor only)")
        dlg.setModal(True)
        dlg.resize(520, 160)

        layout = QVBoxLayout(dlg)
        info = QLabel(
            "This will build and publish a new OgarniaczSM update by running publish.bat.\n"
            "Use only on the main dev machine."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        run_btn = QPushButton("Post update")
        cancel_btn = QPushButton("Cancel")
        buttons.addWidget(run_btn)
        buttons.addWidget(cancel_btn)
        layout.addLayout(buttons)

        cancel_btn.clicked.connect(dlg.reject)
        run_btn.clicked.connect(lambda: self._run_post_update_from_dialog(dlg))

        dlg.exec()

    def _run_post_update_from_dialog(self, dlg: QDialog):
        if not self._authorize_post_update():
            return
        if self._start_publish_update():
            dlg.accept()

    def open_test_update_dialog(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Test ogarniacz changes (wiktor only)")
        dlg.setModal(True)
        dlg.resize(520, 170)

        layout = QVBoxLayout(dlg)
        info = QLabel(
            "This will build a test version and copy it to:\n"
            "C:\\Ogarniacz Tests\n\n"
            "It will not publish to PROD."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        run_btn = QPushButton("Build test version")
        cancel_btn = QPushButton("Cancel")
        buttons.addWidget(run_btn)
        buttons.addWidget(cancel_btn)
        layout.addLayout(buttons)

        cancel_btn.clicked.connect(dlg.reject)
        run_btn.clicked.connect(lambda: self._run_test_update_from_dialog(dlg))

        dlg.exec()

    def _run_test_update_from_dialog(self, dlg: QDialog):
        if not self._authorize_post_update():
            return
        if self._start_test_update():
            dlg.accept()

    def _authorize_post_update(self) -> bool:
        hostname = os.environ.get("COMPUTERNAME", "").strip()
        if hostname.lower() == "blade22":
            return True

        pin, ok = QInputDialog.getText(
            self,
            "Post ogarniacz update (wiktor only)",
            "Enter safety PIN:",
            QLineEdit.Password
        )
        if not ok:
            return False
        if pin.strip() != "5225":
            QMessageBox.warning(self, "Invalid PIN", "Wrong safety PIN.")
            return False
        return True

    def _start_publish_update(self) -> bool:
        candidates = [
            CONFIG_PATH.parent / "publish.bat",
            BASE_DIR / "publish.bat",
            BASE_DIR.parent / "publish.bat",
        ]
        publish_bat = next((p for p in candidates if p.exists()), None)
        if not publish_bat:
            QMessageBox.critical(
                self,
                "Publish not found",
                "Could not find publish.bat.\n\n"
                f"Checked:\n- {candidates[0]}\n- {candidates[1]}\n- {candidates[2]}"
            )
            return False
        try:
            subprocess.Popen(
                ["cmd", "/k", str(publish_bat)],
                cwd=str(publish_bat.parent),
                shell=False
            )
            QMessageBox.information(
                self,
                "Publishing started",
                f"Started:\n{publish_bat}\n\nA console window will show progress."
            )
            return True
        except Exception as e:
            QMessageBox.critical(self, "Publish error", f"Failed to start publish:\n{e}")
            return False

    def _start_test_update(self) -> bool:
        candidates = [
            CONFIG_PATH.parent / "test_publish.bat",
            BASE_DIR / "test_publish.bat",
            BASE_DIR.parent / "test_publish.bat",
        ]
        test_bat = next((p for p in candidates if p.exists()), None)
        if not test_bat:
            QMessageBox.critical(
                self,
                "Test publish not found",
                "Could not find test_publish.bat.\n\n"
                f"Checked:\n- {candidates[0]}\n- {candidates[1]}\n- {candidates[2]}"
            )
            return False

        try:
            subprocess.Popen(
                ["cmd", "/k", str(test_bat)],
                cwd=str(test_bat.parent),
                shell=False
            )
            QMessageBox.information(
                self,
                "Test build started",
                f"Started:\n{test_bat}\n\nA console window will show progress."
            )
            return True
        except Exception as e:
            QMessageBox.critical(self, "Test publish error", f"Failed to start test build:\n{e}")
            return False

    def check_config_update(self):
        try:
            mtime = os.path.getmtime(CONFIG_PATH)
            if self.config_mtime is None or mtime != self.config_mtime:
                self.load_config_and_rebuild()
        except Exception:
            pass

    def clear_flow(self):
        # Iterate backwards to safely remove items
        for i in range(self.flow_layout.count() - 1, -1, -1):
            item = self.flow_layout.takeAt(i)
            w = item.widget()
            if w is not None:
                w.setParent(None); w.deleteLater()

    def rebuild_home_tiles(self):
        self.clear_flow()
        tiles = list(self.config.get("tiles", []))
        if not any(str(t.get("action", "")).lower() in
                   ("open_archviz_studio", "archviz_studio", "archviz") for t in tiles):
            tiles.append({"label": "Archviz Studio", "type": "internal",
                          "action": "open_archviz_studio",
                          "tile_icon": str(Path(__file__).resolve().parent / "archviz_studio_widget.png")})
        for t in tiles:
            label = t.get("label", "Tile"); icon_path = t.get("tile_icon", "")
            if str(t.get("action", "")).lower() in ("open_archviz_studio", "archviz_studio", "archviz"):
                if not icon_path or not Path(resolve_rel_to_config(icon_path)).is_file():
                    icon_path = str(Path(__file__).resolve().parent / "archviz_studio_widget.png")
            w = TileWidget(label, icon_path, t, self.launch_payload, self.flow_widget)
            self.flow_layout.addWidget(w)

        # Explicitly calculate and set the required height for the content.
        # This is the definitive fix for the "disappearing first tile" bug.
        viewport_width = self.scroll.viewport().width()
        margins = self.flow_layout.contentsMargins()
        effective_width = viewport_width - margins.left() - margins.right()
        required_height = self.flow_layout.heightForWidth(effective_width)
        self.flow_widget.setMinimumHeight(required_height)
        _force_repaint_by_resize(self)

    # --------- sync & run for apps (local cache) ---------
    def sync_and_run_app(self, path, args=""):
        if not path: raise RuntimeError("App path is empty.")
        src = Path(resolve_rel_to_config(path))
        if not src.exists(): raise RuntimeError(f"App not found: {src}")
        dst = Path(os.environ["LOCALAPPDATA"]) / "StillMotion" / "bin" / src.name
        dst.parent.mkdir(parents=True, exist_ok=True)
        if (not dst.exists()) or (src.stat().st_mtime > dst.stat().st_mtime):
            shutil.copy2(src, dst)
        cmd = [str(dst)];
        if args: cmd += args.split(" ")
        subprocess.Popen(cmd, shell=False)

    def toggle_always_on_top(self, checked):
        self.always_on_top = checked
        self.aot_btn.setText("Always on Top: ON" if checked else "Always on Top: OFF")
        flags = self.windowFlags();
        self.setWindowFlags((flags | Qt.WindowStaysOnTopHint) if checked else (flags & ~Qt.WindowStaysOnTopHint))
        self.show()

    def force_check_update(self):
        """Force check for updates and show result to user"""
        self.update_btn.setEnabled(False)
        self.update_btn.setText("Checking...")
        try:
            # Read current versions
            local_ver = read_local_version() or "0.0.0"
            prod_ver = read_prod_version() or "0.0.0"
            
            # Check if update is available
            update_available = False
            if pkg_version:
                try:
                    update_available = pkg_version.parse(prod_ver) > pkg_version.parse(local_ver)
                except Exception:
                    # Fallback to string comparison
                    update_available = prod_ver > local_ver
            else:
                update_available = prod_ver > local_ver
            
            if update_available:
                # Ask user if they want to update now
                reply = QMessageBox.question(
                    self,
                    "Update Available",
                    f"An update is available!\n\n"
                    f"Current version: v{local_ver}\n"
                    f"Available version: v{prod_ver}\n\n"
                    f"The app will close and restart after updating.\n\n"
                    f"Update now?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.Yes
                )
                if reply == QMessageBox.Yes:
                    # This will exit the app and launch updater
                    try:
                        autoupdate.check_for_updates_once(silent=False)
                        # If we get here, update check failed (shouldn't happen)
                        QMessageBox.warning(
                            self,
                            "Update Failed",
                            f"Update check failed. Check autoupdate.log:\n{autoupdate.LOG_FILE}"
                        )
                    except Exception as e:
                        QMessageBox.warning(
                            self,
                            "Update Error",
                            f"Failed to start update:\n\n{str(e)}\n\n"
                            f"Check autoupdate.log for details:\n{autoupdate.LOG_FILE}"
                        )
            else:
                # No update available
                QMessageBox.information(
                    self,
                    "Update Check",
                    f"You are running the latest version.\n\n"
                    f"Current version: v{local_ver}\n"
                    f"Published version: v{prod_ver}"
                )
        except FileNotFoundError as e:
            QMessageBox.warning(
                self,
                "Update Check",
                f"Update check failed:\n\n{str(e)}\n\n"
                f"Make sure you have access to:\n{autoupdate.MANIFEST_PATH}"
            )
        except Exception as e:
            QMessageBox.warning(
                self,
                "Update Check",
                f"Update check failed:\n\n{str(e)}\n\n"
                f"Check autoupdate.log for details:\n{autoupdate.LOG_FILE}"
            )
        finally:
            self.update_btn.setEnabled(True)
            self.update_btn.setText("Update")

    def launch_payload(self, payload):
        t = payload.get("type")
        if t == "app":
            self.sync_and_run_app(payload.get("path"), payload.get("args", ""))
        elif t == "folder":
            self.open_folder(payload.get("path"))
        elif t == "maxscript":
            self.run_maxscript(payload.get("path"))
        elif t == "markdown":
            self.show_markdown(payload.get("path"))
        elif t == "python": 
            self.run_python_script(payload.get("path"))
        elif t == "internal":
            self.run_internal(payload.get("action"), payload)
        else:
            raise RuntimeError(f"Unknown tile type: {t}")

    def open_folder(self, path):
        if not path: raise RuntimeError("Folder path is empty.")
        subprocess.Popen(["explorer", resolve_rel_to_config(path)])

    def run_maxscript(self, script_path):
        if not script_path: raise RuntimeError("MaxScript path is empty.")
        script_path = resolve_rel_to_config(script_path)
        if not Path(script_path).exists(): raise RuntimeError(f"MaxScript not found: {script_path}")
        max_exe = self.config.get("max_exe") or "3dsmax.exe"
        cmd = [max_exe, "-U", "MAXScript", script_path]
        subprocess.Popen(cmd, shell=False)

    def show_markdown(self, md_path):
        md_path = resolve_rel_to_config(md_path)
        if not md_path or not Path(md_path).exists(): raise RuntimeError(f"Markdown file not found: {md_path}")
        dlg = MarkdownDialog(md_path, self); dlg.exec()

    def run_internal(self, action, payload=None):
        act = (action or "").strip().lower()

        if act in ("open_archviz_studio", "archviz_studio", "archviz"):
            if self.archviz_studio_widget is None:
                from archviz_studio_widget import ArchvizStudioWidget
                self.archviz_studio_widget = ArchvizStudioWidget(parent=None)
                self.archviz_studio_widget.set_back_callback(lambda: self.stack.setCurrentIndex(0))
                self.stack.addWidget(self.archviz_studio_widget)
            self.resize(max(1400, self.width()), max(900, self.height()))
            self.stack.setCurrentWidget(self.archviz_studio_widget)
            return

        # 1) Wbudowany panel skryptów
        if act in ("", "open_maxscripts_panel", "open_scripts", "scripts", "scripts_panel"):
            if not self.scripts_widget.folder:
                self.scripts_widget.folder = r"Y:\\Instalki\\_SKRYPTY WIKT\\Still Motion Scripts"
            self.scripts_widget.history.clear()
            self.scripts_widget.refresh()
            self.stack.setCurrentIndex(1)
            return

        # 2b) People Enhancer panel
        if act in ("open_people_enhancer", "people_enhancer", "enhance_people"):
            self.stack.setCurrentIndex(3)  # 0:home, 1:scripts, 2:favapps, 3:people_enhancer
            return

        # 2c) Generic Zeus render workflows
        if act in ("open_zeus_workflows", "zeus_workflows", "ai_workflows"):
            self.stack.setCurrentIndex(4)  # 4: Zeus AI workflows
            return

        # 2) Wbudowany panel Fav Apps
        if act in ("open_fav_apps", "fav_apps", "favorites", "apps"):
            self.favapps_widget.set_data(self.config.get("fav_apps", {}))
            self.stack.setCurrentIndex(2)  # 0: home, 1: scripts, 2: fav apps
            return

        # 3) Uruchamianie zewnętrznej aplikacji z payload
        if act in ("open_external", "run_app") and payload and payload.get("path"):
            self.sync_and_run_app(payload.get("path"))
            return

        # 4) Fallback: jeśli jest path w payload, spróbuj uruchomić
        if payload and payload.get("path"):
            p = resolve_rel_to_config(payload.get("path"))
            if Path(p).exists():
                self.sync_and_run_app(p)
                return

        # 5) Brak obsługi
        QMessageBox.information(self, "Internal", f"No handler for action: {action}")


# ---------------- python handler ----------------

    def run_python_script(self, script_path):
        """
        Run a Python script using the system Python interpreter.
        Automatically installs any missing pip packages and Poppler before launching.
        """
        if not script_path:
            raise RuntimeError("Python script path is empty.")

        script_path = resolve_rel_to_config(script_path)
        script_file = Path(script_path)

        if not script_file.exists():
            raise RuntimeError(f"Python script not found: {script_path}")

        python_exe = find_python_exe()

        if not python_exe and not getattr(sys, "frozen", False):
            python_exe = sys.executable

        if not python_exe:
            QMessageBox.critical(
                self,
                "Python Not Found",
                "Could not find Python interpreter.\n\n"
                "Please install Python from https://python.org and try again."
            )
            return

        # Infer required packages from the script
        pip_pkgs, external_tools = infer_pip_packages_from_script(str(script_file))
        needs_poppler = "poppler" in external_tools

        # Check which pip packages are actually missing
        missing_pkgs = []
        for pkg in pip_pkgs:
            # Map pip package name to importable module name for the check
            mod_check = {
                "pdf2image": "pdf2image",
                "Pillow": "PIL",
                "pywin32": "win32com",
                "numpy": "numpy",
                "opencv-python": "cv2",
            }.get(pkg, pkg)
            check = subprocess.run(
                [python_exe, "-c", f"import {mod_check}"],
                capture_output=True
            )
            if check.returncode != 0:
                missing_pkgs.append(pkg)

        poppler_missing = needs_poppler and not poppler_available()

        # If anything is missing, install silently with a progress dialog
        if missing_pkgs or poppler_missing:
            dlg = QDialog(self)
            dlg.setWindowTitle("Setting up…")
            dlg.setModal(True)
            dlg.resize(520, 300)
            layout = QVBoxLayout(dlg)
            lbl = QLabel(f"Installing dependencies for <b>{script_file.name}</b>…")
            lbl.setWordWrap(True)
            layout.addWidget(lbl)
            log_box = QTextEdit()
            log_box.setReadOnly(True)
            log_box.setStyleSheet("QTextEdit { background:#111; border:1px solid #333; }")
            layout.addWidget(log_box, 1)
            dlg.show()

            def log(msg):
                log_box.append(msg)
                log_box.ensureCursorVisible()
                QApplication.processEvents()

            if missing_pkgs:
                log(f"[i] Installing: {', '.join(missing_pkgs)}")
                ok = pip_install(python_exe, missing_pkgs, log)
                if not ok:
                    log("[!] Some packages failed to install. The script may not work correctly.")

            if poppler_missing:
                log("[i] Installing Poppler (PDF support)…")
                bin_path = install_poppler_silent(log)
                if bin_path:
                    log(f"[OK] Poppler ready: {bin_path}")
                else:
                    log("[!] Poppler install failed — PDF conversion may not work.")

            log("[i] Done. Launching script…")
            QTimer.singleShot(800, dlg.accept)
            dlg.exec()

        # Launch the script
        try:
            subprocess.Popen([python_exe, str(script_file)], shell=False)
        except Exception as e:
            QMessageBox.critical(self, "Script Error", f"Failed to run Python script:\n{e}")

# ---------------- entry ----------------

def main():
    QApplication.setAttribute(Qt.AA_ShareOpenGLContexts)
    app = QApplication(sys.argv)

    # --- Splash (prosty, lekki) ---
    pix = QPixmap(420, 180)
    pix.fill(Qt.black)  # tło
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setPen(Qt.white)
    p.setFont(QFont("Segoe UI", 20, QFont.Weight.Bold))
    p.drawText(pix.rect().adjusted(0, 30, 0, -90), Qt.AlignHCenter | Qt.AlignVCenter, "Ogarniacz SM")
    p.setFont(QFont("Segoe UI", 11))
    p.drawText(pix.rect().adjusted(0, 90, 0, 0), Qt.AlignHCenter | Qt.AlignTop, "Loading… Please wait")
    p.end()

    splash = QSplashScreen(pix)
    splash.setWindowFlag(Qt.FramelessWindowHint, True)
    splash.setWindowFlag(Qt.WindowStaysOnTopHint, True)
    splash.show()
    app.processEvents()  # pokaż od razu

    # --- Główne okno ---
    win = OgarniaczWindow()
    win.show()
    if "--archviz-studio" in sys.argv:
        win.run_internal("open_archviz_studio")

     # AUTO UPDATE
    try:
        autoupdate.check_for_updates_once(silent=True)
        autoupdate.start_periodic_update_check(900)
    except Exception:
        pass

    # zamknij splash chwilę po pierwszym kadrze (gdy UI już stoi)
    QTimer.singleShot(200, splash.close)

    sys.exit(app.exec())

if __name__ == "__main__":
    try:
        if "--archviz-server" in sys.argv:
            from archviz_server import run_server
            import argparse
            parser = argparse.ArgumentParser()
            parser.add_argument("--archviz-server", action="store_true")
            parser.add_argument("--port", type=int, default=8890)
            parser.add_argument("--registry")
            args = parser.parse_args()
            run_server(args.port, args.registry)
        elif "--archviz-pick" in sys.argv:
            from archviz_cli import pick_result
            import argparse
            parser = argparse.ArgumentParser()
            parser.add_argument("--archviz-pick", choices=["folder", "image", "images"])
            parser.add_argument("--result-file")
            args = parser.parse_args()
            pick_result(args.archviz_pick, args.result_file)
        else:
            main()
    except Exception as e:
        import traceback
        msg = "Unhandled error:\n\n" + str(e) + "\n\n" + traceback.format_exc()
        try:
            ctypes.windll.user32.MessageBoxW(0, msg, "OgarniaczSM – crash", 0x10)
        except Exception:
            pass
        sys.exit(1)
