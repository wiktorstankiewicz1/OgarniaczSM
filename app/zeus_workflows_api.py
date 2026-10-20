"""HTTP client for render workflows processed by Zeus."""

import json
import mimetypes
import os
import shutil
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


API_URL = os.environ.get(
    "OGARNIACZ_ZEUS_API",
    "https://zeus.tailf131eb.ts.net/ogarniacz-api/v1",
).rstrip("/")


def _error_message(error: urllib.error.HTTPError) -> str:
    try:
        payload = json.loads(error.read().decode("utf-8"))
        return str(payload.get("error") or payload)
    except Exception:
        return "Zeus returned HTTP %s" % error.code


def _json_request(path: str, timeout: int = 15) -> dict:
    request = urllib.request.Request(API_URL + path, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        raise RuntimeError(_error_message(error)) from error
    except urllib.error.URLError as error:
        raise RuntimeError("Cannot reach Zeus: %s" % error.reason) from error


def get_catalog() -> dict:
    return _json_request("/render-workflows")


def get_jobs(limit: int = 40) -> list[dict]:
    data = _json_request("/render-jobs?limit=%d" % max(1, min(100, limit)))
    return data.get("jobs", [])


def submit_image(workflow_id: str, image_path: str) -> dict:
    source = Path(image_path)
    content_type = mimetypes.guess_type(source.name)[0] or "application/octet-stream"
    headers = {
        "Content-Type": content_type,
        "X-File-Name": urllib.parse.quote(source.name),
        "Accept": "application/json",
    }
    request = urllib.request.Request(
        API_URL + "/render-workflows/%s/jobs" % urllib.parse.quote(workflow_id),
        data=source.read_bytes(),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            return json.loads(response.read().decode("utf-8"))["job"]
    except urllib.error.HTTPError as error:
        raise RuntimeError(_error_message(error)) from error
    except urllib.error.URLError as error:
        raise RuntimeError("Upload to Zeus failed: %s" % error.reason) from error


def download_result(job_id: str, destination: str) -> str:
    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".part")
    request = urllib.request.Request(
        API_URL + "/render-jobs/%s/result" % urllib.parse.quote(job_id),
        headers={"Accept": "image/*"},
    )
    try:
        with urllib.request.urlopen(request, timeout=180) as response, temporary.open("wb") as output:
            shutil.copyfileobj(response, output)
        temporary.replace(target)
        return str(target)
    except urllib.error.HTTPError as error:
        temporary.unlink(missing_ok=True)
        raise RuntimeError(_error_message(error)) from error
    except urllib.error.URLError as error:
        temporary.unlink(missing_ok=True)
        raise RuntimeError("Download from Zeus failed: %s" % error.reason) from error

