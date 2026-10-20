# Blade22 i Zeus

## Gotowe stanowiska

| Komputer | Folder do ustawienia jako główny w projekcie Codex |
| --- | --- |
| Blade22 | C:\Users\wikto\source\repos\OgarniaczSM |
| Zeus | C:\Users\Zeus\source\repos\OgarniaczSM |

Repozytorium: https://github.com/wiktorstankiewicz1/OgarniaczSM

Aktualna wspólna baza: `development/project-foundation`. `main` nadal zawiera
starszy układ i nie został automatycznie zastąpiony. Oba klony mają tę samą
historię i śledzą `origin/development/project-foundation`.

Zeus: utworzono projekt Codex `Ogarniacz SM`, ID
`01a15a4a-27b9-7ed1-a405-368731c740ec`, z jednym lokalnym katalogiem źródeł.
Zarejestrowano również ten projekt jako projekt Zeusa w ustawieniach klienta
na Blade22. Jeśli otwarta aplikacja nie pokazuje go od razu, uruchom Codex
ponownie, żeby odczytał zapisane ustawienia. Kopie ustawień sprzed rejestracji
znajdują się obok plików `.codex-global-state.json` z sufiksem
`.ogarniacz-backup-<czas>`.

Oba komputery mają własne `.venv` na zarządzanym Pythonie 3.12.11,
22 pakiety według `requirements-windows.lock.txt`, lokalny `app/config.json`
i lokalny znacznik wersji deweloperskiej. Na Zeusie przechodzą wszystkie
3 testy, kompilacja składni oraz kontrola zgodności zależności.

## Codzienna praca

1. Zapisz bieżącą pracę w commicie i sprawdź `git status`.
2. Pobierz stan GitHub: `git fetch origin`.
3. Przed nowym zadaniem przejdź na `development/project-foundation` i wykonaj
   `git pull --ff-only`.
4. Dla zadania utwórz własną gałąź, np. `feature/blade22-pdf` lub
   `feature/zeus-workflows`. Dwie równoległe rozmowy powinny pracować na
   oddzielnych gałęziach; w obrębie jednego komputera używaj oddzielnych worktree,
   jeśli prace mają trwać równocześnie.
5. Uruchom kontrole z DEVELOPMENT.md, zapisz commit i wyślij swoją gałąź przez
   `git push -u origin HEAD`. Zintegruj zmianę przez PR do bieżącej wspólnej bazy.
6. Drugie stanowisko pobiera zmiany przez `git fetch` / `git pull --ff-only`.
   Jeżeli fast-forward się nie udaje, obejrzyj rozbieżność; nie używaj force-push.

Po integracji fundamentu do `main` zmień wspólną bazę na `main` na obu stanowiskach.
Zmiana źródeł w GitHub nie publikuje automatycznie nowego EXE.

Konfiguracje stanowisk, środowiska Pythona i pliki wynikowe nie są synchronizowane
przez Git. Nie kopiuj `.venv` pomiędzy komputerami. Udział
`Y:\Instalki\_SKRYPTY WIKT\OgarniaczSM\PROD` pozostaje istniejącą dystrybucją
produkcyjną; żadne czynności przygotowania klonów nie modyfikują tego katalogu.
