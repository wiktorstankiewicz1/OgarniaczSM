# OgarniaczSM

Aplikacja desktopowa Still Motion: kafelki skryptów i aplikacji, PDF Magician,
People Enhancer oraz zadania przetwarzane na Zeusie.

Folder główny projektu Codex na Blade22:
`C:\Users\wikto\source\repos\OgarniaczSM`.
Wybierz katalog zawierający ten plik i `.git`, a nie `app/` ani udział Y:.

```text
OgarniaczSM/
  app/                 aktualne źródła, narzędzia budowania i zasoby
    config.example.json  wzór konfiguracji; config.json pozostaje lokalny
    version.txt          numer dotychczasowego wydania: 0.5.2.28
  tests/               testy izolacji aktualizatora
  docs/
    DEVELOPMENT.md     uruchamianie i zasady Git
    ROADMAP.md         priorytety dalszego rozwoju
    audit/             ustalenia i sumy SHA256 importu
    legacy/            wcześniejsze instrukcje i stare pliki .spec
  archive/             źródła ze starego repozytorium Git (styczeń 2026)
```

Start w PowerShell, z katalogu repozytorium:

```powershell
uv venv --python 3.12.11 --managed-python .venv
uv pip sync --python .venv/Scripts/python.exe requirements-windows.lock.txt
Copy-Item .\app\config.example.json .\app\config.json
$version = (Get-Content .\app\version.txt -Raw).Trim() + '.dev0'
@{version=$version} | ConvertTo-Json | Set-Content .\app\version.json -Encoding utf8
Set-Location app
..\.venv\Scripts\python.exe main.py
```

Na Blade22 `.venv` jest już przygotowane. Nie nadpisuj własnego config.json
przy kolejnych uruchomieniach. Globalny Python 3.12 ma błąd ctypes, więc używaj
interpretera projektu. `requirements-windows.lock.txt` zapisuje sprawdzony
zestaw 22 pakietów dla Windows/Python 3.12; pełny build EXE wymaga osobnej walidacji.

`config.example.json` zachowuje firmowe ścieżki Y: do projektów i skryptów 3ds Max.
Ikony oraz PDF Magician są lokalne. Własne ścieżki ustaw w `app/config.json`.
Poppler, ComfyUI, modele i usługi Zeusa to zależności zewnętrzne; repozytorium
ich nie instaluje. Nie wszystkie moduły wymagają ich do pracy.

Źródła przejęto z udziału Y: 20.10.2026 z weryfikacją SHA256. Zachowano dawną
historię Git i origin. Prace są na gałęzi `development/project-foundation`.
Zmiany są zapisane lokalnie; niczego nie wypchnięto ani nie wdrożono.

Testy: `python -m unittest discover -s tests -v`.
Szczegóły i ograniczenia: [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md).
