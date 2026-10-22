"""Persistent, mask-constrained image editing for Archviz Studio.

GUI, HTTP and CLI use this same engine. Images/revisions are immutable; project
metadata uses atomic writes and a cross-process writer lock. A technical PASS
never means that a person has approved the visual result.
"""
from __future__ import annotations

import base64
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
from functools import lru_cache
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import shutil
import socket
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zipfile

import numpy as np
from PIL import Image, ImageCms, ImageDraw, ImageEnhance, ImageFilter, ImageOps

MODEL = "gemini-3-pro-image"
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp", ".bmp"}
DEFAULT_SETTINGS = {
    "model": MODEL, "thinking_level": "HIGH", "image_size": "2K",
    "max_paid_calls": 3, "context_px": 128, "edge_width": 12,
    "compositor": "local", "comfy_url": "http://127.0.0.1:18188",
}
_LOCKS: dict[str, threading.RLock] = {}
_LOCKS_GUARD = threading.Lock()


class StudioError(ValueError):
    """A user-actionable validation or project-state error."""


class _UnknownProviderOutcome(RuntimeError):
    pass


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def file_sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _json_read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def _atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        with temp.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if temp.exists():
            temp.unlink()


def _within(path, parent):
    try:
        Path(path).resolve().relative_to(Path(parent).resolve())
        return True
    except ValueError:
        return False


def _overlap(a, b):
    return _within(a, b) or _within(b, a)


@lru_cache(maxsize=1)
def _srgb():
    return ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()


def _load_rgb(path):
    with Image.open(path) as source:
        source.load()
        im = ImageOps.exif_transpose(source)
        profile = source.info.get("icc_profile")
        if profile:
            try:
                im = ImageCms.profileToProfile(im, ImageCms.ImageCmsProfile(io.BytesIO(profile)),
                                              ImageCms.createProfile("sRGB"), outputMode="RGB")
            except (OSError, ValueError, ImageCms.PyCMSError):
                raise StudioError("Nie można odczytać profilu kolorów obrazu: " + Path(path).name)
        return im.convert("RGB")


def _save_rgb(path, array):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(np.asarray(array, dtype=np.uint8), "RGB").save(path, icc_profile=_srgb())


def _safe_name(value):
    value = str(value).strip()
    if not value or Path(value).name != value or "/" in value or "\\" in value:
        raise StudioError("Nazwa eksportu musi być samą nazwą pliku.")
    if any(c in value for c in '<>:"|?*') or value.endswith((" ", ".")):
        raise StudioError("Niepoprawna nazwa pliku eksportu.")
    if Path(value).suffix.lower() not in {".jpg", ".jpeg"}:
        raise StudioError("Eksport końcowy musi mieć rozszerzenie JPG.")
    return value


def _redact(value):
    if isinstance(value, dict):
        return {str(k): ("[REDACTED]" if any(t in str(k).lower() for t in
                ("api_key", "apikey", "authorization", "password", "secret", "access_token"))
                else _redact(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact(v) for v in value]
    if isinstance(value, str):
        value = re.sub(r"AIza[0-9A-Za-z_-]{20,}", "[REDACTED]", value)
        value = re.sub(r"\bsk-[A-Za-z0-9_-]{16,}", "[REDACTED]", value)
        value = re.sub(r"(?i)(api[_-]?key|authorization|password|secret)\s*[:=]\s*[^\s,;]+",
                       r"\1=[REDACTED]", value)
        return value
    return value


def _api_key():
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key and os.name == "nt":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as reg:
                key = str(winreg.QueryValueEx(reg, "GEMINI_API_KEY")[0]).strip()
        except (OSError, ValueError):
            pass
    if not key or key.lower() in {"not-set", "none", "null"}:
        raise StudioError("Brak GEMINI_API_KEY. Ustaw istniejący klucz użytkownika Windows i ponów zadanie.")
    return key


def _pid_alive(pid):
    """Conservative liveness check; os.kill(pid,0) is unsafe on Windows."""
    try:
        pid=int(pid)
    except (TypeError,ValueError):
        return False
    if pid<=0:return False
    if pid==os.getpid():return True
    if os.name=="nt":
        import ctypes
        from ctypes import wintypes
        kernel=ctypes.WinDLL("kernel32",use_last_error=True)
        kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
        kernel.OpenProcess.restype=wintypes.HANDLE
        kernel.GetExitCodeProcess.argtypes=[wintypes.HANDLE,ctypes.POINTER(wintypes.DWORD)]
        kernel.GetExitCodeProcess.restype=wintypes.BOOL
        kernel.CloseHandle.argtypes=[wintypes.HANDLE]
        handle=kernel.OpenProcess(0x1000,False,pid)
        if not handle:return ctypes.get_last_error() not in {87,1168}
        try:
            code=wintypes.DWORD()
            if not kernel.GetExitCodeProcess(handle,ctypes.byref(code)):return True
            return code.value==259
        finally:kernel.CloseHandle(handle)
    try:
        os.kill(pid,0)
        return True
    except ProcessLookupError:return False
    except PermissionError:return True


def provider_available():
    try:
        _api_key()
        return True
    except StudioError:
        return False


def _finite(value, name, low, high):
    try:
        result = float(value)
    except (TypeError, ValueError):
        raise StudioError("Niepoprawny parametr: " + name)
    if not math.isfinite(result) or not low <= result <= high:
        raise StudioError("Parametr poza zakresem: " + name)
    return result


def rasterize_annotations(size, annotations, operation="local", edge_width=12):
    """Return allowed-alpha and hard protection masks in original image pixels.

    Edge rectangles/polygons are outlines, never their filled bounding boxes.
    Soft selection coverage is feathered inward only. Hard protections always
    win, including their antialias/blur support explicitly painted by the user.
    """
    w, h = size
    edit = Image.new("L", size)
    protect = Image.new("L", size)
    if not isinstance(annotations, list) or len(annotations) > 1000:
        raise StudioError("Niepoprawna lista zaznaczeń.")
    for ann in annotations:
        role = ann.get("role", "edit")
        if role not in {"edit", "protect", "foreground", "background"}:
            raise StudioError("Niepoprawna rola zaznaczenia.")
        target = protect if role != "edit" else edit
        draw = ImageDraw.Draw(target)
        kind = ann.get("type", "pen")
        width = int(round(_finite(ann.get("width", edge_width if operation == "edge" and role == "edit" else 12), "width", 1, 512)))
        pts = ann.get("points") or []
        clean = []
        for pt in pts:
            if not isinstance(pt, (list, tuple)) or len(pt) != 2:
                raise StudioError("Niepoprawny punkt maski.")
            clean.append((_finite(pt[0], "x", -w, 2*w), _finite(pt[1], "y", -h, 2*h)))
        outline = operation == "edge" and role == "edit"
        if kind in {"rectangle", "rect"}:
            bounds = ann.get("bounds")
            if not isinstance(bounds, (list, tuple)) or len(bounds) != 4:
                raise StudioError("Prostokąt wymaga granic [left,top,right,bottom].")
            x0, y0, x1, y1 = [_finite(n, "bounds", -max(w,h), 2*max(w,h)) for n in bounds]
            box = (min(x0,x1), min(y0,y1), max(x0,x1), max(y0,y1))
            draw.rectangle(box, outline=255, width=width) if outline else draw.rectangle(box, fill=255)
        elif kind == "polygon":
            if len(clean) < 3:
                raise StudioError("Wielokąt wymaga minimum trzech punktów.")
            if outline:
                draw.line(clean + [clean[0]], fill=255, width=width, joint="curve")
            else:
                draw.polygon(clean, fill=255)
        elif kind in {"pen", "brush"}:
            if not clean:
                raise StudioError("Pędzel wymaga punktów w oryginalnych pikselach.")
            if len(clean) > 1:
                draw.line(clean, fill=255, width=width, joint="curve")
            r = width / 2
            for x,y in [clean[0], clean[-1]]:
                draw.ellipse((x-r,y-r,x+r,y+r), fill=255)
        else:
            raise StudioError("Nieobsługiwany typ zaznaczenia: " + str(kind))
    ea = np.asarray(edit, dtype=np.uint8).copy()
    pm = np.asarray(protect, dtype=np.uint8).copy()
    # Inward coverage only: no implicit expansion into unselected pixels.
    aa = np.asarray(edit.filter(ImageFilter.GaussianBlur(.55)), dtype=np.uint8).copy()
    aa[ea == 0] = 0
    aa[pm > 0] = 0
    return aa, pm


def _linear_blend(base, foreground, alpha):
    a = np.asarray(alpha, dtype=np.float32) / 255
    b = np.asarray(base, dtype=np.float32) / 255
    f = np.asarray(foreground, dtype=np.float32) / 255
    bl = np.where(b <= .04045, b/12.92, ((b+.055)/1.055)**2.4)
    fl = np.where(f <= .04045, f/12.92, ((f+.055)/1.055)**2.4)
    mixed = bl*(1-a[...,None]) + fl*a[...,None]
    srgb = np.where(mixed <= .0031308, mixed*12.92, 1.055*np.power(np.maximum(mixed,0),1/2.4)-.055)
    result = np.clip(np.rint(srgb*255),0,255).astype(np.uint8)
    result[a == 0] = np.asarray(base)[a == 0]
    return result


class StudioProject:
    def __init__(self, work_dir):
        self.work_dir = Path(work_dir).expanduser().resolve()
        self.manifest_path = self.work_dir / "project.json"
        if not self.manifest_path.is_file():
            raise StudioError("Nie znaleziono project.json w wybranym folderze pracy.")
        with _LOCKS_GUARD:
            self._thread_lock = _LOCKS.setdefault(str(self.work_dir).casefold(), threading.RLock())
        self._load()

    @classmethod
    def create(cls, name, work_dir, input_dirs, output_dir):
        work = Path(work_dir).expanduser().resolve()
        output = Path(output_dir).expanduser().resolve()
        inputs = [str(Path(x).expanduser().resolve()) for x in (input_dirs or [])]
        cls._validate_folders(work, inputs, output)
        if not str(name).strip():
            raise StudioError("Podaj nazwę projektu.")
        work.mkdir(parents=True, exist_ok=True)
        if (work/"project.json").exists():
            raise StudioError("Projekt już istnieje. Użyj Otwórz projekt.")
        if any(work.iterdir()):
            raise StudioError("Nowy folder pracy musi być pusty.")
        output.mkdir(parents=True, exist_ok=True)
        value = {"schema_version":1,"id":uuid.uuid4().hex,"name":str(name).strip(),
                 "created_at":utc_now(),"updated_at":utc_now(),"work_dir":str(work),
                 "input_dirs":inputs,"output_dir":str(output),"settings":deepcopy(DEFAULT_SETTINGS),
                 "api_calls_used":0,"frames":[],"jobs":[],"exports":[],"repair_kits":[]}
        _atomic_json(work/"project.json", value)
        return cls(work)

    @staticmethod
    def _validate_folders(work, inputs, output):
        if work == output or _within(work, output):
            raise StudioError("Folder wynikowy nie może zawierać folderu pracy.")
        for source in inputs:
            if _overlap(source, output):
                raise StudioError("Folder output musi być oddzielony od folderów input.")
            if Path(source).resolve() == work:
                raise StudioError("Folder pracy nie może być folderem input.")

    def _load(self):
        try:
            p = _json_read(self.manifest_path)
        except (OSError, ValueError) as error:
            raise StudioError("Nie można odczytać manifestu projektu: " + str(error))
        if p.get("schema_version") != 1 or not isinstance(p.get("frames"), list) or not isinstance(p.get("jobs"), list):
            raise StudioError("Nieobsługiwany format manifestu projektu.")
        # The physical work folder is authoritative after a portable project move.
        p["work_dir"] = str(self.work_dir)
        return p

    def _save(self, p, event=None):
        p["updated_at"] = utc_now()
        _atomic_json(self.manifest_path, p)
        if event:
            with (self.work_dir/"events.jsonl").open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(_redact({"at":utc_now(),**event}),ensure_ascii=False)+"\n")

    @contextmanager
    def _write_lock(self):
        with self._thread_lock:
            lock = self.work_dir/".writer.lock"
            deadline = time.monotonic()+15
            while True:
                try:
                    fd = os.open(str(lock), os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600)
                    break
                except FileExistsError:
                    if time.monotonic() >= deadline:
                        raise StudioError("Projekt jest zapisywany przez inny proces. Sprawdź .writer.lock; nie usuwaj go podczas pracy.")
                    time.sleep(.05)
            try:
                with os.fdopen(fd,"w",encoding="utf-8") as stream:
                    json.dump({"host":socket.gethostname(),"pid":os.getpid(),"created_at":utc_now()},stream)
                yield
            finally:
                lock.unlink(missing_ok=True)

    def _path(self, value):
        path = Path(value)
        if not path.is_absolute():
            path = self.work_dir/path
        path = path.resolve()
        if not _within(path,self.work_dir):
            raise StudioError("Ścieżka artefaktu wychodzi poza folder projektu.")
        return path

    def _rel(self, path):
        return str(Path(path).resolve().relative_to(self.work_dir)).replace("\\","/")

    @staticmethod
    def _frame(p, frame_id):
        for frame in p["frames"]:
            if frame["id"] == frame_id:
                return frame
        raise StudioError("Nie znaleziono kadru.")

    @classmethod
    def _revision(cls, p, frame_id, revision_id):
        frame = cls._frame(p,frame_id)
        for revision in frame["revisions"]:
            if revision["id"] == revision_id:
                return revision
        raise StudioError("Nie znaleziono wersji obrazu.")

    @staticmethod
    def _job(p, job_id):
        for job in p["jobs"]:
            if job["id"] == job_id:
                return job
        raise StudioError("Nie znaleziono zadania.")

    def snapshot(self):
        with self._thread_lock:
            return deepcopy(self._load())

    def update_settings(self, **values):
        with self._write_lock():
            p = self._load()
            settings = values.pop("settings", {}) or {}
            settings.update({k:values.pop(k) for k in list(values) if k in DEFAULT_SETTINGS})
            if settings.get("model",MODEL) != MODEL or settings.get("thinking_level","HIGH") != "HIGH":
                raise StudioError("Ten profil używa wyłącznie Nano Banana Pro z jawnym HIGH.")
            for key in settings:
                if key not in DEFAULT_SETTINGS:
                    raise StudioError("Nieobsługiwane ustawienie: "+str(key))
            if "max_paid_calls" in settings:
                settings["max_paid_calls"] = int(_finite(settings["max_paid_calls"],"max_paid_calls",0,100))
            for key,lo,hi in [("context_px",0,2048),("edge_width",1,512)]:
                if key in settings:settings[key]=int(_finite(settings[key],key,lo,hi))
            if settings.get("image_size", "2K") not in {"1K","2K","4K"}:
                raise StudioError("Niepoprawna rozdzielczość generacji.")
            if settings.get("compositor","local") not in {"local","comfy"}:
                raise StudioError("Niepoprawny silnik kompozycji.")
            if "name" in values:
                if not str(values["name"]).strip():raise StudioError("Nazwa projektu jest pusta.")
                p["name"] = str(values["name"]).strip()
            if "input_dirs" in values:p["input_dirs"]=[str(Path(x).expanduser().resolve()) for x in values["input_dirs"]]
            if "output_dir" in values:p["output_dir"]=str(Path(values["output_dir"]).expanduser().resolve())
            self._validate_folders(self.work_dir,p["input_dirs"],Path(p["output_dir"]))
            for frame in p["frames"]:
                if _within(frame["source_path"],p["output_dir"]):
                    raise StudioError("Folder output zawiera źródło jednego z kadrów.")
            p["settings"].update(settings)
            self._save(p,{"type":"settings_updated"})
            return deepcopy(p)

    def import_images(self, paths):
        if not isinstance(paths,list) or not paths:
            raise StudioError("Wybierz pliki albo folder input.")
        entries=[]
        for item in paths:
            row={"path":str(item)} if isinstance(item,(str,Path)) else dict(item)
            path=Path(row["path"]).expanduser().resolve()
            if path.is_dir():
                entries.extend({"path":str(x)} for x in sorted(path.iterdir()) if x.is_file() and x.suffix.lower() in IMAGE_EXTENSIONS)
            else:entries.append({**row,"path":str(path)})
        if not entries:raise StudioError("Nie znaleziono obsługiwanych obrazów.")
        with self._write_lock():
            p=self._load()
            seen={(r["source_path"],r.get("source_sha256")) for r in p["frames"]}
            for row in entries:
                source=Path(row["path"])
                if not source.is_file() or source.suffix.lower() not in IMAGE_EXTENSIONS:
                    raise StudioError("Nieobsługiwany obraz: "+source.name)
                if _within(source,self.work_dir) or _within(source,p["output_dir"]):
                    raise StudioError("Nie importuj plików z folderu work ani output.")
                source_hash=file_sha256(source)
                if (str(source),source_hash) in seen:continue
                export_name=_safe_name(row.get("export_name") or source.stem+".jpg")
                im=_load_rgb(source)
                if im.width*im.height>100_000_000:raise StudioError("Obraz przekracza limit100MP.")
                fid=uuid.uuid4().hex;rid=uuid.uuid4().hex
                folder=self.work_dir/"frames"/fid/"revisions"/rid;folder.mkdir(parents=True,exist_ok=False)
                original=folder/("original"+source.suffix.lower());shutil.copyfile(source,original)
                if file_sha256(original)!=source_hash:raise StudioError("Błąd weryfikacji kopii źródłowej.")
                target=folder/"result.png";im.save(target,icc_profile=_srgb())
                revision={"id":rid,"parent_id":None,"image_path":self._rel(target),"sha256":file_sha256(target),
                          "status":"source","annotations":[],"created_at":utc_now(),
                          "qa":{"technical_status":"PASS","visual_status":"PENDING","source_frozen":True,
                                "width":im.width,"height":im.height,"outside_changed_pixels":0,"protected_changed_pixels":0}}
                frame={"id":fid,"name":row.get("name") or source.name,"source_path":str(source),
                       "source_sha256":source_hash,"frozen_source_path":self._rel(original),"export_name":export_name,
                       "active_revision_id":rid,"approved_revision_id":None,"revisions":[revision]}
                p["frames"].append(frame);seen.add((str(source),source_hash))
            self._save(p,{"type":"images_imported","count":len(entries)})
            return deepcopy(p)

    def get_revision(self,frame_id,revision_id):
        return deepcopy(self._revision(self._load(),frame_id,revision_id))

    def image_path(self,frame_id,revision_id):
        revision=self.get_revision(frame_id,revision_id);path=self._path(revision["image_path"])
        if not path.is_file():raise StudioError("Brak obrazu wersji.")
        return path

    def _verified_revision(self,p,frame_id,revision_id):
        revision=self._revision(p,frame_id,revision_id);path=self._path(revision["image_path"])
        if not path.is_file() or file_sha256(path)!=revision["sha256"]:
            raise StudioError("Obraz wersji został zmieniony. Nie można użyć starego SHA.")
        return revision,path

    def save_annotations(self,frame_id,revision_id,annotations,source_sha256=None):
        with self._write_lock():
            p=self._load();revision,path=self._verified_revision(p,frame_id,revision_id)
            if source_sha256 and source_sha256!=revision["sha256"]:
                raise StudioError("Uwagi dotyczą innego obrazu (niezgodny SHA256).")
            with Image.open(path) as im:
                rasterize_annotations(im.size,annotations)
            revision["annotations"]=deepcopy(annotations)
            self._save(p,{"type":"annotations_saved","frame_id":frame_id,"revision_id":revision_id})
            return deepcopy(revision)

    def create_job(self,frame_id,revision_id,operation,annotations=None,options=None):
        if operation not in {"color","edge","people","local"}:
            raise StudioError("Nieobsługiwany rodzaj poprawki.")
        options=deepcopy(options or {})
        with self._write_lock():
            p=self._load();revision,path=self._verified_revision(p,frame_id,revision_id)
            anns=deepcopy(revision["annotations"] if annotations is None else annotations)
            # Previously marked protections propagate to new edits of this exact image.
            if annotations is not None:
                ids={a.get("id") for a in anns}
                anns.extend(deepcopy(a) for a in revision["annotations"] if a.get("role","edit")!="edit" and a.get("id") not in ids)
            settings={**p["settings"],**options}
            width=_finite(settings.get("edge_width",12),"edge_width",1,512)
            context=int(_finite(settings.get("context_px",128),"context_px",0,2048))
            base=Image.open(path).convert("RGB");allowed,protected=rasterize_annotations(base.size,anns,operation,width)
            ys,xs=np.nonzero(allowed)
            if len(xs)==0:raise StudioError("Zaznacz obszar poprawki; maska nie może być pusta ani w całości chroniona.")
            job_id=uuid.uuid4().hex;folder=self.work_dir/"jobs"/job_id;folder.mkdir(parents=True,exist_ok=False)
            Image.fromarray(allowed).save(folder/"allowed_mask.png");Image.fromarray(protected).save(folder/"protect_mask.png")
            bbox=[max(0,int(xs.min())-context),max(0,int(ys.min())-context),min(base.width,int(xs.max())+context+1),min(base.height,int(ys.max())+context+1)]
            # At least a modest material context, clipped to the native frame.
            for axis,limit in [(0,base.width),(1,base.height)]:
                gap=max(0,256-(bbox[axis+2]-bbox[axis]));bbox[axis]=max(0,bbox[axis]-gap//2);bbox[axis+2]=min(limit,bbox[axis+2]+gap-gap//2)
            target=folder/"context.png";base.crop(bbox).save(target,icc_profile=_srgb())
            overlay=np.asarray(base).copy();sel=allowed>0;pro=protected>0
            overlay[sel]=np.rint(overlay[sel]*.5+np.array([20,210,230])*.5).astype(np.uint8)
            overlay[pro]=np.rint(overlay[pro]*.5+np.array([65,220,80])*.5).astype(np.uint8)
            _save_rgb(folder/"mask_review.png",overlay)
            job={"id":job_id,"frame_id":frame_id,"parent_revision_id":revision_id,"parent_sha256":revision["sha256"],
                 "operation":operation,"annotations":anns,"options":_redact(options),"status":"queued","stage":"mask_ready","progress":5,
                 "created_at":utc_now(),"error":None,"result_revision_id":None,
                 "artifacts":{"allowed_mask":self._rel(folder/"allowed_mask.png"),"protect_mask":self._rel(folder/"protect_mask.png"),
                              "context":self._rel(target),"mask_review":self._rel(folder/"mask_review.png"),"crop_box":bbox},
                 "mask_preflight":{"allowed_pixels":int(sel.sum()),"protected_pixels":int(pro.sum()),"overlap_pixels":int((sel&pro).sum()),
                                   "semantic_review":"USER_MASK","allowed_sha256":file_sha256(folder/"allowed_mask.png"),"protect_sha256":file_sha256(folder/"protect_mask.png")}}
            _atomic_json(folder/"job.json",job);p["jobs"].append(job)
            self._save(p,{"type":"job_created","job_id":job_id,"operation":operation})
            return deepcopy(job)

    def get_job(self,job_id):
        return deepcopy(self._job(self._load(),job_id))

    def recover_jobs(self):
        """Explicit startup recovery only; never starts a provider request.

        A different host or a live worker is left alone. Cached real provider
        output can be resumed; a dispatched call without its receipt is UNKNOWN.
        """
        lock=self.work_dir/".writer.lock"
        if lock.exists():
            try:
                old=_json_read(lock);before=file_sha256(lock)
            except (OSError,ValueError):
                raise StudioError("Nieczytelna blokada zapisu. Sprawdź .writer.lock przed ręcznym odzyskaniem projektu.")
            if str(old.get("host","")).casefold()==socket.gethostname().casefold() and not _pid_alive(old.get("pid")):
                if lock.exists() and file_sha256(lock)==before:lock.unlink()
        recovered=[];skipped=[]
        with self._write_lock():
            p=self._load()
            for job in p["jobs"]:
                if job.get("status")!="running":continue
                host=job.get("worker_host")
                if (host and str(host).casefold()!=socket.gethostname().casefold()) or _pid_alive(job.get("worker_pid")):
                    skipped.append(job["id"]);continue
                folder=self.work_dir/"jobs"/job["id"];valid_cache=False
                try:
                    receipt=_json_read(folder/"provider_receipt.json")
                    valid_cache=file_sha256(folder/"provider_output.png")==receipt["output_sha256"]
                except (OSError,ValueError,KeyError):pass
                if job.get("paid_call_reserved_at") and not valid_cache:
                    job.update(status="unknown",stage="provider_outcome_unknown",error="Proces przerwano po wysłaniu płatnego żądania; brak kompletnego wyniku i receipt. Brak automatycznej ponownej generacji.")
                else:
                    job.update(status="queued",stage="resume_ready",error=None,progress=55 if valid_cache else 5)
                job["recovered_at"]=utc_now();job["recovery_used_provider_cache"]=valid_cache
                _atomic_json(folder/"job.json",job);recovered.append(job["id"])
            if recovered:self._save(p,{"type":"orphan_jobs_recovered","job_ids":recovered})
        return {"recovered":recovered,"skipped_live":skipped,"project":deepcopy(p)}

    def _stage(self,job_id,stage,progress,**extra):
        with self._write_lock():
            p=self._load();job=self._job(p,job_id);job.update({"stage":stage,"progress":progress,"updated_at":utc_now(),**_redact(extra)})
            self._save(p)
            _atomic_json(self.work_dir/"jobs"/job_id/"job.json",job)
            return deepcopy(job)

    def set_resume_composition(self,job_id,options):
        """Change only the finishing endpoint while preserving the paid input."""
        if not isinstance(options,dict) or set(options)-{"compositor","comfy_url"}:
            raise StudioError("Przy wznowieniu można zmienić wyłącznie kompozycję i adres ComfyUI.")
        if options.get("compositor","local") not in {"local","comfy"}:
            raise StudioError("Niepoprawny silnik kompozycji.")
        if "comfy_url" in options:
            parsed=urllib.parse.urlparse(str(options["comfy_url"]))
            if parsed.scheme not in {"http","https"} or not parsed.netloc or parsed.username or parsed.query or parsed.fragment:
                raise StudioError("Niepoprawny adres ComfyUI.")
        with self._write_lock():
            p=self._load();job=self._job(p,job_id)
            if job["status"] not in {"queued","failed"}:
                raise StudioError("Zmiana kompozycji jest dostępna wyłącznie przed jawnym wznowieniem zadania w kolejce lub ze znanym błędem.")
            job["resume_composition_options"]=dict(options)
            self._save(p,{"type":"resume_composition_updated","job_id":job_id,"options":dict(options)})
            _atomic_json(self.work_dir/"jobs"/job_id/"job.json",job)
            return deepcopy(job)

    def cancel_job(self,job_id):
        """Discard a queued draft without interrupting an in-flight paid call."""
        with self._write_lock():
            p=self._load();job=self._job(p,job_id)
            if job["status"]!="queued":
                raise StudioError("Anulować można tylko zadanie, które jeszcze nie pracuje.")
            job.update(status="cancelled",stage="cancelled",progress=0,updated_at=utc_now())
            self._save(p,{"type":"job_cancelled","job_id":job_id})
            _atomic_json(self.work_dir/"jobs"/job_id/"job.json",job)
            return deepcopy(job)

    def run_job(self,job_id):
        with self._write_lock():
            p=self._load();job=self._job(p,job_id)
            if job["status"]=="completed":return deepcopy(job)
            if job["status"]=="cancelled":raise StudioError("To zadanie zostało anulowane.")
            if job["status"] in {"running","unknown"}:
                raise StudioError("Zadanie działa lub wynik płatnego wywołania jest nieznany. Nie będzie automatycznie powtórzone.")
            revision,path=self._verified_revision(p,job["frame_id"],job["parent_revision_id"])
            if revision["sha256"]!=job["parent_sha256"]:raise StudioError("Zmieniona baza zadania.")
            job.update(status="running",stage="preparing",progress=10,error=None,started_at=utc_now(),worker_pid=os.getpid(),worker_host=socket.gethostname())
            settings={**p["settings"],**job["options"],**job.get("resume_composition_options",{})};job=deepcopy(job);self._save(p,{"type":"job_started","job_id":job_id})
        folder=self.work_dir/"jobs"/job_id
        try:
            base=np.asarray(Image.open(path).convert("RGB")).copy()
            allowed=np.asarray(Image.open(self._path(job["artifacts"]["allowed_mask"])).convert("L")).copy()
            protected=np.asarray(Image.open(self._path(job["artifacts"]["protect_mask"])).convert("L")).copy()
            if file_sha256(self._path(job["artifacts"]["allowed_mask"]))!=job["mask_preflight"]["allowed_sha256"] or file_sha256(self._path(job["artifacts"]["protect_mask"]))!=job["mask_preflight"]["protect_sha256"]:
                raise StudioError("Maski zadania zostały zmienione po przygotowaniu.")
            if job["operation"]=="color":
                self._stage(job_id,"color_adjustment",35)
                brightness=_finite(settings.get("brightness",1),"brightness",.05,5)
                saturation=_finite(settings.get("saturation",1),"saturation",0,3)
                desired=np.asarray(ImageEnhance.Color(ImageEnhance.Brightness(Image.fromarray(base)).enhance(brightness)).enhance(saturation)).copy()
                tint=_finite(settings.get("tint",0),"tint",-.3,.3)
                warmth=_finite(settings.get("warmth",0),"warmth",-.3,.3)
                if tint or warmth:
                    # Deterministic local color cast correction in linear sRGB.
                    # Negative tint removes magenta; positive warmth raises red
                    # relative to blue. The ordinary allowed/protect masks apply.
                    normalized=desired.astype(np.float32)/255
                    linear=np.where(normalized<=.04045,normalized/12.92,((normalized+.055)/1.055)**2.4)
                    gains=np.exp(np.array([tint/2+warmth,-tint,tint/2-warmth],dtype=np.float32))
                    linear=np.clip(linear*gains,0,1)
                    adjusted=np.where(linear<=.0031308,linear*12.92,1.055*linear**(1/2.4)-.055)
                    desired=np.clip(np.rint(adjusted*255),0,255).astype(np.uint8)
            else:
                self._stage(job_id,"generating_pro_high",25)
                desired=self._generate(job,base,allowed,settings,folder)
            result=_linear_blend(base,desired,allowed)
            result[protected>0]=base[protected>0]
            _save_rgb(folder/"prepared_result.png",result)
            compositor=settings.get("compositor","local")
            if compositor=="comfy":
                self._stage(job_id,"comfy_composition",65)
                result=self._comfy(job,base,result,allowed,protected,settings,folder)
            elif compositor!="local":raise StudioError("Nieobsługiwany compositor.")
            self._stage(job_id,"technical_qa",85)
            revision=self._finish_candidate(job,result,base,allowed,protected,folder,compositor)
            return self._stage(job_id,"completed",100,status="completed",result_revision_id=revision["id"],completed_at=utc_now())
        except _UnknownProviderOutcome as error:
            return self._stage(job_id,"provider_outcome_unknown",25,status="unknown",error=str(error))
        except Exception as error:
            return self._stage(job_id,"failed",0,status="failed",error=str(_redact(str(error))))

    def _generate(self,job,base,allowed,settings,folder):
        output=folder/"provider_output.png"
        receipt_path=folder/"provider_receipt.json"
        box=job["artifacts"]["crop_box"];l,t,r,b=box
        if output.is_file() and receipt_path.is_file():
            receipt=_json_read(receipt_path)
            if file_sha256(output)!=receipt["output_sha256"]:raise StudioError("Zmieniony zachowany wynik modelu.")
        else:
            budget=self._load()
            if budget.get("api_calls_used",0)>=int(budget["settings"].get("max_paid_calls",3)):
                raise StudioError("Osiągnięto limit płatnych generacji projektu.")
            key=_api_key()
            config={"responseModalities":["TEXT","IMAGE"],"thinkingConfig":{"thinkingLevel":"HIGH"},"imageConfig":{"imageSize":settings.get("image_size","2K")}}
            crop=Image.fromarray(base).crop(box)
            ratios={"1:1":1,"2:3":2/3,"3:2":3/2,"3:4":3/4,"4:3":4/3,"4:5":4/5,"5:4":5/4,"9:16":9/16,"16:9":16/9,"21:9":21/9}
            aspect=min(ratios,key=lambda a:abs(math.log(crop.width/crop.height/ratios[a])))
            config["imageConfig"]["aspectRatio"]=aspect
            ratio=ratios[aspect];pw=max(crop.width,math.ceil(crop.height*ratio));ph=max(crop.height,math.ceil(crop.width/ratio))
            padded=np.pad(np.asarray(crop),((0,ph-crop.height),(0,pw-crop.width),(0,0)),mode="edge")
            target=folder/"provider_target.png";_save_rgb(target,padded)
            guide=padded.copy();local=allowed[t:b,l:r]>0
            guide[:b-t,:r-l][local]=(guide[:b-t,:r-l][local]*.4+np.array([0,210,230])*.6).astype(np.uint8)
            gp=folder/"provider_guide.png";_save_rgb(gp,guide)
            instructions=str(settings.get("prompt") or " ".join(a.get("comment","") for a in job["annotations"] if a.get("role","edit")=="edit")).strip()
            if not instructions:raise StudioError("Opisz poprawkę przed uruchomieniem generacji.")
            purpose={"edge":"Repair only the selected boundary/contact between the existing objects. Reconstruct a physically plausible continuous silhouette, fine natural antialiasing, original material grain and correct contact shadow. Do not merely blur or smear the edge. Preserve the exact shapes and design on both sides.",
                     "people":"Replace only the selected people with clearly different photorealistic adult identities, hair and clothing. Keep believable scale, pose, contact points and scene lighting. Preserve explicitly protected people and stroller/furniture parts.",
                     "local":"Make only the requested local architectural edit, preserving all surrounding accepted design."}[job["operation"]]
            prompt=("IMAGE1 is the exact original native architectural-image crop. IMAGE2 is only a cyan selection-location guide, never a style reference. "+purpose+" User request: "+instructions+
                    " Return one clean image matching IMAGE1 framing, dimensions, camera and illumination. No magenta/pink fringe, invented outlines, text, graphic guides, collage or new unrequested objects. All unselected material, accepted people, reflections and architecture must remain unchanged. A broad crop provides context; only the narrow selected pixels will be used. Keep the full context aligned with the original.")
            request_manifest={"model":MODEL,"generationConfig":config,"prompt":prompt,"crop_box":box,"padded_size":[pw,ph],"input_sha256":{target.name:file_sha256(target),gp.name:file_sha256(gp)},"parent_sha256":job["parent_sha256"]}
            _atomic_json(folder/"provider_request.json",_redact(request_manifest))
            meta_url="https://generativelanguage.googleapis.com/v1beta/models/"+MODEL
            with urllib.request.urlopen(urllib.request.Request(meta_url,headers={"x-goog-api-key":key}),timeout=30) as response:
                _atomic_json(folder/"model_metadata.json",json.load(response))
            with self._write_lock():
                project=self._load();limit=int(project["settings"].get("max_paid_calls",3))
                if project.get("api_calls_used",0)>=limit:raise StudioError("Osiągnięto limit płatnych generacji projektu.")
                project["api_calls_used"]=project.get("api_calls_used",0)+1
                self._job(project,job["id"])["paid_call_reserved_at"]=utc_now();self._save(project,{"type":"paid_call_reserved","job_id":job["id"]})
            parts=[{"text":prompt}]+[{"inlineData":{"mimeType":"image/png","data":base64.b64encode(x.read_bytes()).decode("ascii")}} for x in [target,gp]]
            request=urllib.request.Request(meta_url+":generateContent",data=json.dumps({"contents":[{"role":"user","parts":parts}],"generationConfig":config}).encode(),headers={"Content-Type":"application/json","x-goog-api-key":key},method="POST")
            started=time.monotonic()
            try:
                with urllib.request.urlopen(request,timeout=420) as response:data=json.load(response)
            except urllib.error.HTTPError as error:
                # HTTP response is a known failure; never include credential headers.
                detail=error.read(3000).decode("utf-8",errors="replace")
                _atomic_json(folder/"provider_error.json",{"http_status":error.code,"message":_redact(detail)})
                raise StudioError("Gemini HTTP%d: zobacz provider_error.json." % error.code) from None
            except (urllib.error.URLError,TimeoutError,ConnectionError,OSError):
                raise _UnknownProviderOutcome("Po wysłaniu żądania utracono odpowiedź modelu. Wynik/rozliczenie są nieznane; zadanie nie zostanie automatycznie powtórzone.") from None
            images=[];thought_skipped=0
            for candidate in data.get("candidates",[]):
                for part in candidate.get("content",{}).get("parts",[]):
                    if part.get("thought"):thought_skipped+=1;continue
                    inline=part.get("inlineData",{})
                    if inline.get("mimeType","").startswith("image/"):
                        images.append(base64.b64decode(inline["data"]))
            if not images:
                _atomic_json(folder/"provider_no_image.json",_redact({k:v for k,v in data.items() if k!="candidates"}))
                raise StudioError("Model nie zwrócił końcowego obrazu. Nie wykonano automatycznej ponownej generacji.")
            with Image.open(io.BytesIO(images[-1])) as image:image.convert("RGB").save(output,icc_profile=_srgb())
            receipt={"model":MODEL,"model_version":data.get("modelVersion"),"generationConfig":config,"usage":data.get("usageMetadata"),"response_id":data.get("responseId"),"elapsed_seconds":round(time.monotonic()-started,3),"thought_images_skipped":thought_skipped,"output_sha256":file_sha256(output),"padded_size":[pw,ph],"crop_box":box,"created_at":utc_now()}
            _atomic_json(receipt_path,receipt)
        receipt=_json_read(receipt_path);native=Image.open(output).convert("RGB").resize(tuple(receipt["padded_size"]),Image.Resampling.LANCZOS).crop((0,0,r-l,b-t))
        desired=base.copy();desired[t:b,l:r]=np.asarray(native)
        self._stage(job["id"],"generated",55,receipt=receipt)
        return desired

    @staticmethod
    def _http_json(url,data=None,timeout=45):
        request=urllib.request.Request(url,data=None if data is None else json.dumps(data).encode(),headers={"Content-Type":"application/json"})
        with urllib.request.urlopen(request,timeout=timeout) as response:return json.load(response)

    @staticmethod
    def _upload_comfy(api,path,subfolder):
        boundary="----Archviz"+uuid.uuid4().hex
        fields=[]
        for name,value in [("type","input"),("overwrite","false"),("subfolder",subfolder)]:
            fields.append(("--%s\r\nContent-Disposition: form-data; name=\"%s\"\r\n\r\n%s\r\n"%(boundary,name,value)).encode())
        fields.append(("--%s\r\nContent-Disposition: form-data; name=\"image\"; filename=\"%s\"\r\nContent-Type: image/png\r\n\r\n"%(boundary,Path(path).name)).encode()+Path(path).read_bytes()+b"\r\n")
        body=b"".join(fields)+("--%s--\r\n"%boundary).encode()
        req=urllib.request.Request(api+"/upload/image",data=body,headers={"Content-Type":"multipart/form-data; boundary="+boundary})
        with urllib.request.urlopen(req,timeout=90) as response:value=json.load(response)
        return "/".join(x for x in [value.get("subfolder",""),value["name"]] if x)

    def _comfy(self,job,base,result,allowed,protected,settings,folder):
        api=str(settings.get("comfy_url","")).rstrip("/")
        parsed=urllib.parse.urlparse(api)
        if parsed.scheme not in {"http","https"} or not parsed.netloc or parsed.username or parsed.query or parsed.fragment:
            raise StudioError("Niepoprawny adres ComfyUI.")
        stats=self._http_json(api+"/system_stats");_atomic_json(folder/"comfy_system_stats.json",stats)
        # Linear composition already produced the exact expected image. Comfy
        # copyback is restricted by the same binary support, not a second feather.
        _save_rgb(folder/"comfy_base.png",base);_save_rgb(folder/"comfy_prepared.png",result)
        Image.fromarray((allowed>0).astype(np.uint8)*255).save(folder/"comfy_support.png")
        subfolder="archviz_studio/"+job["id"]
        sources=[self._upload_comfy(api,folder/name,subfolder) for name in ["comfy_base.png","comfy_prepared.png","comfy_support.png"]]
        nodes={"1":{"class_type":"LoadImage","inputs":{"image":sources[0]}},"2":{"class_type":"LoadImage","inputs":{"image":sources[1]}},"3":{"class_type":"LoadImageMask","inputs":{"image":sources[2],"channel":"red"}},"4":{"class_type":"ImageCompositeMasked","inputs":{"destination":["1",0],"source":["2",0],"mask":["3",0],"x":0,"y":0,"resize_source":False}},"5":{"class_type":"SaveImage","inputs":{"images":["4",0],"filename_prefix":subfolder+"/result"}}}
        _atomic_json(folder/"comfy_workflow.json",nodes)
        response=self._http_json(api+"/prompt",{"prompt":nodes,"client_id":uuid.uuid4().hex});_atomic_json(folder/"comfy_submission.json",response)
        if "prompt_id" not in response:raise StudioError("ComfyUI odrzucił workflow.")
        pid=response["prompt_id"];deadline=time.monotonic()+360
        while time.monotonic()<deadline:
            history=self._http_json(api+"/history/"+pid)
            if pid in history:break
            time.sleep(.5)
        else:raise StudioError("Przekroczony czas kompozycji Comfy; generacja jest zachowana do wznowienia.")
        history=history[pid];_atomic_json(folder/"comfy_history.json",history)
        if history.get("status",{}).get("status_str")!="success":raise StudioError("ComfyUI nie zakończył kompozycji.")
        image=history["outputs"]["5"]["images"][0];q=urllib.parse.urlencode({k:image[k] for k in ["filename","subfolder","type"]})
        with urllib.request.urlopen(api+"/view?"+q,timeout=90) as response:(folder/"comfy_raw.png").write_bytes(response.read())
        actual=np.asarray(Image.open(folder/"comfy_raw.png").convert("RGB")).copy()
        if actual.shape!=result.shape or np.max(np.abs(actual.astype(np.int16)-result.astype(np.int16)))>1:
            raise StudioError("Rzeczywisty wynik Comfy nie odpowiada przygotowanemu obrazowi.")
        actual[(allowed==0)|(protected>0)]=base[(allowed==0)|(protected>0)]
        return actual

    def _finish_candidate(self,job,result,base,allowed,protected,folder,compositor="local"):
        changed=np.any(result!=base,axis=2);outside=int((changed&(allowed==0)).sum());guard=int((changed&(protected>0)).sum())
        if outside or guard:raise StudioError("Zmiana poza maską albo w chronionym obszarze blokuje wynik.")
        rid=uuid.uuid4().hex;target=self.work_dir/"frames"/job["frame_id"]/"revisions"/rid/"result.png"
        _save_rgb(target,result)
        with Image.open(target) as readback:
            readback.load()
            if readback.size!=(base.shape[1],base.shape[0]) or readback.mode!="RGB" or not readback.info.get("icc_profile"):
                raise StudioError("Niepoprawny format końcowego PNG.")
            if not np.array_equal(np.asarray(readback),result):raise StudioError("PNG nie odpowiada kompozycji.")
        qa={"technical_status":"PASS","visual_status":"PENDING","width":base.shape[1],"height":base.shape[0],"changed_pixels":int(changed.sum()),"outside_changed_pixels":outside,"outside_allowed_changed_pixels":outside,"protected_changed_pixels":guard,"allowed_protected_overlap_pixels":int(((allowed>0)&(protected>0)).sum()),"compositor":compositor,"warnings":[] if changed.any() else ["Wynik nie zawiera zmienionych pikseli."],"checked_at":utc_now()}
        revision={"id":rid,"parent_id":job["parent_revision_id"],"image_path":self._rel(target),"sha256":file_sha256(target),"status":"candidate","annotations":[deepcopy(a) for a in job.get("annotations",[]) if a.get("role","edit")!="edit"],"qa":qa,"created_at":utc_now(),"job_id":job["id"],"operation":job["operation"]}
        _atomic_json(folder/"technical_qa.json",{**qa,"result_sha256":revision["sha256"]})
        # Immutable visual evidence includes a full preview and exact native crops.
        full=Image.fromarray(result);full.thumbnail((1600,1000));full.save(folder/"review_full.png")
        box=job["artifacts"]["crop_box"];Image.fromarray(base).crop(box).save(folder/"review_before_native.png");Image.fromarray(result).crop(box).save(folder/"review_after_native.png")
        with self._write_lock():
            p=self._load();parent,_=self._verified_revision(p,job["frame_id"],job["parent_revision_id"])
            if parent["sha256"]!=job["parent_sha256"]:raise StudioError("Baza zmieniła się podczas zadania.")
            frame=self._frame(p,job["frame_id"]);frame["revisions"].append(revision);frame["active_revision_id"]=rid
            # Commit the candidate and its completed job in one manifest write:
            # a crash between this point and the sidecar update cannot cause a
            # resumed job to create a duplicate version or repeat a paid call.
            self._job(p,job["id"]).update(status="completed",stage="completed",progress=100,
                                        result_revision_id=rid,completed_at=utc_now())
            self._save(p,{"type":"candidate_created","job_id":job["id"],"revision_id":rid,"sha256":revision["sha256"]})
        return revision

    def approve(self,frame_id,revision_id):
        with self._write_lock():
            p=self._load();revision,_=self._verified_revision(p,frame_id,revision_id)
            if revision.get("qa",{}).get("technical_status")!="PASS":raise StudioError("Wersja nie przeszła kontroli technicznej.")
            if revision["status"]=="rejected":raise StudioError("Odrzucona wersja nie może zostać zatwierdzona.")
            revision["status"]="approved";revision["approved_at"]=utc_now();revision["approval_actor"]="human"
            revision["qa"]["visual_status"]="USER_APPROVED"
            frame=self._frame(p,frame_id);frame["approved_revision_id"]=revision_id;frame["active_revision_id"]=revision_id
            self._save(p,{"type":"user_approved","frame_id":frame_id,"revision_id":revision_id})
            return deepcopy(p)

    def reject(self,frame_id,revision_id):
        with self._write_lock():
            p=self._load();revision,_=self._verified_revision(p,frame_id,revision_id)
            if revision["status"]=="approved":raise StudioError("Zatwierdzona wersja pozostaje w historii. Odrzuć nowego kandydata.")
            revision["status"]="rejected";revision["rejected_at"]=utc_now()
            frame=self._frame(p,frame_id)
            if frame["active_revision_id"]==revision_id:frame["active_revision_id"]=frame.get("approved_revision_id") or revision.get("parent_id") or revision_id
            self._save(p,{"type":"revision_rejected","frame_id":frame_id,"revision_id":revision_id})
            return deepcopy(p)

    def export_approved(self,frame_ids=None):
        with self._write_lock():
            p=self._load();output=Path(p["output_dir"]).resolve();self._validate_folders(self.work_dir,p["input_dirs"],output)
            selected=[self._frame(p,fid) for fid in frame_ids] if frame_ids is not None else [f for f in p["frames"] if f.get("approved_revision_id")]
            if not selected:raise StudioError("Brak zatwierdzonych kadrów do eksportu.")
            names={};items=[]
            # Detect collisions before any output is created or replaced.
            for frame in p["frames"]:
                name=_safe_name(frame["export_name"]);key=name.casefold()
                if key in names:raise StudioError("Kolizja nazw eksportu: "+name)
                names[key]=frame["id"]
                if _within(frame["source_path"],output):raise StudioError("Output zawiera plik źródłowy.")
            for frame in selected:
                rid=frame.get("approved_revision_id")
                if not rid:raise StudioError("Wybrany kadr nie jest zatwierdzony.")
                revision,path=self._verified_revision(p,frame["id"],rid)
                if revision["status"]!="approved" or revision.get("approval_actor")!="human":raise StudioError("Eksport wymaga jawnej akceptacji użytkownika.")
                destination=output/frame["export_name"]
                if destination.exists() and not destination.is_file():
                    raise StudioError("Cel eksportu nie jest plikiem: "+destination.name)
                items.append((frame,revision,path))
            export_id=uuid.uuid4().hex;staging=self.work_dir/"exports"/export_id;staging.mkdir(parents=True,exist_ok=False)
            staged=[]
            for frame,revision,path in items:
                cached=path.parent/"approved_export.jpg";cachemeta=path.parent/"approved_export.json"
                if cached.exists() or cachemeta.exists():
                    if not cached.is_file() or not cachemeta.is_file():raise StudioError("Niekompletny cache JPG zatwierdzonej wersji.")
                    cm=_json_read(cachemeta)
                    if cm.get("png_sha256")!=revision["sha256"] or file_sha256(cached)!=cm.get("jpg_sha256"):
                        raise StudioError("Zmieniono cache JPG zatwierdzonej wersji.")
                else:
                    with Image.open(path) as im:
                        im.convert("RGB").save(cached,quality=97,subsampling=0,icc_profile=im.info.get("icc_profile") or _srgb())
                    _atomic_json(cachemeta,{"png_sha256":revision["sha256"],"jpg_sha256":file_sha256(cached),"created_at":utc_now(),"quality":97,"subsampling":0})
                jpg=staging/frame["export_name"];shutil.copyfile(cached,jpg)
                with Image.open(jpg) as im:im.load();assert im.mode=="RGB"
                staged.append((frame,revision,jpg,file_sha256(jpg)))
            output.mkdir(parents=True,exist_ok=True);records=[]
            for frame,revision,jpg,sha in staged:
                dest=output/frame["export_name"]
                if dest.parent.resolve()!=output:raise StudioError("Niepoprawna ścieżka eksportu.")
                backup=None
                unchanged=dest.is_file() and file_sha256(dest)==sha
                if dest.exists() and not dest.is_file():raise StudioError("Cel eksportu nie jest plikiem: "+dest.name)
                if dest.exists() and not unchanged:
                    bp=staging/"previous"/dest.name;bp.parent.mkdir(exist_ok=True);shutil.copyfile(dest,bp)
                    if file_sha256(bp)!=file_sha256(dest):raise StudioError("Nie udało się sprawdzić kopii poprzedniej dostawy.")
                    backup={"path":self._rel(bp),"sha256":file_sha256(bp)}
                if not unchanged:
                    tmp=output/("."+dest.name+"."+export_id+".tmp")
                    try:
                        shutil.copyfile(jpg,tmp)
                        if file_sha256(tmp)!=sha:raise StudioError("Błąd kopii JPG.")
                        os.replace(tmp,dest)
                    finally:tmp.unlink(missing_ok=True)
                if file_sha256(dest)!=sha:raise StudioError("Błąd odczytu dostarczonego JPG.")
                with Image.open(dest) as im:im.load();dimensions=list(im.size)
                records.append({"frame_id":frame["id"],"revision_id":revision["id"],"png_sha256":revision["sha256"],"path":str(dest),"sha256":sha,"dimensions":dimensions,"previous":backup,"unchanged":unchanged})
            receipt={"id":export_id,"status":"VERIFIED","created_at":utc_now(),"files":records}
            _atomic_json(staging/"receipt.json",receipt);p["exports"].append(receipt);self._save(p,{"type":"approved_export","export_id":export_id})
            return deepcopy(receipt)

    def export_repair_kit(self,frame_id,revision_id,annotations=None):
        with self._write_lock():
            p=self._load();revision,path=self._verified_revision(p,frame_id,revision_id)
            anns=deepcopy(revision["annotations"] if annotations is None else annotations)
            image=Image.open(path).convert("RGB");allowed,protected=rasterize_annotations(image.size,anns,"edge",p["settings"].get("edge_width",12))
            ys,xs=np.nonzero(allowed)
            if not len(xs):raise StudioError("Zaznacz krawędź do poprawy w Photoshopie.")
            pad=int(p["settings"].get("context_px",128));box=[max(0,int(xs.min())-pad),max(0,int(ys.min())-pad),min(image.width,int(xs.max())+pad+1),min(image.height,int(ys.max())+pad+1)]
            kid=uuid.uuid4().hex;folder=self.work_dir/"repair_kits"/kid;folder.mkdir(parents=True,exist_ok=False)
            target=folder/"target.png";mp=folder/"mask.png";image.crop(box).save(target,icc_profile=_srgb())
            Image.fromarray(allowed).crop(box).save(mp);Image.fromarray(allowed).save(folder/"allowed_full.png");Image.fromarray(protected).save(folder/"protect_full.png")
            overlay=np.asarray(image).copy();sel=allowed>0;overlay[sel]=(overlay[sel]*.4+np.array([0,210,230])*.6).astype(np.uint8);Image.fromarray(overlay).crop(box).save(folder/"selection_preview.png")
            manifest={"schema_version":1,"id":kid,"project_id":p["id"],"frame_id":frame_id,"revision_id":revision_id,"parent_sha256":revision["sha256"],"native_size":list(image.size),"crop_box":box,"crop_size":[box[2]-box[0],box[3]-box[1]],"annotations":anns,"created_at":utc_now(),"files":{name:file_sha256(folder/name) for name in ["target.png","mask.png","allowed_full.png","protect_full.png"]}}
            _atomic_json(folder/"manifest.json",manifest)
            (folder/"README.txt").write_text("Photoshop / Firefly — naprawa krawędzi\n\n1. Otwórz target.png.\n2. Wczytaj mask.png jako zaznaczenie (białe = poprawka).\n3. Popraw wyłącznie zaznaczoną krawędź, zachowując materiały i geometrię.\n4. Zachowaj dokładny rozmiar płótna i zapisz RGB jako edited.png.\n5. W Archviz Studio wybierz Importuj poprawkę.\n\nProgram przywróci wszystkie piksele poza maską i chronione fragmenty. Import tworzy nową, niezatwierdzoną wersję. Nie zmieniaj mask.png ani manifest.json.\n",encoding="utf-8")
            value={"kit_path":str(folder),"target_path":str(target),"mask_path":str(mp),"manifest_path":str(folder/"manifest.json"),"manifest_sha256":file_sha256(folder/"manifest.json"),"suggested_result_path":str(folder/"edited.png"),"id":kid,"frame_id":frame_id,"revision_id":revision_id}
            p["repair_kits"].append(value);self._save(p,{"type":"repair_kit_created","kit_id":kid})
            return value

    def import_repair(self,frame_id,revision_id,kit_path,result_path):
        kit=Path(kit_path).expanduser().resolve()
        if kit.is_file():kit=kit.parent
        if not _within(kit,self.work_dir/"repair_kits"):raise StudioError("Repair-kit musi należeć do tego projektu.")
        m=_json_read(kit/"manifest.json");p=self._load();revision,path=self._verified_revision(p,frame_id,revision_id)
        registered=next((x for x in p.get("repair_kits",[]) if x.get("id")==m.get("id")),None)
        if not registered or registered.get("manifest_sha256")!=file_sha256(kit/"manifest.json"):
            raise StudioError("Manifest repair-kitu został zmieniony albo nie należy do tego projektu.")
        if (m.get("project_id"),m.get("frame_id"),m.get("revision_id"),m.get("parent_sha256"))!=(p["id"],frame_id,revision_id,revision["sha256"]):
            raise StudioError("Repair-kit dotyczy innego obrazu albo wersji.")
        for name,sha in m["files"].items():
            if Path(name).name!=name or file_sha256(kit/name)!=sha:raise StudioError("Zmieniono pliki lub maskę repair-kitu.")
        rp=Path(result_path).expanduser().resolve()
        external=_load_rgb(rp);base=np.asarray(Image.open(path).convert("RGB")).copy();desired=base.copy();l,t,r,b=m["crop_box"]
        if list(external.size)==m["crop_size"]:desired[t:b,l:r]=np.asarray(external)
        elif list(external.size)==m["native_size"]:desired=np.asarray(external).copy()
        else:raise StudioError("Rozmiar poprawki różni się od oryginalnego wycinka/płótna. Import zablokowany.")
        allowed=np.asarray(Image.open(kit/"allowed_full.png").convert("L")).copy();protected=np.asarray(Image.open(kit/"protect_full.png").convert("L")).copy()
        result=_linear_blend(base,desired,allowed);result[protected>0]=base[protected>0]
        jid=uuid.uuid4().hex;folder=self.work_dir/"jobs"/jid;folder.mkdir(parents=True,exist_ok=False)
        job={"id":jid,"frame_id":frame_id,"parent_revision_id":revision_id,"parent_sha256":revision["sha256"],"operation":"external","annotations":m["annotations"],"status":"running","stage":"importing_repair","progress":50,"created_at":utc_now(),"error":None,"options":{},"artifacts":{"crop_box":m["crop_box"],"external_source":str(rp),"external_sha256":file_sha256(rp),"kit_id":m["id"]}}
        with self._write_lock():
            p=self._load();p["jobs"].append(job);self._save(p,{"type":"external_repair_import","job_id":jid})
        try:
            candidate=self._finish_candidate(job,result,base,allowed,protected,folder,"external_import")
            self._stage(jid,"completed",100,status="completed",result_revision_id=candidate["id"],completed_at=utc_now())
            return candidate
        except Exception as error:
            self._stage(jid,"failed",0,status="failed",error=str(error));raise

    def diagnostics(self,destination=None):
        p=self.snapshot();folder=Path(destination).expanduser().resolve() if destination else self.work_dir/"diagnostics"
        if _within(folder,p["output_dir"]):raise StudioError("Diagnostyka nie może trafić do folderu dostawy.")
        folder.mkdir(parents=True,exist_ok=True);target=folder/("archviz-diagnostics-"+uuid.uuid4().hex+".zip")
        total_bytes=0;included=[];limit=120_000_000
        with zipfile.ZipFile(target,"x",zipfile.ZIP_DEFLATED) as z:
            def artifact(path,arcname):
                nonlocal total_bytes
                if not path.is_file():return
                size=path.stat().st_size
                row={"path":arcname,"source_sha256":file_sha256(path),"size_bytes":size}
                if size>30_000_000 or total_bytes+size>limit:
                    included.append({**row,"included":False,"reason":"diagnostic_size_cap"});return
                z.write(path,arcname);total_bytes+=size;included.append({**row,"included":True})
            z.writestr("project.json",json.dumps(_redact(p),ensure_ascii=False,indent=2))
            z.writestr("README_CODEX.txt","Archviz Studio diagnostic bundle.\nRead project.json, jobs/*/job.json and technical_qa.json.\nInput images/revisions remain immutable. Human approval is separate from technical PASS.\nUse the same StudioProject/CLI/API; do not edit approved output directly.\nDo not blindly retry paid jobs with unknown outcome.\n")
            events=self.work_dir/"events.jsonl"
            if events.exists():z.writestr("events.jsonl",str(_redact(events.read_text(encoding="utf-8"))))
            for job in reversed(p["jobs"][-10:]):
                jf=self.work_dir/"jobs"/job["id"]
                for name in ["job.json","technical_qa.json","provider_request.json","provider_receipt.json","provider_error.json","model_metadata.json","comfy_workflow.json","comfy_history.json"]:
                    path=jf/name
                    if path.is_file():z.writestr("jobs/"+job["id"]+"/"+name,json.dumps(_redact(_json_read(path)),ensure_ascii=False,indent=2))
                for name in ["allowed_mask.png","protect_mask.png","context.png","review_full.png","review_before_native.png","review_after_native.png"]:
                    path=jf/name
                    artifact(path,"jobs/"+job["id"]+"/"+name)
                mask_review=jf/"mask_review.png"
                if mask_review.is_file() and total_bytes<limit:
                    with Image.open(mask_review) as im:
                        preview=im.convert("RGB");preview.thumbnail((1600,1000));buf=io.BytesIO();preview.save(buf,format="PNG")
                    content=buf.getvalue()
                    if total_bytes+len(content)<=limit:
                        z.writestr("jobs/"+job["id"]+"/mask_review_preview.png",content);total_bytes+=len(content)
            z.writestr("repair_kit_links.json",json.dumps(_redact(p.get("repair_kits",[])),ensure_ascii=False,indent=2))
            for kit in reversed(p.get("repair_kits",[])[-2:]):
                kf=Path(kit["kit_path"])
                if not _within(kf,self.work_dir/"repair_kits"):continue
                for name in ["target.png","mask.png","selection_preview.png"]:
                    artifact(kf/name,"repair_kits/"+kit["id"]+"/"+name)
                if (kf/"manifest.json").is_file():z.writestr("repair_kits/"+kit["id"]+"/manifest.json",json.dumps(_redact(_json_read(kf/"manifest.json")),ensure_ascii=False,indent=2))
            z.writestr("included_artifacts.json",json.dumps({"uncompressed_artifact_limit":limit,"included_bytes":total_bytes,"files":included},ensure_ascii=False,indent=2))
        return {"path":str(target),"sha256":file_sha256(target),"size_bytes":target.stat().st_size,"redacted":True,"uncompressed_artifact_bytes":total_bytes}
