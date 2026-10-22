"""Archviz Studio local automation and diagnostic entry point."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import urllib.request


def emit(value):
    print(json.dumps(value, ensure_ascii=False, default=str, indent=2), flush=True)


def pick_result(kind, result_file=None):
    result = pick(kind)
    if result_file:
        Path(result_file).write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    else:
        emit(result)


def pick(kind):
    from PySide6.QtWidgets import QApplication, QFileDialog
    app = QApplication.instance() or QApplication(["Archviz Studio"])
    if kind == "folder":
        value = QFileDialog.getExistingDirectory(None, "Archviz Studio — wybierz folder")
        result = [value] if value else []
    elif kind == "images":
        result, _ = QFileDialog.getOpenFileNames(None, "Archviz Studio — dodaj wizualizacje", "", "Obrazy (*.jpg *.jpeg *.png *.tif *.tiff *.webp)")
    else:
        value, _ = QFileDialog.getOpenFileName(None, "Archviz Studio — wybierz wynik", "", "Obrazy (*.png *.jpg *.jpeg *.tif *.tiff)")
        result = [value] if value else []
    return {"paths": result}


def service_request(base_url, route, payload=None):
    base = base_url.rstrip("/")
    if payload is None:
        with urllib.request.urlopen(base + route, timeout=30) as response:
            return json.load(response)
    with urllib.request.urlopen(base + "/api/bootstrap", timeout=10) as response:
        token = json.load(response)["token"]
    request = urllib.request.Request(base + route, data=json.dumps(payload).encode("utf-8"),
                                     headers={"Content-Type": "application/json", "X-Studio-Token": token})
    with urllib.request.urlopen(request, timeout=300) as response:
        return json.load(response)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    serve = commands.add_parser("serve", help="Run the persistent local service")
    serve.add_argument("--port", type=int, default=8890)
    serve.add_argument("--registry")
    serve.add_argument("--ready-file")
    gui = commands.add_parser("gui", help="Open the real desktop editor")
    gui.add_argument("--url", default="http://127.0.0.1:8890/")
    picker = commands.add_parser("pick", help=argparse.SUPPRESS)
    picker.add_argument("kind", choices=["folder", "image", "images"])
    picker.add_argument("--result-file")
    state = commands.add_parser("state", help="Inspect the same state used by the GUI")
    state.add_argument("--url", default="http://127.0.0.1:8890/")
    create = commands.add_parser("create", help="Create an isolated project")
    create.add_argument("--name", required=True)
    create.add_argument("--work", required=True)
    create.add_argument("--input", action="append", default=[])
    create.add_argument("--output", required=True)
    for command in ["inspect", "diagnose", "import", "annotate", "run", "resume", "cancel", "recover", "export", "repair-kit", "import-repair"]:
        item = commands.add_parser(command)
        item.add_argument("--work", required=True)
        if command == "import":
            item.add_argument("paths", nargs="+")
        if command in {"annotate", "run", "repair-kit", "import-repair"}:
            item.add_argument("--frame", required=True)
            item.add_argument("--revision", required=True)
        if command in {"annotate", "run", "repair-kit"}:
            item.add_argument("--annotations", help="JSON list or object containing annotations")
        if command == "annotate":
            item.add_argument("--source-sha256")
        if command == "run":
            item.add_argument("--operation", choices=["color", "edge", "people", "local"], required=True)
            item.add_argument("--options", help="JSON options file")
        if command in {"resume", "cancel"}:
            item.add_argument("--job", required=True, help="Existing queued/failed job; cached model output is reused")
        if command == "resume":
            item.add_argument("--compositor", choices=["local", "comfy"])
            item.add_argument("--comfy-url")
        if command == "import-repair":
            item.add_argument("--kit", required=True)
            item.add_argument("--result", required=True)
        if command in {"diagnose", "export"}:
            item.add_argument("--destination" if command == "diagnose" else "--frame", action="append" if command == "export" else "store")
    args = parser.parse_args(argv)
    if args.command == "serve":
        from archviz_server import run_server
        run_server(args.port, args.registry, args.ready_file)
        return 0
    if args.command == "gui":
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QApplication
        from archviz_studio_widget import ArchvizStudioWidget
        QApplication.setAttribute(Qt.AA_ShareOpenGLContexts)
        app = QApplication.instance() or QApplication(["Archviz Studio"])
        window = ArchvizStudioWidget(url=args.url)
        window.resize(1500, 980)
        window.setWindowTitle("Archviz Studio — OgarniaczSM")
        window.show()
        return app.exec()
    if args.command == "pick":
        pick_result(args.kind, args.result_file)
        return 0
    if args.command == "state":
        emit(service_request(args.url, "/api/state"))
        return 0
    from archviz_core import StudioProject
    if args.command == "create":
        project = StudioProject.create(args.name, args.work, args.input, args.output)
        emit(project.snapshot())
        return 0
    project = StudioProject(args.work)
    annotations = None
    if getattr(args, "annotations", None):
        annotations = json.loads(Path(args.annotations).read_text(encoding="utf-8-sig"))
        if isinstance(annotations, dict):
            annotations = annotations["annotations"]
    if args.command == "inspect":
        emit(project.snapshot())
    elif args.command == "diagnose":
        emit(project.diagnostics(args.destination))
    elif args.command == "import":
        emit(project.import_images(args.paths))
    elif args.command == "annotate":
        emit(project.save_annotations(args.frame, args.revision, annotations or [], args.source_sha256))
    elif args.command == "run":
        options = json.loads(Path(args.options).read_text(encoding="utf-8-sig")) if args.options else None
        job = project.create_job(args.frame, args.revision, args.operation, annotations, options)
        result = project.run_job(job["id"])
        emit(result)
        return 0 if result["status"] == "completed" else 1
    elif args.command == "resume":
        composition = {k: v for k, v in {"compositor": args.compositor, "comfy_url": args.comfy_url}.items() if v is not None}
        if composition:
            project.set_resume_composition(args.job, composition)
        result = project.run_job(args.job)
        emit(result)
        return 0 if result["status"] == "completed" else 1
    elif args.command == "recover":
        emit(project.recover_jobs())
    elif args.command == "cancel":
        emit(project.cancel_job(args.job))
    elif args.command == "export":
        emit(project.export_approved(args.frame))
    elif args.command == "repair-kit":
        emit(project.export_repair_kit(args.frame, args.revision, annotations))
    elif args.command == "import-repair":
        emit(project.import_repair(args.frame, args.revision, args.kit, args.result))
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        raise SystemExit(main())
    except Exception as error:
        emit({"error": str(error), "type": type(error).__name__})
        raise SystemExit(1)
