"""Loopback Archviz Studio service, shared by desktop, browser and CLI."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import threading
import time
from urllib.parse import unquote, urlparse, parse_qs

APP_DIR = Path(__file__).resolve().parent
DEFAULT_PORT = 8890


def default_registry():
    return Path(os.environ.get("LOCALAPPDATA", Path.home())) / "OgarniaczSM" / "ArchvizStudio" / "registry.json"


def atomic_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + secrets.token_hex(6) + ".tmp")
    try:
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


class StudioService:
    def __init__(self, registry=None):
        self.registry = Path(registry or default_registry())
        self.lock = threading.RLock()
        self.token = secrets.token_urlsafe(32)
        self.projects = {}
        self.current = None
        self.executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="archviz")
        self.futures = {}
        self.recent = []
        self.startup_error = None
        if self.registry.exists():
            try:
                saved = json.loads(self.registry.read_text(encoding="utf-8-sig"))
                self.recent = saved.get("projects", [])
                active = saved.get("active_work_dir")
                if active and (Path(active) / "project.json").is_file():
                    self.open_project(active)
            except Exception as error:
                self.startup_error = "Nie udało się przywrócić projektu: " + str(error)

    def _core(self):
        from archviz_core import StudioProject
        return StudioProject

    def _remember(self, project):
        data = project.snapshot()
        work = str(Path(data["work_dir"]).resolve())
        entry = {"work_dir": work, "name": data["name"], "id": data["id"]}
        self.recent = [entry] + [p for p in self.recent if p.get("work_dir") != work]
        self.recent = self.recent[:30]
        atomic_json(self.registry, {"schema_version": 1, "active_work_dir": work, "projects": self.recent})

    def create_project(self, data):
        with self.lock:
            project = self._core().create(data["name"], data["work_dir"], data.get("input_dirs", []), data["output_dir"])
            if data.get("settings"):
                project.update_settings(**data["settings"])
            self.current = project
            self.projects[str(Path(data["work_dir"]).resolve())] = project
            self._remember(project)
            return project.snapshot()

    def open_project(self, work_dir):
        with self.lock:
            path = Path(work_dir)
            if path.name == "project.json":
                path = path.parent
            key = str(path.resolve())
            if key not in self.projects:
                self.projects[key] = self._core()(key)
                recover = getattr(self.projects[key], "recover_jobs", None)
                if recover:
                    recover()
            self.current = self.projects[key]
            self._remember(self.current)
            self.startup_error = None
            return self.current.snapshot()

    def require_project(self):
        with self.lock:
            if self.current is None:
                raise ValueError("Najpierw utwórz lub otwórz projekt.")
            return self.current

    def state(self):
        from archviz_core import provider_available
        with self.lock:
            return {"project": self.current.snapshot() if self.current else None,
                    "projects": self.recent, "startup_error": self.startup_error,
                    "capabilities": {"native_picker": True, "repair_kit": True,
                                     "providers": ["gemini", "external"], "api_version": 1,
                                     "gemini_available": provider_available(),
                                     "automatic_firefly": False}}

    def submit(self, data):
        project = self.require_project()
        job = project.create_job(data["frame_id"], data["revision_id"], data["operation"],
                                 annotations=data.get("annotations"), options=data.get("options"))
        key = (project.snapshot()["id"], job["id"])
        self.futures[key] = self.executor.submit(project.run_job, job["id"])
        return job

    def resume(self, job_id, composition_options=None):
        project = self.require_project()
        job = project.get_job(job_id)
        if job["status"] not in {"queued", "failed"}:
            raise ValueError("Można wznowić zadanie w kolejce lub świadomie ponowić znany błąd. Wynik nieznanej generacji sprawdź w diagnostyce.")
        key = (project.snapshot()["id"], job_id)
        future = self.futures.get(key)
        if future and not future.done():
            raise ValueError("To zadanie już pracuje.")
        if composition_options is not None:
            project.set_resume_composition(job_id, composition_options)
        self.futures[key] = self.executor.submit(project.run_job, job_id)
        return job

    def expand_imports(self, paths):
        result = []
        allowed = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp"}
        for item in paths:
            path = Path(item["path"] if isinstance(item, dict) else item).expanduser()
            if path.is_dir():
                result.extend(str(p) for p in sorted(path.iterdir()) if p.is_file() and p.suffix.lower() in allowed)
            else:
                result.append(item)
        if not result:
            raise ValueError("Nie znaleziono obrazów w podanych ścieżkach.")
        return result

    def native_picker(self, kind):
        if kind not in {"folder", "images", "image"}:
            raise ValueError("Nieznany rodzaj wyboru plików.")
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        command = [sys.executable, str(APP_DIR / "archviz_cli.py"), "pick", kind]
        # A windowed PyInstaller executable has no stdout. A temporary result
        # file also makes the source and frozen picker use the same contract.
        with tempfile.TemporaryDirectory(prefix="archviz-picker-") as temporary:
            result_file = Path(temporary) / "result.json"
            if getattr(sys, "frozen", False):
                command = [sys.executable, "--archviz-pick", kind]
            command += ["--result-file", str(result_file)]
            result = subprocess.run(command, cwd=APP_DIR, capture_output=True,
                                    timeout=300, creationflags=flags)
            if result.returncode or not result_file.is_file():
                raise RuntimeError("Nie udało się otworzyć okna wyboru. Wpisz ścieżkę ręcznie.")
            return json.loads(result_file.read_text(encoding="utf-8"))

    def shutdown(self):
        # Worker jobs are not cancelled when a browser/desktop view closes.
        self.executor.shutdown(wait=True, cancel_futures=False)


class StudioHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address, service):
        self.service = service
        super().__init__(address, StudioHandler)


class StudioHandler(BaseHTTPRequestHandler):
    server_version = "ArchvizStudio/1"

    def log_message(self, format, *args):
        # No query strings, credentials, prompts or local file paths in HTTP logs.
        pass

    @property
    def service(self):
        return self.server.service

    def _headers(self, status, content_type, length, cache="no-store"):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", cache)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "SAMEORIGIN")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self'; frame-ancestors 'self'")
        self.end_headers()

    def _json(self, payload, status=200):
        raw = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        self._headers(status, "application/json; charset=utf-8", len(raw))
        self.wfile.write(raw)

    def _host_ok(self):
        host = self.headers.get("Host", "")
        return host in {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}

    def _authorize(self):
        if not self._host_ok():
            raise PermissionError("Nieprawidłowy adres lokalnej usługi.")
        origin = self.headers.get("Origin")
        allowed = {f"http://127.0.0.1:{self.server.server_port}", f"http://localhost:{self.server.server_port}"}
        if origin and origin not in allowed:
            raise PermissionError("Żądanie spoza lokalnego interfejsu zostało odrzucone.")
        if not secrets.compare_digest(self.headers.get("X-Studio-Token", ""), self.service.token):
            raise PermissionError("Odśwież połączenie z Archviz Studio.")

    def do_GET(self):
        try:
            if not self._host_ok():
                raise PermissionError("Nieprawidłowy adres lokalnej usługi.")
            parsed = urlparse(self.path)
            path = unquote(parsed.path)
            if path in {"/", "/index.html"}:
                raw = (APP_DIR / "archviz_studio.html").read_bytes()
                self._headers(200, "text/html; charset=utf-8", len(raw))
                self.wfile.write(raw)
            elif path == "/icon.png":
                raw = (APP_DIR / "archviz_studio.png").read_bytes()
                self._headers(200, "image/png", len(raw), "private, max-age=3600")
                self.wfile.write(raw)
            elif path == "/api/bootstrap":
                self._json({"token": self.service.token, "api_version": 1})
            elif path == "/api/health":
                self._json({"status": "ok", "service": "archviz-studio", "api_version": 1})
            elif path == "/api/state":
                self._json(self.service.state())
            elif path == "/api/pick":
                self._authorize()
                self._json(self.service.native_picker(parse_qs(parsed.query).get("kind", ["folder"])[0]))
            elif path.startswith("/api/jobs/"):
                self._json({"job": self.service.require_project().get_job(path.rsplit("/", 1)[-1])})
            elif path.startswith("/image/"):
                parts = path.strip("/").split("/")
                if len(parts) != 3:
                    raise ValueError("Nieprawidłowy identyfikator obrazu.")
                project = self.service.require_project()
                revision = project.get_revision(parts[1], parts[2])
                if self.headers.get("If-None-Match") == '"' + revision["sha256"] + '"':
                    self.send_response(304)
                    self.end_headers()
                    return
                image_path = Path(project.image_path(parts[1], parts[2])).resolve()
                work = Path(project.snapshot()["work_dir"]).resolve()
                if not image_path.is_relative_to(work):
                    raise PermissionError("Obraz znajduje się poza projektem.")
                raw = image_path.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Content-Length", str(len(raw)))
                self.send_header("Cache-Control", "private, max-age=31536000, immutable")
                self.send_header("ETag", '"' + revision["sha256"] + '"')
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                self.wfile.write(raw)
            else:
                self._json({"error": "Nie znaleziono zasobu."}, 404)
        except Exception as error:
            self._error(error)

    def _error(self, error):
        if isinstance(error, (BrokenPipeError, ConnectionResetError)):
            return
        status = 403 if isinstance(error, PermissionError) else 400 if isinstance(error, (ValueError, KeyError, FileNotFoundError, FileExistsError)) else 500
        self._json({"error": str(error) or type(error).__name__, "type": type(error).__name__}, status)

    def do_POST(self):
        try:
            self._authorize()
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 4 * 1024 * 1024:
                raise ValueError("Nieprawidłowy rozmiar żądania.")
            data = json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(data, dict):
                raise ValueError("Oczekiwano obiektu JSON.")
            path = urlparse(self.path).path
            if path == "/api/project/create":
                self._json({"project": self.service.create_project(data)})
                return
            if path == "/api/project/open":
                self._json({"project": self.service.open_project(data["work_dir"])})
                return
            project = self.service.require_project()
            if path == "/api/project/settings":
                values = dict(data.get("settings", {}))
                values.update({k: v for k, v in data.items() if k != "settings"})
                project.update_settings(**values)
                with self.service.lock:
                    self.service._remember(project)
                response = {}
            elif path == "/api/import":
                project.import_images(self.service.expand_imports(data["paths"]))
                response = {}
            elif path == "/api/annotations":
                revision = project.save_annotations(data["frame_id"], data["revision_id"], data["annotations"], source_sha256=data.get("source_sha256"))
                response = {"revision": revision}
            elif path == "/api/jobs":
                response = {"job": self.service.submit(data)}
            elif path == "/api/jobs/resume":
                response = {"job": self.service.resume(data["job_id"], data.get("composition_options"))}
            elif path == "/api/jobs/cancel":
                response = {"job": project.cancel_job(data["job_id"])}
            elif path == "/api/approve":
                project.approve(data["frame_id"], data["revision_id"])
                response = {}
            elif path == "/api/reject":
                project.reject(data["frame_id"], data["revision_id"])
                response = {}
            elif path == "/api/export":
                response = {"receipt": project.export_approved(data.get("frame_ids"))}
            elif path == "/api/repair-kit":
                response = {"kit": project.export_repair_kit(data["frame_id"], data["revision_id"], data.get("annotations"))}
            elif path == "/api/import-repair":
                response = {"revision": project.import_repair(data["frame_id"], data["revision_id"], data["kit_path"], data["result_path"])}
            elif path == "/api/diagnostics":
                response = {"diagnostics": project.diagnostics(data.get("destination"))}
            else:
                self._json({"error": "Nie znaleziono operacji."}, 404)
                return
            response["project"] = project.snapshot()
            self._json(response)
        except Exception as error:
            self._error(error)


def run_server(port=DEFAULT_PORT, registry=None, ready_file=None):
    service = StudioService(registry)
    server = StudioHTTPServer(("127.0.0.1", port), service)
    url = f"http://127.0.0.1:{server.server_port}/"
    if ready_file:
        atomic_json(ready_file, {"url": url, "port": server.server_port, "pid": os.getpid()})
    if sys.stdout is not None:
        print(json.dumps({"url": url, "pid": os.getpid()}), flush=True)
    try:
        server.serve_forever(poll_interval=.2)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        service.shutdown()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--registry")
    parser.add_argument("--ready-file")
    args = parser.parse_args()
    run_server(args.port, args.registry, args.ready_file)
