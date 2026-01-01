from pathlib import Path
import sys
import os
import json
import subprocess
import ctypes
import shutil
import autoupdate


from PySide6.QtWidgets import QSplashScreen
from PySide6.QtGui import QPainter, QFont
from PySide6.QtCore import Qt, QTimer, QSize, QPoint, QRect
from PySide6.QtGui import QIcon, QPixmap, QMouseEvent
from PySide6.QtWidgets import (
    QApplication, QWidget, QPushButton, QScrollArea, QVBoxLayout, QHBoxLayout,
    QMessageBox, QLabel, QTextEdit, QDialog, QSizePolicy, QLayout, QFrame,
    QStackedLayout, QFileDialog
)

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
    import traceback
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

# ---------------- layout helper ----------------

class FlowLayout(QLayout):
    def __init__(self, parent=None, margin=8, hspacing=20, vspacing=12):
        super().__init__(parent)
        self._items = []
        self.setContentsMargins(margin, margin, margin, margin)
        self._hspace = hspacing
        self._vspace = vspacing

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index):
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self):
        return Qt.Orientations(Qt.Orientation(0))

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._do_layout(QRect(0, 0, width, 0), True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, False)

    def sizeHint(self):
        return QSize(400, 300)

    def _do_layout(self, rect, test_only):
        x = rect.x(); y = rect.y(); line_height = 0
        for item in self._items:
            wid = item.widget() if hasattr(item, "widget") else None
            if wid is None or not wid.isVisible():
                continue
            space_x = self._hspace; space_y = self._vspace
            next_x = x + item.sizeHint().width() + space_x
            if next_x - space_x > rect.right() and line_height > 0:
                x = rect.x(); y = y + line_height + space_y
                next_x = x + item.sizeHint().width() + space_x
                line_height = 0
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), item.sizeHint()))
            x = next_x
            line_height = max(line_height, item.sizeHint().height())
        return y + line_height - rect.y()

# ---------------- markdown dialog ----------------

class MarkdownDialog(QDialog):
    def __init__(self, path, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Markdown: {Path(path).name}")
        self.resize(800, 600)
        layout = QVBoxLayout(self)
        self.text = QTextEdit(self)
        self.text.setReadOnly(True)
        layout.addWidget(self.text)
        try:
            with open(path, "r", encoding="utf-8") as f:
                self.text.setPlainText(f.read())
        except Exception as e:
            self.text.setPlainText(f"Failed to open markdown:\n{e}")

# ---------------- home tile ----------------

class TileWidget(QFrame):
    def __init__(self, label, icon_path, payload, launcher, parent=None):
        super().__init__(parent)
        self.payload = payload
        self.launcher = launcher
        self.setObjectName("tile")
        self.setMinimumSize(QSize(200, 220))
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.setStyleSheet(
            """
            QFrame#tile { border-radius: 12px; border: 1px solid #3f3f3f; background: #242424; }
            QFrame#tile:hover { background: #2c2c2c; }
            QLabel#tilelabel { color:#f0f0f0; font-weight:600; }
            """
        )
        v = QVBoxLayout(self)
        v.setContentsMargins(12, 12, 12, 12)
        v.setSpacing(5)
        self.icon_label = QLabel(self)
        self.icon_label.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
        self.icon_label.setFixedSize(96, 96)
        self.icon_label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.set_icon(icon_path)
        self.text_label = QLabel(label, self)
        self.text_label.setObjectName("tilelabel")
        self.text_label.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
        self.text_label.setWordWrap(True)
        self.text_label.setMaximumWidth(200)
        v.addWidget(self.icon_label, alignment=Qt.AlignHCenter)
        v.addWidget(self.text_label, alignment=Qt.AlignHCenter)

    def set_icon(self, icon_path):
        if icon_path:
            icon_path = resolve_rel_to_config(icon_path)
        pix = None
        if icon_path and Path(icon_path).exists():
            pix = QPixmap(str(icon_path))
        if not pix or pix.isNull():
            pix = QPixmap(96, 96); pix.fill(Qt.transparent)
        scaled = pix.scaled(96, 96, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.icon_label.setPixmap(scaled)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            try:
                self.launcher(self.payload)
            except Exception as e:
                QMessageBox.critical(self, "Launch error", str(e))
        super().mousePressEvent(event)

# ---------------- embedded scripts panel ----------------

class ScriptTile(QFrame):
    def __init__(self, script_path: Path, parent=None):
        super().__init__(parent)
        self.script_path = script_path
        self._drag_start = None
        self.setObjectName("scripttile")
        self.setMinimumSize(QSize(160, 170))
        self.setMaximumWidth(200)
        self.setCursor(Qt.OpenHandCursor)
        self.setStyleSheet(
            """
            QFrame#scripttile { border-radius: 12px; border: 1px solid #3f3f3f; background: #242424; }
            QFrame#scripttile:hover { background: #2c2c2c; }
            QLabel#name { color:#f0f0f0; font-weight:500; }
            """
        )
        v = QVBoxLayout(self)
        v.setContentsMargins(12, 12, 12, 12)
        v.setSpacing(8)
        icon_lbl = QLabel(self)
        icon_lbl.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
        icon_lbl.setFixedSize(96, 96)
        icon_lbl.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        icon = self._load_icon_for_script(script_path)
        icon_lbl.setPixmap(icon)
        name_lbl = QLabel(script_path.stem, self)
        name_lbl.setObjectName("name")
        name_lbl.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
        name_lbl.setWordWrap(True)
        name_lbl.setMaximumWidth(180)
        v.addWidget(icon_lbl, alignment=Qt.AlignHCenter)
        v.addWidget(name_lbl, alignment=Qt.AlignHCenter)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag_start = e.position().toPoint()
            self.setCursor(Qt.ClosedHandCursor)
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._drag_start is not None and (e.position().toPoint() - self._drag_start).manhattanLength() >= 8:
            self._start_drag(); self._drag_start = None
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        self.setCursor(Qt.OpenHandCursor); self._drag_start = None
        super().mouseReleaseEvent(e)

    def _start_drag(self):
        if not self.script_path.exists():
            return
        from PySide6.QtCore import QMimeData, QUrl
        from PySide6.QtGui import QDrag
        md = QMimeData(); md.setUrls([QUrl.fromLocalFile(str(self.script_path))])
        drag = QDrag(self); drag.setMimeData(md)
        drag.setPixmap(QPixmap(96, 96)); drag.exec(Qt.CopyAction)

    def _load_icon_for_script(self, script_path: Path) -> QPixmap:
        png = script_path.with_suffix(".png")
        if png.exists():
            pix = QPixmap(str(png))
            if not pix.isNull():
                return pix.scaled(96, 96, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        pm = QPixmap(96, 96); pm.fill(Qt.darkGray)
        from PySide6.QtGui import QPainter, QColor, QFont
        p = QPainter(pm); p.setPen(Qt.white); p.setFont(QFont("Segoe UI", 16, QFont.Weight.DemiBold))
        p.drawText(pm.rect(), Qt.AlignCenter, script_path.stem[:3]); p.end()
        return pm

class ScriptsGridWidget(QWidget):
    def __init__(self, folder: str, parent=None):
        super().__init__(parent)
        self.folder = folder
        top = QHBoxLayout()
        self.back_btn = QPushButton("← Back"); self.refresh_btn = QPushButton("Refresh"); self.folder_btn = QPushButton("Change folder")
        for b in (self.back_btn, self.refresh_btn, self.folder_btn):
            b.setFixedHeight(30)
            b.setStyleSheet("QPushButton { padding:6px 10px; border-radius:8px; border:1px solid #3f3f3f; background:#2a2a2a; color:#f0f0f0;} QPushButton:hover{background:#333}")
        top.addWidget(self.back_btn); top.addStretch(1); top.addWidget(self.refresh_btn); top.addWidget(self.folder_btn)
        self.flow_widget = QWidget(); self.flow_layout = FlowLayout(self.flow_widget, margin=12, hspacing=12, vspacing=12)
        self.flow_widget.setLayout(self.flow_layout)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setWidget(self.flow_widget)
        root = QVBoxLayout(self); root.addLayout(top); root.addWidget(scroll)
        self.refresh_btn.clicked.connect(self.refresh); self.folder_btn.clicked.connect(self.choose_folder)
        self.refresh()

    def list_ms(self):
        p = Path(self.folder)
        return sorted([f for f in p.glob("*.ms") if f.is_file()]) if p.exists() else []

    def refresh(self):
        while self.flow_layout.count():
            item = self.flow_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None); w.deleteLater()
        files = self.list_ms()
        if not files:
            lbl = QLabel("No .ms files found"); lbl.setStyleSheet("color:#bbb;")
            self.flow_layout.addWidget(lbl); return
        for f in files:
            self.flow_layout.addWidget(ScriptTile(f, self.flow_widget))
        self.flow_layout.invalidate(); self.flow_widget.adjustSize(); self.flow_widget.updateGeometry(); self.flow_widget.repaint()

    def choose_folder(self):
        dlg = QFileDialog(self); dlg.setFileMode(QFileDialog.Directory); dlg.setOption(QFileDialog.ShowDirsOnly, True)
        if dlg.exec():
            folders = dlg.selectedFiles()
            if folders:
                self.folder = folders[0]; self.refresh()


# ---------------- fav apps panel (embedded) ----------------

class FavAppTile(QFrame):
    ICON_SIZE = QSize(96, 96)

    def __init__(self, label: str, path: str, icon_path: str | None, launcher, parent=None):
        super().__init__(parent)
        self.label = label
        self.path = path
        self.launcher = launcher

        self.setObjectName("scripttile")
        self.setMinimumSize(QSize(160, 170))
        self.setMaximumWidth(200)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet(
            """
            QFrame#scripttile { border-radius: 12px; border: 1px solid #3f3f3f; background: #242424; }
            QFrame#scripttile:hover { background: #2c2c2c; }
            QLabel#name { color:#f0f0f0; font-weight:500; }
            """
        )
        v = QVBoxLayout(self)
        v.setContentsMargins(12, 12, 12, 12)
        v.setSpacing(8)

        icon_lbl = QLabel(self)
        icon_lbl.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
        icon_lbl.setFixedSize(self.ICON_SIZE)
        icon_lbl.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        icon_lbl.setPixmap(self._load_icon(icon_path, label))

        name_lbl = QLabel(label, self)
        name_lbl.setObjectName("name")
        name_lbl.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
        name_lbl.setWordWrap(True)
        name_lbl.setMaximumWidth(180)

        v.addWidget(icon_lbl, alignment=Qt.AlignHCenter)
        v.addWidget(name_lbl, alignment=Qt.AlignHCenter)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            try:
                self.launcher(self.path)
            except Exception as ex:
                QMessageBox.critical(self, "Launch error", str(ex))
        super().mousePressEvent(e)

    def _load_icon(self, icon_path: str | None, text: str) -> QPixmap:
        pm = None
        if icon_path:
            icon_abs = resolve_rel_to_config(icon_path)
            p = Path(icon_abs)
            if p.exists():
                pm = QPixmap(str(p))
        if not pm or pm.isNull():
            # placeholder z inicjałami
            pm = QPixmap(self.ICON_SIZE)
            pm.fill(Qt.darkGray)
            from PySide6.QtGui import QPainter, QFont
            painter = QPainter(pm)
            painter.setPen(Qt.white)
            painter.setFont(QFont("Segoe UI", 16, QFont.Weight.DemiBold))
            painter.drawText(pm.rect(), Qt.AlignCenter, (text or "APP")[:3])
            painter.end()
        return pm.scaled(self.ICON_SIZE, Qt.KeepAspectRatio, Qt.SmoothTransformation)


class FavAppsWidget(QWidget):
    def __init__(self, parent=None, launcher=None):
        super().__init__(parent)
        self.launcher = launcher  # funkcja do odpalania ścieżek (sync_and_run_app)
        self.data = {}  # dict: {section_name: [ {label, path, icon?}, ... ]}

        top = QHBoxLayout()
        self.back_btn = QPushButton("← Back")
        self.refresh_btn = QPushButton("Refresh")
        for b in (self.back_btn, self.refresh_btn):
            b.setFixedHeight(30)
            b.setStyleSheet("QPushButton { padding:6px 10px; border-radius:8px; border:1px solid #3f3f3f; background:#2a2a2a; color:#f0f0f0;} QPushButton:hover{background:#333}")
        top.addWidget(self.back_btn)
        top.addStretch(1)
        top.addWidget(self.refresh_btn)

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

        self.refresh_btn.clicked.connect(self.rebuild)

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


# ---------------- main window ----------------

class OgarniaczWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Ogarniacz SM")
        self.resize(1100, 760)
        self.config = {}; self.config_mtime = None; self.always_on_top = False
        top = QHBoxLayout(); self.title_label = QLabel("Ogarniacz SM"); self.title_label.setStyleSheet("color:#ddd; font-weight:600;"); top.addWidget(self.title_label, 1)
        self.refresh_btn = QPushButton("Refresh"); self.refresh_btn.clicked.connect(self.load_config_and_rebuild)
        self.aot_btn = QPushButton("Always on Top: OFF"); self.aot_btn.setCheckable(True); self.aot_btn.toggled.connect(self.toggle_always_on_top)
        for b in (self.refresh_btn, self.aot_btn):
            b.setStyleSheet("QPushButton { padding:6px 10px; border-radius:8px; border:1px solid #3f3f3f; background:#242424; color:#f0f0f0;} QPushButton:hover{background:#2c2c2c} QPushButton:pressed{background:#1f1f1f}"); b.setFixedHeight(32)
        top.addWidget(self.refresh_btn, 0); top.addWidget(self.aot_btn, 0)
        self.stack = QStackedLayout()
        self.home_widget = QWidget(); self.flow_widget = QWidget(self.home_widget); self.flow_layout = FlowLayout(self.flow_widget, margin=12, hspacing=12, vspacing=12); self.flow_widget.setLayout(self.flow_layout)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setWidget(self.flow_widget)
        home_root = QVBoxLayout(self.home_widget); home_root.addWidget(scroll)

        self.scripts_widget = ScriptsGridWidget(folder="", parent=None)
        self.scripts_widget.back_btn.clicked.connect(lambda: self.stack.setCurrentIndex(0))
        self.stack.addWidget(self.home_widget)
        self.stack.addWidget(self.scripts_widget)

        # --- Fav Apps panel (dodajemy teraz, PRZED root layoutem) ---
        self.favapps_widget = FavAppsWidget(parent=None, launcher=lambda p: self.sync_and_run_app(p))
        self.favapps_widget.back_btn.clicked.connect(lambda: self.stack.setCurrentIndex(0))
        self.stack.addWidget(self.favapps_widget)

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
            self.title_label.setText(f"Ogarniacz SM — v{ver}")


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



    def check_config_update(self):
        try:
            mtime = os.path.getmtime(CONFIG_PATH)
            if self.config_mtime is None or mtime != self.config_mtime:
                self.load_config_and_rebuild()
        except Exception:
            pass

    def clear_flow(self):
        while self.flow_layout.count():
            item = self.flow_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None); w.deleteLater()

    def rebuild_home_tiles(self):
        self.clear_flow()
        tiles = self.config.get("tiles", [])
        for t in tiles:
            label = t.get("label", "Tile"); icon_path = t.get("tile_icon", "")
            w = TileWidget(label, icon_path, t, self.launch_payload, self.flow_widget)
            self.flow_layout.addWidget(w)
        if not any(t.get("type") == "internal" and t.get("action") == "open_maxscripts_panel" for t in tiles):
            default_payload = {"type": "internal", "action": "open_maxscripts_panel"}
            w = TileWidget("3ds Max Scripts (embedded)", "", default_payload, self.launch_payload, self.flow_widget)
            self.flow_layout.addWidget(w)
        self.flow_layout.invalidate(); self.flow_widget.adjustSize(); self.flow_widget.updateGeometry(); self.flow_widget.repaint()

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

        # 1) Wbudowany panel skryptów
        if act in ("", "open_maxscripts_panel", "open_scripts", "scripts", "scripts_panel"):
            if not self.scripts_widget.folder:
                self.scripts_widget.folder = r"Y:\\Instalki\\_SKRYPTY WIKT\\Still Motion Scripts"
            self.scripts_widget.refresh()
            self.stack.setCurrentIndex(1)
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



# ---------------- entry ----------------

def main():
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
        main()
    except Exception as e:
        import traceback
        msg = "Unhandled error:\n\n" + str(e) + "\n\n" + traceback.format_exc()
        try:
            ctypes.windll.user32.MessageBoxW(0, msg, "OgarniaczSM – crash", 0x10)
        except Exception:
            pass
        sys.exit(1)

