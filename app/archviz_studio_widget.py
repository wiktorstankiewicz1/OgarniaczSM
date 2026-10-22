"""Native OgarniaczSM panel hosting the shared Archviz Studio editor."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import urllib.request

from PySide6.QtCore import QUrl, QTimer
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel


def service_info(url):
    try:
        with urllib.request.urlopen(url.rstrip("/") + "/api/health", timeout=1) as response:
            return json.load(response)
    except Exception:
        return None


def service_available(url):
    from archviz_runtime import compatible_service
    return compatible_service(service_info(url))


class ArchvizStudioWidget(QWidget):
    def __init__(self, parent=None, url=None, registry=None):
        super().__init__(parent)
        self.url = url or os.environ.get("OGARNIACZ_ARCHVIZ_URL", "http://127.0.0.1:8890/")
        self.registry = registry or os.environ.get("OGARNIACZ_ARCHVIZ_REGISTRY")
        self._back_callback = None
        self._starting = False
        self._service_error = None
        self._loaded = False
        self._process = None
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        top = QHBoxLayout()
        self.back = QPushButton("← OgarniaczSM")
        self.back.clicked.connect(self._go_back)
        top.addWidget(self.back)
        top.addWidget(QLabel("Archviz Studio"))
        self.status = QLabel("Edytor wizualizacji")
        top.addWidget(self.status, 1)
        browser = QPushButton("Otwórz w przeglądarce")
        browser.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(self.url)))
        top.addWidget(browser)
        retry = QPushButton("Połącz ponownie")
        retry.clicked.connect(self._connect)
        top.addWidget(retry)
        root.addLayout(top)
        try:
            from PySide6.QtWebEngineWidgets import QWebEngineView
            self.view = QWebEngineView(self)
            self.view.loadFinished.connect(self._load_finished)
            root.addWidget(self.view, 1)
        except ImportError:
            self.view = None
            root.addWidget(QLabel("Brak Qt WebEngine. Ten sam edytor jest dostępny przyciskiem „Otwórz w przeglądarce”."))
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(300)
        self._poll_timer.timeout.connect(self._poll)

    def set_back_callback(self, callback):
        self._back_callback = callback

    def _go_back(self):
        if self._back_callback:
            self._back_callback()

    def showEvent(self, event):
        super().showEvent(event)
        if not self._loaded:
            self._connect()

    def _connect(self):
        if self._starting:
            return
        self._starting = True
        self._service_error = None
        self._loaded = False
        self.status.setText("Łączenie z lokalnym silnikiem…")
        self._poll_timer.start()

        def start():
            try:
                if not service_available(self.url):
                    live = service_info(self.url)
                    if live:
                        if live.get("service") != "archviz-studio" or not live.get("build"):
                            raise RuntimeError("Port zajmuje wcześniejszy silnik. Zakończ go przed otwarciem nowej wersji.")
                        # A previous build can hand off only when idle. Its jobs
                        # and project remain on disk; no process is force-killed.
                        base = self.url.rstrip("/")
                        with urllib.request.urlopen(base + "/api/bootstrap", timeout=3) as response:
                            token = json.load(response)["token"]
                        request = urllib.request.Request(base + "/api/shutdown", data=b"{}",
                            headers={"Content-Type": "application/json", "X-Studio-Token": token})
                        with urllib.request.urlopen(request, timeout=5):
                            pass
                        deadline = time.monotonic() + 10
                        while service_info(self.url) and time.monotonic() < deadline:
                            time.sleep(.2)
                        if service_info(self.url):
                            raise RuntimeError("Poprzedni silnik nie zakończył pracy.")
                    from urllib.parse import urlparse
                    parsed = urlparse(self.url)
                    if parsed.hostname not in {"127.0.0.1", "localhost"}:
                        raise ValueError("Automatyczny start działa tylko dla lokalnego silnika.")
                    app = Path(__file__).resolve().parent
                    command = [sys.executable, str(app / "archviz_server.py"), "--port", str(parsed.port or 8890)]
                    # In a frozen application sys.executable is the Ogarniacz exe,
                    # so use its explicit server command instead of a .py argument.
                    if getattr(sys, "frozen", False):
                        command = [sys.executable, "--archviz-server", "--port", str(parsed.port or 8890)]
                    registry = self.registry
                    if registry:
                        command += ["--registry", registry]
                    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
                    self._process = subprocess.Popen(command, cwd=app, stdout=subprocess.DEVNULL,
                                                     stderr=subprocess.DEVNULL, creationflags=flags,
                                                     close_fds=True)
                    deadline = time.monotonic() + 20
                    while time.monotonic() < deadline:
                        if service_available(self.url):
                            break
                        if self._process.poll() is not None:
                            raise RuntimeError("Silnik zakończył pracę. Uruchom archviz_cli.py serve, aby zobaczyć diagnostykę.")
                        time.sleep(.2)
                    else:
                        raise RuntimeError("Lokalny silnik nie odpowiedział w ciągu 20 sekund.")
            except Exception as error:
                self._service_error = str(error)
            finally:
                self._starting = False

        threading.Thread(target=start, daemon=True, name="archviz-start").start()

    def _poll(self):
        if self._starting:
            return
        self._poll_timer.stop()
        if self._service_error:
            self.status.setText(self._service_error)
            return
        if self.view:
            self.view.setUrl(QUrl(self.url))
        else:
            self.status.setText("Silnik gotowy — otwórz edytor w przeglądarce.")

    def _load_finished(self, ok):
        self._loaded = bool(ok)
        self.status.setText("Lokalny projekt • zadania działają niezależnie od okna" if ok else "Nie udało się załadować edytora — sprawdź połączenie.")
