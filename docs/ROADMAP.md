# Kolejne kroki

## 1. Spójne wydania — przed następną publikacją

- Zastąpić trzy skrypty publikacji jednym procesem z jawnym kanałem dev/test/prod
  i katalogiem docelowym niezależnym od lokalizacji źródeł.
- Wczytywać `app/version.txt` tylko raz. Generować version.json oraz manifest
  z tego numeru i SHA commita; build testowy nie powinien podbijać produkcji.
  Zachować istniejące numery 0.5.2.x dla kompatybilności aktualizatora.
- Pakować lokalne ikony, domyślną konfigurację, wersję i PDF Magician.
  Przetestować na komputerze bez dostępu do źródeł na Y:.
- Potwierdzić przygotowany lockfile pełnym buildem w czystym venv. Nie zbierać
  przypadkowych bibliotek, torch ani modeli ze środowiska ComfyUI.
- Aktualizator: czekać na zamknięcie starego procesu, kopiować do stagingu,
  weryfikować kompletność, nie połykać błędów kopiowania; zapisywać nową wersję
  dopiero po sukcesie. Zapewnić rollback.
- Rozdzielić instalację testową od `%LOCALAPPDATA%\OgarniaczSM`. Obecny updater
  EXE zawsze wskazuje instalację produkcyjną, także z testowego EXE.

Kryterium: nowy komputer instaluje paczkę, aktualizuje ją i wraca do poprzedniej
wersji; każda paczka jest powiązana z commitem. Nie wystarcza poprawny numer.

## 2. Przenośne środowisko i konfiguracja

- Oddzielić schemat konfiguracji od numeru aplikacji. Obecne `config.version=2`
  może być pokazane przez GUI jako wersja aplikacji, gdy brakuje version.json.
- Ustalić profile stanowisk: Blade22/Zeus/inne; przenieść ścieżki ComfyUI,
  adresy usług i exe 3ds Max do konfiguracji z walidacją.
- Funkcje zależne od ComfyUI/Zeusa ładować opcjonalnie. Obecna ścieżka
  `C:\ComfyUI` na Blade22 nie zawiera już opisanych w LCB źródeł i modeli.
- Oddzielić deweloperskie przyciski budowania/publikacji od aplikacji użytkownika.
  Ograniczenie po nazwie komputera/PIN-ie w kodzie nie jest kontrolą uprawnień.

## 3. Utrzymanie kodu

- Dopiero po ustabilizowaniu wydawania podzielić duży main.py na UI, konfigurację,
  uruchamianie narzędzi i integracje. Zmienić importy i spec PyInstallera razem.
- Dodać testy walidacji konfiguracji, wersji, przerwanej aktualizacji i rollbacku.
  GUI testować z atrapami usług; CI dla podstawowych kontroli jest już dodane.
- Prowadzić krótki changelog i decyzje architektoniczne zamiast wielu
  sprzecznych instrukcji. Dokumentacja bieżąca: README i docs/DEVELOPMENT.md.

Najpierw etap 1, potem nowe funkcje. Fundament lokalny jest przygotowany;
migracja produkcji i integracja gałęzi do main pozostają do wykonania.
