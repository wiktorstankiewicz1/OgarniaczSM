# Wydawanie OgarniaczSM

Kod i build powstają lokalnie. Produkcja współdzielona pozostaje w
`Y:\Instalki\_SKRYPTY WIKT\OgarniaczSM\PROD`. Nie używaj dawnych publish.bat,
test_publish.bat ani czyszczenia Qt z GENERATE_OGARNIACZ_EXE.py do nowych wydań.

## Build

1. Ustaw kolejną czteroczłonową wersję w `app/version.txt` i zapisz wszystkie
   zmiany w commicie. Uruchom testy, compileall i git diff --check.
2. W lokalnym venv wykonaj `python tools/build_release.py --output releases/WERSJA`.
   Narzędzie odrzuca brudne źródła i niepusty output. Buduje ze snapshotu konkretnego
   commita przez git archive, bez konfiguracji użytkownika i bez środowiska Codexa.
3. Wyniki to `dist/OgarniaczSM`, `package.zip`, `release_manifest.json`, log
   i kontrola zasobów WebEngine. Nie usuwa się qtwebengine_locales, zasobów .pak
   ani procesów pomocniczych Qt. W paczce są HTML, ikony, moduły Archviz i updater.
4. Wewnętrzny `file_manifest.json` zawiera SHA256 i rozmiar każdego pliku;
   zewnętrzny manifest zawiera SHA256 inventory oraz ZIP i commit źródeł.

## Test przed publikacją

Skopiuj paczkę do odrębnej instalacji testowej i sprawdź inventory. Nie uruchamiaj
EXE bezpośrednio z niezmiennego artefaktu builda ani z katalogu wydania na Y:.
Można skopiować konfigurację i ustawić `archviz_url` na wolny port lokalny oraz
`archviz_registry` na odrębny rejestr. Produkcyjne wartości domyślne to port8890
i `%LOCALAPPDATA%\StillMotion\ArchvizStudio\registry.json`.

Otwórz kafelek Archviz Studio, sprawdź obraz, lokalną korektę i wybór plików.
Health endpoint musi wykazać `mode=frozen`, wersję, commit i ścieżkę testowanego
EXE; istniejący serwer źródłowy nie jest dowodem poprawnego builda. Zamknij app,
uruchom ją ponownie i sprawdź zapisany projekt. Powtórz po bezczynnym zatrzymaniu
serwera przez autoryzowane `/api/shutdown`, żeby sprawdzić pełny zimny start.
Zatrzymanie jest odrzucane, gdy istnieją aktywne zadania.

## Publikacja i instalacja

Przygotuj niezmienny katalog `PROD/releases/WERSJA` zawierający `app/`, ZIP
i manifest wydania. Kopiuj najpierw do unikalnego folderu tymczasowego, zweryfikuj
pełne SHA256 i dopiero wtedy zmień nazwę na finalną. Zachowaj istniejący manifest
i poprzednie wydanie. Manifest produkcyjny jest publikowany atomowo po testach
i wskazuje `src_path` do nowego `app/`, wersję, commit i hash inventory/ZIP.
To zachowuje zgodność z istniejącymi klientami oczekującymi version/src_path.
Katalog latest można odświeżyć jako kopię zgodności po zmianie manifestu;
poprzedni latest pozostaje jako katalog rollbacku.

Pierwsze przejście ze starego updatera wymaga kontrolowanej instalacji nowej,
zweryfikowanej paczki i aktualizacji istniejącego skrótu. Stary updater nie
otrzymuje automatycznie nowych zabezpieczeń tylko przez publikację nowszego EXE.
Nie kasuj starej instalacji. Po wdrożeniu sprawdź uruchomienie normalnym skrótem,
kafelek oraz restart, korzystając z prawdziwego EXE.

Nowy updater weryfikuje całą paczkę, kopiuje do stagingu obok instalacji,
zachowuje konfigurację i stary rejestr, a następnie przełącza katalogi. Błąd
przełączenia odtwarza poprzedni katalog; wersja nie jest nadpisywana po błędzie
kopii. Helper pochodzi ze zweryfikowanego nowego wydania i jest uruchamiany z
TEMP po zakończeniu starego procesu. Działające zadania Archviz opóźniają update.
Dane nowego rejestru Archviz leżą poza folderem binariów i przeżywają aktualizację.

### Instalacja z sesji Codexa w MSIX

Na Windows 11 zapis nowego katalogu AppData przez proces pakietowy może trafić
do `Packages/<pakiet>/LocalCache`, mimo że w Codexie widać zwykłą ścieżkę.
`Test-Path`, poprawny hash i start EXE z tej samej sesji nie potwierdzają instalacji
dostępnej niezależnie od Codexa. Szczegółowe wykluczenia Windows 11 mają pierwszeństwo
przed starszym globalnym ustawieniem wyłączającym wirtualizację.
[Zasady MSIX](https://learn.microsoft.com/en-us/windows/msix/desktop/flexible-virtualization).

Sprawdź istnienie fizycznego pliku przez zewnętrzny provider WMI `CIM_DataFile`
oraz rzeczywistą ścieżkę uchwytu `GetFinalPathNameByHandleW`. Jeśli zapis został
przekierowany, wykonaj instalację zweryfikowanym `updater.copy_dir` z jednorazowego
zadania Harmonogramu: bieżący użytkownik, `InteractiveToken`, ograniczone uprawnienia,
bez wyzwalaczy. Interpreter, skrypt i protokół umieść poza AppData. Helper musi
przed zapisem potwierdzić `GetCurrentPackageFullName = 15700` (`NO_PACKAGE`).

W tym kontekście wykonaj fizyczną instalację, zachowaj kopie istniejących skrótów
i ustaw ich cel na fizyczny EXE. Rejestr Archviz inicjalizuj wyłącznie, gdy go brak;
istniejącej konfiguracji nie zastępuj. Zachowaj protokół i rollback, usuń jednorazowe
zadanie po zakończeniu. Następnie uruchom aplikację skrótem z Explorera i sprawdź
wersję, commit, panel i zimny restart poza Codexem. Nie zmieniaj zabezpieczeń ani
ustawień wirtualizacji MSIX. Aplikacja nie wymaga stałego zadania Harmonogramu.

## Rollback

Przed zmianą binariów zamknij app i bezczynny serwer. Przywróć poprzedni manifest
atomowo z kopii, przełącz skrót na zachowaną poprzednią instalację i uruchom ją.
Nie usuwaj danych projektów ani nowych artefaktów potrzebnych do diagnostyki.
Tag wydania powinien wskazywać faktyczny commit zapisany w przetestowanej paczce.
