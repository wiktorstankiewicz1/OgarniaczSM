"""Generic OgarniaczSM panel for image workflows processed on Zeus."""

import os
import subprocess
import threading
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

import zeus_workflows_api as api


BUTTON_STYLE = """QPushButton {
    padding:4px 9px; border-radius:6px; border:1px solid #3f3f3f;
    background:#2a2a2a; color:#f0f0f0; font-size:12px;}
QPushButton:hover{background:#333}
QPushButton:disabled{color:#666;background:#1e1e1e;}"""

PRIMARY_STYLE = """QPushButton {
    padding:6px 16px; border-radius:6px; border:1px solid #657f13;
    background:#526812; color:#f6ffd9; font-size:12px; font-weight:600;}
QPushButton:hover{background:#647f15}
QPushButton:disabled{color:#666;background:#1e1e1e;border-color:#333;}"""


def _eta_text(seconds) -> str:
    if seconds is None:
        return "Estimating time"
    seconds = int(seconds)
    if seconds <= 1:
        return "Almost done"
    if seconds < 60:
        return "About %ds left" % seconds
    return "About %d min left" % ((seconds + 59) // 60)


class WorkflowSignals(QObject):
    catalog_ready = Signal(dict)
    jobs_ready = Signal(list)
    submitted = Signal(str, dict)
    local_stage = Signal(str, str, int)
    result_saved = Signal(str, str)
    error = Signal(str, str)
    upload_finished = Signal()


class ZeusJobCard(QFrame):
    def __init__(self, key: str, file_name: str, source_path: str = "", parent=None):
        super().__init__(parent)
        self.key = key
        self.job_id = ""
        self.source_path = source_path
        self.output_path = ""
        self.job = {}
        self.setFrameShape(QFrame.StyledPanel)
        self.setStyleSheet("QFrame{background:#202020;border:1px solid #353535;border-radius:8px;}")

        row = QHBoxLayout(self)
        row.setContentsMargins(8, 7, 8, 7)
        row.setSpacing(9)
        self.preview = QLabel()
        self.preview.setFixedSize(64, 52)
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setStyleSheet("background:#151515;border-radius:5px;color:#777;font-weight:700;")
        if source_path:
            pixmap = QPixmap(source_path)
            if not pixmap.isNull():
                self.preview.setPixmap(pixmap.scaled(64, 52, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            else:
                self.preview.setText("AI")
        else:
            self.preview.setText("AI")
        row.addWidget(self.preview)

        details = QVBoxLayout()
        details.setSpacing(3)
        name = QLabel(file_name)
        name.setStyleSheet("color:#e8e8e8;font-size:12px;font-weight:600;")
        self.stage = QLabel("Ready to send")
        self.stage.setStyleSheet("color:#888;font-size:11px;")
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(5)
        self.progress.setStyleSheet(
            "QProgressBar{border:0;border-radius:2px;background:#333;}"
            "QProgressBar::chunk{border-radius:2px;background:#d9ff52;}"
        )
        self.eta = QLabel("")
        self.eta.setStyleSheet("color:#686868;font-size:10px;")
        details.addWidget(name)
        details.addWidget(self.stage)
        details.addWidget(self.progress)
        details.addWidget(self.eta)
        row.addLayout(details, 1)

        self.action = QPushButton("Remove")
        self.action.setStyleSheet(BUTTON_STYLE)
        row.addWidget(self.action)

    def update_job(self, job: dict):
        self.job = job
        self.job_id = job.get("id", self.job_id)
        status = job.get("status", "")
        self.stage.setText(job.get("stage") or status.title())
        self.progress.setValue(int(float(job.get("progress") or 0)))
        if status in ("queued", "uploading", "running"):
            self.eta.setText(_eta_text(job.get("etaSeconds")))
            self.action.setText("Working")
            self.action.setEnabled(False)
        elif status == "completed":
            self.eta.setText("Result ready")
            self.stage.setStyleSheet("color:#76e7a5;font-size:11px;")
            self.action.setText("Open" if self.output_path else "Save as")
            self.action.setEnabled(True)
        elif status == "failed":
            self.eta.setText(job.get("message") or "Workflow failed")
            self.eta.setToolTip(job.get("message") or "")
            self.stage.setStyleSheet("color:#ff777d;font-size:11px;")
            self.action.setText("Remove")
            self.action.setEnabled(True)

    def set_local_stage(self, label: str, percent: int):
        self.stage.setText(label)
        self.progress.setValue(percent)
        self.action.setEnabled(False)

    def set_saved(self, output_path: str):
        self.output_path = output_path
        self.stage.setText("Saved next to source")
        self.eta.setText(Path(output_path).name)
        self.action.setText("Open")
        self.action.setEnabled(True)


class ZeusWorkflowsWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._back_callback = None
        self._signals = WorkflowSignals()
        self._signals.catalog_ready.connect(self._on_catalog)
        self._signals.jobs_ready.connect(self._on_jobs)
        self._signals.submitted.connect(self._on_submitted)
        self._signals.local_stage.connect(self._on_local_stage)
        self._signals.result_saved.connect(self._on_result_saved)
        self._signals.error.connect(self._on_error)
        self._signals.upload_finished.connect(self._on_upload_finished)
        self._catalog = []
        self._cards = {}
        self._source_by_job = {}
        self._downloading = set()
        self._uploading = False
        self._refreshing = False
        self._build_ui()
        self._refresh()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh)
        self._timer.start(2500)

    def set_back_callback(self, callback):
        self._back_callback = callback
        self._back.clicked.connect(callback)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 12)
        root.setSpacing(9)

        top = QHBoxLayout()
        self._back = QPushButton("← Back")
        self._back.setStyleSheet(BUTTON_STYLE)
        top.addWidget(self._back)
        title = QLabel("Zeus AI Workflows")
        title.setStyleSheet("color:#e8e8e8;font-size:15px;font-weight:700;")
        top.addWidget(title)
        top.addStretch(1)
        self._dot = QLabel("●")
        self._dot.setStyleSheet("color:#777;font-size:12px;")
        self._status = QLabel("Connecting to Zeus…")
        self._status.setStyleSheet("color:#888;font-size:11px;")
        top.addWidget(self._dot)
        top.addWidget(self._status)
        root.addLayout(top)

        controls = QHBoxLayout()
        self._workflow = QComboBox()
        self._workflow.setMinimumWidth(180)
        self._workflow.setStyleSheet(
            "QComboBox{padding:5px 9px;border:1px solid #3f3f3f;border-radius:6px;"
            "background:#242424;color:#eee;}"
        )
        self._add = QPushButton("+ Add images")
        self._add.setStyleSheet(BUTTON_STYLE)
        self._add.clicked.connect(self._pick_images)
        self._send = QPushButton("Send to Zeus")
        self._send.setStyleSheet(PRIMARY_STYLE)
        self._send.setEnabled(False)
        self._send.clicked.connect(self._send_pending)
        controls.addWidget(self._workflow)
        controls.addWidget(self._add)
        controls.addWidget(self._send)
        controls.addStretch(1)
        root.addLayout(controls)

        hint = QLabel("Choose a workflow, send renders to Zeus, and results will return next to the source images.")
        hint.setStyleSheet("color:#686868;font-size:11px;")
        hint.setWordWrap(True)
        root.addWidget(hint)

        self._cards_widget = QWidget()
        self._cards_layout = QVBoxLayout(self._cards_widget)
        self._cards_layout.setContentsMargins(0, 0, 0, 0)
        self._cards_layout.setSpacing(6)
        self._cards_layout.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self._cards_widget)
        scroll.setStyleSheet("QScrollArea{border:none;}")
        root.addWidget(scroll, 1)

    def _selected_workflow_id(self) -> str:
        return str(self._workflow.currentData() or "")

    def _refresh(self):
        if self._refreshing:
            return
        self._refreshing = True

        def worker():
            try:
                catalog = api.get_catalog()
                jobs = api.get_jobs()
                self._signals.catalog_ready.emit(catalog)
                self._signals.jobs_ready.emit(jobs)
            except Exception as error:
                self._signals.error.emit("connection", str(error))
            finally:
                self._refreshing = False

        threading.Thread(target=worker, daemon=True).start()

    def _on_catalog(self, catalog: dict):
        workflows = catalog.get("workflows", [])
        current = self._selected_workflow_id()
        if [item.get("id") for item in workflows] != [item.get("id") for item in self._catalog]:
            self._catalog = workflows
            self._workflow.clear()
            for workflow in workflows:
                self._workflow.addItem(workflow.get("name", workflow.get("id", "Workflow")), workflow.get("id"))
            if current:
                index = self._workflow.findData(current)
                if index >= 0:
                    self._workflow.setCurrentIndex(index)
        online = bool(catalog.get("comfyOnline"))
        self._dot.setStyleSheet("color:%s;font-size:12px;" % ("#76e7a5" if online else "#d9ff52"))
        self._status.setText("Zeus ready" if online else "Zeus is starting ComfyUI…")
        self._update_send_button()

    def _pick_images(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Choose renders",
            "Y:/",
            "Images (*.png *.jpg *.jpeg *.webp)",
        )
        for path in paths:
            key = "local:" + path
            if key in self._cards:
                continue
            card = ZeusJobCard(key, Path(path).name, source_path=path, parent=self._cards_widget)
            card.action.clicked.connect(lambda _checked=False, item_key=key: self._remove_card(item_key))
            self._cards[key] = card
            self._cards_layout.insertWidget(0, card)
        self._update_send_button()

    def _pending_sources(self) -> list[str]:
        return [card.source_path for key, card in self._cards.items() if key.startswith("local:")]

    def _update_send_button(self):
        ready = self._status.text() == "Zeus ready"
        self._send.setEnabled(bool(self._pending_sources()) and ready and not self._uploading and bool(self._selected_workflow_id()))

    def _send_pending(self):
        sources = self._pending_sources()
        workflow_id = self._selected_workflow_id()
        if not sources or not workflow_id or self._uploading:
            return
        self._uploading = True
        self._add.setEnabled(False)
        self._send.setEnabled(False)

        def worker():
            for source in sources:
                try:
                    self._signals.local_stage.emit(source, "Sending to Zeus…", 2)
                    job = api.submit_image(workflow_id, source)
                    self._signals.submitted.emit(source, job)
                except Exception as error:
                    self._signals.error.emit(source, str(error))
            self._signals.upload_finished.emit()

        threading.Thread(target=worker, daemon=True).start()

    def _on_local_stage(self, source: str, label: str, percent: int):
        card = self._cards.get("local:" + source)
        if card:
            card.set_local_stage(label, percent)

    def _on_submitted(self, source: str, job: dict):
        old_key = "local:" + source
        card = self._cards.pop(old_key, None)
        if not card:
            card = ZeusJobCard(job["id"], job.get("fileName", Path(source).name), source_path=source, parent=self._cards_widget)
            self._cards_layout.insertWidget(0, card)
        card.key = job["id"]
        card.job_id = job["id"]
        try:
            card.action.clicked.disconnect()
        except RuntimeError:
            pass
        card.action.clicked.connect(lambda _checked=False, item_key=job["id"]: self._card_action(item_key))
        self._cards[job["id"]] = card
        self._source_by_job[job["id"]] = source
        card.update_job(job)

    def _on_upload_finished(self):
        self._uploading = False
        self._add.setEnabled(True)
        self._update_send_button()
        self._refresh()

    def _on_jobs(self, jobs: list):
        for job in reversed(jobs):
            job_id = job.get("id")
            if not job_id:
                continue
            card = self._cards.get(job_id)
            if not card:
                card = ZeusJobCard(job_id, job.get("fileName", "Image"), parent=self._cards_widget)
                card.job_id = job_id
                card.action.clicked.connect(lambda _checked=False, item_key=job_id: self._card_action(item_key))
                self._cards[job_id] = card
                self._cards_layout.insertWidget(0, card)
            card.update_job(job)
            if job.get("status") == "completed" and job_id in self._source_by_job and not card.output_path:
                self._auto_download(job_id, job)

    def _auto_download(self, job_id: str, job: dict):
        if job_id in self._downloading:
            return
        source = Path(self._source_by_job[job_id])
        suffix = str(job.get("workflowId") or "zeus_result").replace("-", "_")
        destination = source.with_name(source.stem + "_" + suffix + ".png")
        self._download(job_id, str(destination))

    def _download(self, job_id: str, destination: str):
        if job_id in self._downloading:
            return
        self._downloading.add(job_id)

        def worker():
            try:
                saved = api.download_result(job_id, destination)
                self._signals.result_saved.emit(job_id, saved)
            except Exception as error:
                self._signals.error.emit(job_id, str(error))
            finally:
                self._downloading.discard(job_id)

        threading.Thread(target=worker, daemon=True).start()

    def _on_result_saved(self, job_id: str, output_path: str):
        card = self._cards.get(job_id)
        if card:
            card.set_saved(output_path)

    def _card_action(self, key: str):
        card = self._cards.get(key)
        if not card:
            return
        if card.output_path:
            subprocess.Popen(["explorer", "/select,", os.path.normpath(card.output_path)])
            return
        if card.job.get("status") == "completed":
            suggested = card.job.get("fileName", "zeus_result.png")
            suggested = str(Path(suggested).with_suffix(".png"))
            destination, _ = QFileDialog.getSaveFileName(self, "Save Zeus result", suggested, "PNG image (*.png)")
            if destination:
                self._download(card.job_id, destination)
            return
        self._remove_card(key)

    def _remove_card(self, key: str):
        card = self._cards.pop(key, None)
        if card:
            card.setParent(None)
            card.deleteLater()
        self._update_send_button()

    def _on_error(self, context: str, message: str):
        if context == "connection":
            self._dot.setStyleSheet("color:#ff777d;font-size:12px;")
            self._status.setText("Zeus unavailable")
            self._status.setToolTip(message)
        else:
            card = self._cards.get(context) or self._cards.get("local:" + context)
            if card:
                card.stage.setText("Failed")
                card.stage.setStyleSheet("color:#ff777d;font-size:11px;")
                card.eta.setText(message)
                card.eta.setToolTip(message)
                card.action.setText("Remove")
                card.action.setEnabled(True)
        self._update_send_button()
