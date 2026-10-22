# Archviz Studio first working version — shared implementation contract

Working tree: `C:/Users/wikto/source/worktrees/OgarniaczSM-archviz-studio`.
Use original repository `.venv/Scripts/python.exe`; no deployment/install/update.
Python flat modules and colocated same-basename icons, per AGENTS.md.
Do not alter any approved Elektrovnia source or delivery files. Pilot uses its
own work/output directories under `codex_test_poprawek/_archviz_studio_pilot`.

## Ownership

- core agent: `app/archviz_core.py`, matching icon, backend docs if needed.
- canvas agent: `app/archviz_studio.html` only.
- QA agent: tests and independent actual-image/GUI QA, no production core/UI.
- root: `archviz_server.py`, `archviz_cli.py`, `archviz_studio_widget.py`, icons,
  main.py/config integration, docs, startup and live service verification.

## Core interface (root service calls these)

`StudioProject(work_dir)` opens an existing project, no implicit writes.
`StudioProject.create(name, work_dir, input_dirs, output_dir)` creates/returns it.

Methods:

- `snapshot()` -> project dict, including frames and jobs below.
- `update_settings(**values)` -> snapshot (also name/input_dirs/output_dir).
- `import_images(paths)` -> snapshot. Each item a path string or dict
  `{path, export_name?, name?}`; freezes originals and lossless native baseline.
- `save_annotations(frame_id, revision_id, annotations, source_sha256=None)`
  -> revision; rejects stale image hashes.
- `create_job(frame_id, revision_id, operation, annotations=None, options=None)`
  -> queued job dict. No network until `run_job(job_id)`.
- `run_job(job_id)` -> job dict; persists phases/errors and immutable candidate.
- `get_job(job_id)`, `get_revision(frame_id, revision_id)` -> dict.
- `image_path(frame_id, revision_id)` -> Path.
- `approve(frame_id, revision_id)` -> snapshot. Explicit human action only;
  block technical failure, distinguish visual review/user approval.
- `reject(frame_id, revision_id)` -> snapshot.
- `export_approved(frame_ids=None)` -> export receipt. JPG only with original
  basename; atomic replace, prior backup outside output, size/hash read-back,
  reject output/input overlap and basename collisions before any export.
- `diagnostics(destination=None)` -> dict containing path; redact credentials.
- `export_repair_kit(frame_id, revision_id, annotations=None)` -> dict with
  `kit_path`, `target_path`, `mask_path`, `manifest_path`, `suggested_result_path`.
- `import_repair(frame_id, revision_id, kit_path, result_path)` -> revision.
  Must validate parent hash, exact crop/native dimensions, protected pixels,
  use kit mask only, and create an unapproved candidate with technical QA.

## JSON schema

Project: `schema_version:1`, `id`, `name`, `work_dir`, `input_dirs`, `output_dir`,
`settings`, `frames:[]`, `jobs:[]`. JSON paths may be relative inside work;
core resolves them through image_path. Atomic JSON and interprocess writer
protection; no SQLite/WAL on Y: share. Validate traversal and dangerous overlap.

Frame: `id`, `name`, `source_path`, `export_name`, `active_revision_id`,
`approved_revision_id` (null initially), `revisions:[]`.

Revision: `id`, `parent_id`, `image_path`, `sha256`, `status`
(`source|candidate|approved|rejected`), `annotations:[]`, `qa`, `created_at`.
User annotations remain attached to the exact immutable revision image.

Job: `id`, `frame_id`, `parent_revision_id`, `operation`, `status`
(`queued|running|completed|failed|unknown|cancelled`), `stage`, `progress`, `error`,
`result_revision_id` (if completed). Unknown paid-call outcome never blindly retries.

Annotation: `id`, `number`, `type` (`pen|rectangle|polygon`), `points:[[x,y],...]`
in original pixels, `bounds:[left,top,right,bottom]`, `width` (native px),
`role` (`edit|protect`), `comment`, `color`. For rectangle use bounds. `edge`
operation uses drawn pen/outline as a narrow repair band, not the bounding box.
Protection includes explicitly marked foreground/background/people/AA.

Options: `prompt`, `context_px` (default128), `edge_width` (default12),
`brightness` (default1.0), `saturation` (default1.0), `tint`/`warmth` (default0,
range -0.3..0.3, negative tint removes magenta, positive warmth raises red), `provider`,
`compositor` (`local|comfy`), `comfy_url` (configured, default18188 for pilot).
Operations: `color` deterministic, `edge|people|local` actual Gemini Pro.
Existing explicitly authorized Windows User GEMINI_API_KEY, never store key.
Actual model `gemini-3-pro-image`, explicit HIGH, 2K, skip thought-image parts,
archive real config/model/usage. Missing provider never masquerades as AI.
Limited paid calls (project default3), no unlimited repair loops. Context crop
can be broad; copyback only narrow allowed mask minus hard protection. Linear
sRGB blend, keep native resolution/ICC and prove zero changes outside mask.

## HTTP interface root provides

GET `/api/state` -> `{project: snapshot|null, projects:[...], capabilities:{...}}`
POST `/api/project/create` -> `{project}` with name/work_dir/input_dirs/output_dir.
POST `/api/project/open` -> `{project}` with work_dir.
POST `/api/project/settings` -> `{project}` with settings dict/other fields.
POST `/api/import` -> `{project}` with paths list.
POST `/api/annotations` -> `{revision,project}` with frame_id/revision_id/
annotations/source_sha256.
POST `/api/jobs` -> `{job,project}` with frame_id/revision_id/operation/
annotations/options. Starts asynchronously using a small thread pool.
POST `/api/jobs/resume` -> `{job,project}` with job_id, explicitly queued/failed
only; reuse cached provider output. Never blindly repeat unknown paid outcomes.
Optional `composition_options:{compositor,comfy_url}` is stored separately and
audited; only finishing controls may change, never prompt/masks/model settings.
POST `/api/jobs/cancel` -> `{job,project}` with job_id, queued only. Does not
interrupt a running call. Cancelled jobs cannot run or resume.
POST `/api/approve`, `/api/reject` -> `{project}` frame_id/revision_id.
POST `/api/export` -> `{receipt,project}` optional frame_ids.
POST `/api/repair-kit` -> `{kit,project}` frame_id/revision_id/annotations.
POST `/api/import-repair` -> `{revision,project}` frame_id/revision_id/kit_path/
result_path.
POST `/api/diagnostics` -> `{diagnostics}` optional destination.
GET `/image/<frame_id>/<revision_id>` -> PNG, immutable caching by hash.
GET `/api/jobs/<id>` -> `{job}`.
GET `/api/pick?kind=folder|images|image` desktop-native picker if supported;
browser may fall back to typed paths; response `{paths:[...]}`.
Writes require same-origin and `X-Studio-Token` from GET `/api/bootstrap`.
Bind loopback only. Import reads local files; an explicit generative operation
uploads its selected context and mask to the configured Google model provider.

## UI requirements

Polish, dark Ogarniacz style. Project input/work/output controls; frame gallery,
version history/parent, operation+prompt panel, jobs+actual stages/errors,
brush/rectangle/protect/native-width tools, pan/zoom/100%, before/after slider,
annotation-specific comments. Explicit save, run, approve, reject, export.
Edge repair first class, width separate from context; context slider128+.
Photoshop/Firefly repair-kit export and external result import work without
requiring any Photoshop bridge; no claim of automatic Firefly API execution.
Diagnostics and reopen project affordances. No fake generation/progress/QA.
No hidden chat dependency and no paid call on opening/viewing/testing UI.
