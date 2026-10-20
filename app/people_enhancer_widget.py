"""
people_enhancer_widget.py
PySide6 panel for OgarniaczSM - People Enhancement feature.
Self-contained: includes its own back button, no injection needed from main.py.
"""
import threading, time, os, subprocess
from pathlib import Path
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QScrollArea, QFileDialog, QProgressBar, QFrame, QSizePolicy,
)
from PySide6.QtCore import Qt, QTimer, Signal, QObject
from PySide6.QtGui import QPixmap

try:
    import people_enhancer_pipeline as pipeline
    PIPELINE_OK = True
    PIPELINE_ERR = ""
except ImportError as e:
    PIPELINE_OK = False
    PIPELINE_ERR = str(e)

BTN_STYLE = """QPushButton {
    padding:4px 8px; border-radius:6px; border:1px solid #3f3f3f;
    background:#2a2a2a; color:#f0f0f0; font-size:12px;}
QPushButton:hover{background:#333}
QPushButton:disabled{color:#555; background:#1e1e1e;}"""

PRIMARY_BTN = """QPushButton {
    padding:6px 16px; border-radius:6px; border:1px solid #1a5a9a;
    background:#1a4a7a; color:#f0f0f0; font-size:12px; font-weight:600;}
QPushButton:hover{background:#215a9a}
QPushButton:disabled{color:#555; background:#1e1e1e; border-color:#333;}"""


class WorkerSignals(QObject):
    stage_update = Signal(str, str, int)  # (image_path, stage_name, pct)
    job_done     = Signal(str, str)       # (image_path, output_path)
    job_error    = Signal(str, str)       # (image_path, error_msg)
    status_ready = Signal(dict)           # comfyui status dict


class ImageJobCard(QFrame):
    """Progress card for one image."""
    STAGES = {
        "preparing":  "Preparing…",
        "detecting":  "Detecting people…",
        "pass1":      "Pass 1: Structure…",
        "pass2":      "Pass 2: Texture…",
        "face_fix":   "Face composite…",
        "saving":     "Saving…",
        "done":       "✓ Done",
    }

    def __init__(self, image_path: str, on_action, parent=None):
        super().__init__(parent)
        self.image_path  = image_path
        self.output_path = ""
        self._on_action  = on_action
        self.setObjectName("jobcard")
        self.setStyleSheet(
            "QFrame#jobcard{border-radius:8px;border:0.5px solid #3a3a3a;background:#222;}")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFixedHeight(82)

        row = QHBoxLayout(self)
        row.setContentsMargins(8, 6, 8, 6)
        row.setSpacing(10)

        # Thumbnail
        self.thumb = QLabel()
        self.thumb.setFixedSize(60, 60)
        self.thumb.setAlignment(Qt.AlignCenter)
        self.thumb.setStyleSheet("background:#111;border-radius:4px;")
        try:
            pix = QPixmap(image_path)
            if not pix.isNull():
                self.thumb.setPixmap(
                    pix.scaled(60, 60, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        except Exception:
            self.thumb.setText("?")
        row.addWidget(self.thumb)

        # Info
        info = QVBoxLayout()
        info.setSpacing(3)
        name = QLabel(Path(image_path).name)
        name.setStyleSheet("color:#e0e0e0;font-weight:600;font-size:12px;")
        self.stage_lbl = QLabel("Waiting…")
        self.stage_lbl.setStyleSheet("color:#888;font-size:11px;")
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setValue(0)
        self.bar.setFixedHeight(5)
        self.bar.setTextVisible(False)
        self.bar.setStyleSheet(
            "QProgressBar{border-radius:2px;background:#333;}"
            "QProgressBar::chunk{border-radius:2px;background:#4a9eff;}")
        info.addWidget(name)
        info.addWidget(self.stage_lbl)
        info.addWidget(self.bar)
        row.addLayout(info, 1)

        self.btn = QPushButton("✕")
        self.btn.setFixedSize(26, 26)
        self.btn.setStyleSheet(BTN_STYLE)
        self.btn.setToolTip("Remove")
        self.btn.clicked.connect(lambda: self._on_action(self.image_path))
        row.addWidget(self.btn, alignment=Qt.AlignVCenter)

    def set_stage(self, stage: str, pct: int):
        label = self.STAGES.get(stage, stage)
        self.stage_lbl.setText(label)
        self.bar.setValue(pct)
        if stage == "done":
            self.bar.setStyleSheet(
                "QProgressBar{border-radius:2px;background:#333;}"
                "QProgressBar::chunk{border-radius:2px;background:#3cb371;}")
            self.stage_lbl.setStyleSheet("color:#3cb371;font-size:11px;")
            self.btn.setText("📂")
            self.btn.setToolTip("Open output folder")
        elif stage == "error":
            self.bar.setStyleSheet(
                "QProgressBar{border-radius:2px;background:#333;}"
                "QProgressBar::chunk{border-radius:2px;background:#e05050;}")

    def set_error(self, msg: str):
        short = msg[:80] + ("…" if len(msg) > 80 else "")
        self.stage_lbl.setText("✗ " + short)
        self.stage_lbl.setStyleSheet("color:#e05050;font-size:11px;")
        self.stage_lbl.setToolTip(msg)  # full message on hover
        self.set_stage("error", 100)
        self.btn.setText("↺")
        self.btn.setToolTip("Retry")


class PeopleEnhancerWidget(QWidget):
    """
    Main panel. Back button is self-contained.
    Call set_back_callback(fn) after construction to wire up navigation.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self._back_cb  = None
        self._jobs     = {}    # path -> ImageJobCard
        self._queue    = []
        self._running  = False
        self._signals  = WorkerSignals()
        self._signals.stage_update.connect(self._on_stage)
        self._signals.job_done.connect(self._on_done)
        self._signals.job_error.connect(self._on_error)
        self._signals.status_ready.connect(self._on_status)
        self._build_ui()
        self._refresh_status()

    # ── public API ──────────────────────────────────────────────
    def set_back_callback(self, fn):
        self._back_cb = fn
        self._back_btn.clicked.connect(fn)

    # ── UI construction ─────────────────────────────────────────
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 12)
        root.setSpacing(8)

        # Top bar: back + title + status
        top = QHBoxLayout()
        self._back_btn = QPushButton("← Back")
        self._back_btn.setFixedHeight(26)
        self._back_btn.setStyleSheet(BTN_STYLE)
        top.addWidget(self._back_btn)

        title = QLabel("People Enhancement")
        title.setStyleSheet("color:#e0e0e0;font-size:15px;font-weight:700;")
        top.addWidget(title)
        top.addStretch(1)

        self._dot = QLabel("●")
        self._dot.setStyleSheet("color:#888;font-size:13px;")
        self._status_lbl = QLabel("Checking ComfyUI…")
        self._status_lbl.setStyleSheet("color:#888;font-size:11px;")
        top.addWidget(self._dot)
        top.addWidget(self._status_lbl)
        root.addLayout(top)

        # Toolbar
        bar = QHBoxLayout()
        self._add_btn = QPushButton("+ Add Images")
        self._add_btn.setStyleSheet(BTN_STYLE)
        self._add_btn.clicked.connect(self._pick_images)
        self._run_btn = QPushButton("▶  Enhance All")
        self._run_btn.setStyleSheet(PRIMARY_BTN)
        self._run_btn.setEnabled(False)
        self._run_btn.clicked.connect(self._start_all)
        self._clear_btn = QPushButton("Clear")
        self._clear_btn.setStyleSheet(BTN_STYLE)
        self._clear_btn.clicked.connect(self._clear_all)
        bar.addWidget(self._add_btn)
        bar.addWidget(self._run_btn)
        bar.addStretch(1)
        bar.addWidget(self._clear_btn)
        root.addLayout(bar)

        self._eta_lbl = QLabel("")
        self._eta_lbl.setStyleSheet("color:#666;font-size:11px;")
        root.addWidget(self._eta_lbl)

        # Pipeline warning if import failed
        if not PIPELINE_OK:
            warn = QLabel("⚠ Pipeline unavailable: " + PIPELINE_ERR)
            warn.setStyleSheet("color:#e08050;font-size:11px;")
            warn.setWordWrap(True)
            root.addWidget(warn)

        # Cards scroll area
        self._cards_w = QWidget()
        self._cards_vbox = QVBoxLayout(self._cards_w)
        self._cards_vbox.setContentsMargins(0, 0, 0, 0)
        self._cards_vbox.setSpacing(6)
        self._cards_vbox.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self._cards_w)
        scroll.setStyleSheet("QScrollArea{border:none;}")
        root.addWidget(scroll, 1)

        # Status poll timer
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh_status)
        self._timer.start(6000)

    # ── status polling ───────────────────────────────────────────
    def _refresh_status(self):
        def worker():
            if not PIPELINE_OK:
                self._signals.status_ready.emit(
                    {"ok": False, "error": "pipeline import failed: " + PIPELINE_ERR})
                return
            self._signals.status_ready.emit(pipeline.check_comfyui())
        threading.Thread(target=worker, daemon=True).start()

    def _on_status(self, s: dict):
        if s.get("ok"):
            self._dot.setStyleSheet("color:#3cb371;font-size:13px;")
            self._status_lbl.setText(
                "ComfyUI ready  %.1fGB VRAM free" % s.get("vram_free_gb", 0))
        else:
            self._dot.setStyleSheet("color:#e05050;font-size:13px;")
            self._status_lbl.setText("ComfyUI offline")
        self._update_run_btn()

    # ── image picking ─────────────────────────────────────────────
    def _pick_images(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Select renders", "Y:/",
            "Images (*.png *.jpg *.jpeg *.tif *.tiff)")
        for p in paths:
            if p and p not in self._jobs:
                self._add_card(p)
        self._update_run_btn()
        self._update_eta()

    def _add_card(self, path: str):
        card = ImageJobCard(path, self._card_action, parent=self._cards_w)
        self._cards_vbox.insertWidget(self._cards_vbox.count() - 1, card)
        self._jobs[path] = card
        self._queue.append(path)

    def _card_action(self, path: str):
        card = self._jobs.get(path)
        if not card:
            return
        if card.output_path:
            folder = str(Path(card.output_path).parent)
            subprocess.Popen(["explorer", folder])
        else:
            self._remove_card(path)

    def _remove_card(self, path: str):
        card = self._jobs.pop(path, None)
        if card:
            card.setParent(None)
            card.deleteLater()
        if path in self._queue:
            self._queue.remove(path)
        self._update_run_btn()
        self._update_eta()

    def _clear_all(self):
        for path in list(self._jobs):
            card = self._jobs.pop(path)
            card.setParent(None)
            card.deleteLater()
        self._queue.clear()
        self._update_run_btn()
        self._eta_lbl.setText("")

    # ── queue management ──────────────────────────────────────────
    def _update_run_btn(self):
        ready = "ready" in self._status_lbl.text()
        self._run_btn.setEnabled(
            bool(self._queue) and ready and not self._running and PIPELINE_OK)

    def _update_eta(self):
        if not self._queue:
            self._eta_lbl.setText("")
            return
        total = sum(pipeline.estimate_time(1920, 1080) for _ in self._queue) if PIPELINE_OK else 0
        self._eta_lbl.setText("~%dm %02ds estimated for %d image(s)" % (
            total // 60, total % 60, len(self._queue)))

    def _start_all(self):
        if self._running or not self._queue:
            return
        self._running = True
        self._run_btn.setEnabled(False)
        self._add_btn.setEnabled(False)
        threading.Thread(target=self._worker_thread, daemon=True).start()

    def _worker_thread(self):
        pending = [p for p in self._queue
                   if self._jobs.get(p) and not self._jobs[p].output_path]
        for path in pending:
            out = str(Path(path).with_stem(Path(path).stem + "_enhanced"))
            try:
                def cb(stage, pct, _p=path):
                    self._signals.stage_update.emit(_p, stage, pct)
                pipeline.enhance_image(path, out, progress_cb=cb)
                self._jobs[path].output_path = out
                self._signals.job_done.emit(path, out)
            except Exception as e:
                self._signals.job_error.emit(path, str(e))
        self._running = False
        self._signals.job_done.emit("__all_done__", "")

    # ── signal handlers ───────────────────────────────────────────
    def _on_stage(self, path: str, stage: str, pct: int):
        card = self._jobs.get(path)
        if card:
            card.set_stage(stage, pct)

    def _on_done(self, path: str, out: str):
        if path == "__all_done__":
            self._running = False
            self._add_btn.setEnabled(True)
            self._update_run_btn()
            return
        card = self._jobs.get(path)
        if card:
            card.set_stage("done", 100)
            card.output_path = out

    def _on_error(self, path: str, msg: str):
        card = self._jobs.get(path)
        if card:
            card.set_error(msg)
