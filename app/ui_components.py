from pathlib import Path
from PySide6.QtCore import Qt, QSize, QPoint, QRect, QMimeData, QUrl
from PySide6.QtGui import QPixmap, QMouseEvent, QDrag, QPainter, QFont
from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QLabel, QSizePolicy, QLayout, QDialog, QTextEdit, QMessageBox
)

from utils import resolve_rel_to_config

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
        self.invalidate()

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index):
        if 0 <= index < len(self._items):
            self.invalidate()
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
    def __init__(self, label, icon_path, payload, launcher, parent=None, wide_label: bool = False):
        super().__init__(parent)
        self.payload = payload
        self.launcher = launcher
        self.setObjectName("tile")
        # Compact sizing - barely larger than content
        self.setMinimumSize(QSize(110, 120))
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.setStyleSheet(
            """
            QFrame#tile { border-radius: 6px; border: 0.5px solid #3f3f3f; background: #242424; }
            QFrame#tile:hover { background: #2c2c2c; }
            QLabel#tilelabel { color:#f0f0f0; font-weight:600; padding: 2px 4px; }
            """
        )
        v = QVBoxLayout(self)
        # Minimal padding - barely larger than text
        v.setContentsMargins(4, 4, 4, 4)
        v.setSpacing(2)
        v.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
        self.icon_label = QLabel(self)
        self.icon_label.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
        # Consistent 72x72 icon size with other tiles
        self.icon_label.setFixedSize(72, 72)
        self.icon_label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.set_icon(icon_path)
        self.text_label = QLabel(label, self)
        self.text_label.setObjectName("tilelabel")
        self.text_label.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
        self.text_label.setWordWrap(False)
        # Size to fit content - no fixed widths for compact frames
        self.text_label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        # Remove any internal margins on the label itself
        self.text_label.setContentsMargins(0, 0, 0, 0)
        v.addWidget(self.icon_label, alignment=Qt.AlignHCenter)
        v.addWidget(self.text_label, alignment=Qt.AlignHCenter)

    def set_icon(self, icon_path):
        if icon_path:
            icon_path = resolve_rel_to_config(icon_path)
        pix = None
        if icon_path and Path(icon_path).exists():
            pix = QPixmap(str(icon_path))
        if not pix or pix.isNull():
            pix = QPixmap(72, 72); pix.fill(Qt.transparent)
        scaled = pix.scaled(72, 72, Qt.KeepAspectRatio, Qt.SmoothTransformation)
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
        # Compact sizing to match home tiles
        self.setMinimumSize(QSize(110, 120))
        self.setMaximumWidth(160)
        self.setCursor(Qt.OpenHandCursor)
        self.setStyleSheet(
            """
            QFrame#scripttile { border-radius: 6px; border: 0.5px solid #3f3f3f; background: #242424; }
            QFrame#scripttile:hover { background: #2c2c2c; }
            QLabel#name { color:#f0f0f0; font-weight:500; padding: 2px 4px; }
            """
        )
        v = QVBoxLayout(self)
        # Minimal padding to match home tiles
        v.setContentsMargins(4, 4, 4, 4)
        v.setSpacing(2)
        v.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
        icon_lbl = QLabel(self)
        icon_lbl.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
        # Smaller icon to match compact style
        icon_lbl.setFixedSize(72, 72)
        icon_lbl.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        icon = self._load_icon_for_script(script_path)
        icon_lbl.setPixmap(icon)
        name_lbl = QLabel(script_path.stem, self)
        name_lbl.setObjectName("name")
        name_lbl.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
        name_lbl.setWordWrap(False)
        name_lbl.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        name_lbl.setContentsMargins(0, 0, 0, 0)
        v.addWidget(icon_lbl, alignment=Qt.AlignHCenter)
        v.addWidget(name_lbl, alignment=Qt.AlignHCenter)

        # Load description and set tooltip
        self.description = ""
        desc_path = self.script_path.with_suffix(".txt")
        if desc_path.exists():
            try:
                self.description = desc_path.read_text(encoding="utf-8").strip()
            except Exception:
                self.description = "Error reading description."

        if self.description:
            snippet = self.description.split('\n')[0]
            if len(snippet) > 100:
                snippet = snippet[:100] + "..."
            tooltip_text = f"{snippet}\n\nPPM - więcej"
            self.setToolTip(tooltip_text)

    def contextMenuEvent(self, event):
        if self.description:
            dlg = QMessageBox(self)
            dlg.setWindowTitle(f"Description: {self.script_path.stem}")
            dlg.setText(self.description)
            dlg.setIcon(QMessageBox.Information)
            dlg.exec()
        else:
            super().contextMenuEvent(event)

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
        p = QPainter(pm); p.setPen(Qt.white); p.setFont(QFont("Segoe UI", 16, QFont.Weight.DemiBold))
        p.drawText(pm.rect(), Qt.AlignCenter, script_path.stem[:3]); p.end()
        return pm

# ---------------- fav apps panel (embedded) ----------------

class FavAppTile(QFrame):
    ICON_SIZE = QSize(72, 72)

    def __init__(self, label: str, path: str, icon_path: str | None, launcher, parent=None):
        super().__init__(parent)
        self.label = label
        self.path = path
        self.launcher = launcher

        self.setObjectName("scripttile")
        # Compact sizing to match home tiles
        self.setMinimumSize(QSize(110, 120))
        self.setMaximumWidth(160)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet(
            """
            QFrame#scripttile { border-radius: 6px; border: 0.5px solid #3f3f3f; background: #242424; }
            QFrame#scripttile:hover { background: #2c2c2c; }
            QLabel#name { color:#f0f0f0; font-weight:500; padding: 2px 4px; }
            """
        )
        v = QVBoxLayout(self)
        # Minimal padding to match home tiles
        v.setContentsMargins(4, 4, 4, 4)
        v.setSpacing(2)
        v.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)

        icon_lbl = QLabel(self)
        icon_lbl.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
        icon_lbl.setFixedSize(self.ICON_SIZE)
        icon_lbl.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        icon_lbl.setPixmap(self._load_icon(icon_path, label))

        name_lbl = QLabel(label, self)
        name_lbl.setObjectName("name")
        name_lbl.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
        name_lbl.setWordWrap(False)
        name_lbl.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        name_lbl.setContentsMargins(0, 0, 0, 0)

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
            painter = QPainter(pm)
            painter.setPen(Qt.white)
            painter.setFont(QFont("Segoe UI", 16, QFont.Weight.DemiBold))
            painter.drawText(pm.rect(), Qt.AlignCenter, (text or "APP")[:3])
            painter.end()
        return pm.scaled(self.ICON_SIZE, Qt.KeepAspectRatio, Qt.SmoothTransformation)