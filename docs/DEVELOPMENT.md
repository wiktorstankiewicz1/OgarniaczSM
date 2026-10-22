# Rozwój i wersjonowanie

## Folder w Codex

W menu projektu wybierz Edytuj projekt, dodaj
`C:\Users\wikto\source\repos\OgarniaczSM` i ustaw ten folder jako główny.
Nowe rozmowy powinny pracować w katalogu z `.git` i `AGENTS.md`.
Opcjonalny drugi folder: `Y:\Instalki\_SKRYPTY WIKT\Still Motion Scripts`,
jeśli zadanie obejmuje rozwój MaxScriptów. Sam Ogarniacz nie wymaga go jako
drugiego katalogu projektu do przeglądania kafelków.

## Git

Nowe repozytorium zachowuje historię starej gałęzi `main.py`, stan importu
0.5.2.28 i oddzielny commit porządkowania. `origin` wskazuje istniejące repo
GitHub. Stare gałęzie zdalne pozostają bez zmian. Nie używaj force-push.

Na obecnym etapie kontynuuj `development/project-foundation`; większą funkcję
rozwijaj na osobnej gałęzi utworzonej z tej bazy. Po sprawdzeniu zmian wypchnij
gałąź i przygotuj PR do `main`, uwzględniając różnicę wobec starego `main`.
Dopiero po integracji używaj `main` jako podstawy następnych zmian.

Przed commitem: sprawdź `git status`, uruchom testy, obejrzyj diff. Commituj
źródła, przykładową konfigurację i zasoby. Instalacje, logi, EXE, konfiguracja
stanowiska, środowiska i modele są ignorowane. Usunięcie EXE z bieżącego drzewa
nie usuwa go ze starej historii.

Nie synchronizuj jednego katalogu `.git` przez iCloud/SMB pomiędzy komputerami.
Na Zeusie i innych stanowiskach używaj oddzielnego klonu i synchronizacji Git.
Udział Y: pozostaje miejscem dystrybucji i danych firmowych.

## Środowisko i weryfikacja

Python 3.12.11; własne `.venv` utwórz poleceniami z README. Zależności runtime są
w `app/requirements.txt`, narzędzia builda w `requirements-dev.txt`.
`requirements-windows.lock.txt` przypina sprawdzone 22 pakiety dla Windows.
Lockfile zweryfikowano testami, importem GUI i kontrolą zależności, ale jeszcze
nie pełnym buildem EXE. Do aktualizacji pakietów użyj requirements-dev.txt,
powtórz kontrole i świadomie odśwież lockfile.
Nie wykonuj `pip freeze` z globalnego Pythona ani ze środowiska ComfyUI.
Na Blade22 globalny Python 3.12.1 ma niesprawne ctypes; lokalne `.venv` korzysta
ze sprawnego interpretera zarządzanego przez uv. Nie modyfikowano starego Pythona.

Z katalogu głównego repozytorium:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m compileall -q app tests
git diff --check
```

Testy aktualizatora nie dotykają udziału Y:, instalacji, procesów ani sieci.
Sprawdzają, że kod uruchomiony z Pythona nie aktualizuje produkcyjnej instalacji,
a tryb skompilowany nadal uruchamia aktualizator po wykryciu nowszego wydania.
Sprawdzono też konstrukcję głównego okna w trybie offscreen (6 kafelków,
5 paneli) z atrapami odpytywania usług i skanowania katalogu skryptów.

Uruchamiaj GUI z `app/`, żeby zachować dotychczasową obsługę ścieżek względnych.
`OGARNIACZSM_CONFIG` może wskazać inny plik konfiguracji. `app/config.json` jest
lokalny, a `app/config.example.json` stanowi wersjonowany wzór. Opcjonalny lokalny
`app/version.json` służy dawnemu GUI do wyświetlania wersji; nie jest źródłem
numeru wydania. Oryginalne `version.txt` pozostaje niezmienione.

## Build i dystrybucja

Nowa ścieżka wydań to `tools/build_release.py`, uruchamiane z czystego commita.
Instrukcja stagingu, testu EXE, publikacji i rollbacku: [RELEASING.md](RELEASING.md).
Poniższy opis starego GENERATE pozostaje dokumentacją importu; nie używaj go do
nowego wydania, ponieważ usuwa część zasobów Qt WebEngine.

Dotychczasowy build lokalny, uruchamiany z `app/` we własnym `.venv`:

```powershell
..\.venv\Scripts\python.exe GENERATE_OGARNIACZ_EXE.py
```

Wyniki: `app/dist/ogarniacz/`; pliki pośrednie: `app/build/ogarniacz/`.
To import istniejącego builda, nie potwierdzona ścieżka wydania. Nie został
wykonany pełny build, instalacja ani test end-to-end na stanowisku użytkownika.
Zasoby i wersję trzeba jeszcze jawnie dodać do pakietu przed wydaniem.
Stare `.spec` z absolutnymi ścieżkami przeniesiono do `docs/legacy/specs/`.

Nie używaj `publish.bat`, `publish_update.bat` ani `test_publish.bat` jako
nowego procesu wydawniczego. Pierwsze dwa publikują do lokalnego `app/PROD`,
podczas gdy updater odczytuje manifest na Y:. Trzeci używa stałej wersji
`0.0.0.1` i współdzielonego katalogu `C:\Ogarniacz Tests`.
Do czasu migracji produkcja nadal korzysta z istniejącej instalacji na Y:.

Docelowo: testy → build z zapisanego commita → test osobnej instalacji →
niezmienny katalog `releases/<wersja>/` → manifest wskazujący to wydanie.
Manifest powinien zawierać numer wersji, commit i SHA256 paczki. Zmianę
`latest` wykonuj po weryfikacji; poprzednie wydanie zachowaj do rollbacku.
Tag `v<wersja>` dodawaj do commita rzeczywiście wydanej, sprawdzonej paczki.
Nie taguj obecnej kopii jako potwierdzonego builda produkcyjnego.
