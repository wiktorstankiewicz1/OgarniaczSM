# OgarniaczSM

This repository contains the Still Motion desktop toolbox (Python / PySide6),
including PDF Magician, MaxScript tiles, People Enhancer and Zeus workflows.
Read README.md and docs/DEVELOPMENT.md before changing build or release behavior.

- Active code is in app/. Preserve its flat imports and colocated resources until
  a separate migration updates imports, configuration and PyInstaller together.
- docs/legacy/ and archive/ are historical reference, not current instructions.
- The source import is recorded in docs/audit/source-import-2026-10-20.json.
- When creating or updating scripts, always put the script icon in the same
  folder as the script and use the same base name (for example tool.ms/tool.png).
  Keep toolbar size/alpha variants there with only format-required suffixes.
  The imported scripts use copies of the existing app icon as .ico companions.
- Never import generated build/, dist/, PROD/, virtual environments or model
  weights into Git. Keep app/config.json local; maintain config.example.json.
- Local source runs must not trigger the updater for the installed app.
- app/version.txt is the existing four-component release version. Preserve
  compatibility; do not renumber published releases during cleanup.
- Use the repository virtual environment. Run unittest and compileall as in
  docs/DEVELOPMENT.md; mock services, updater execution and process exits.
- Do not run publishing, installers, dependency repair or update actions as part
  of ordinary verification. Those operations change deployments or installations.
- Shared production remains Y:\Instalki\_SKRYPTY WIKT\OgarniaczSM\PROD.
  Legacy publish scripts in this checkout write to app/PROD; they do not deploy
  the shared production. Release migration remains a separate task.
