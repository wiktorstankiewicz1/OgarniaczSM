# Archviz Studio

Pierwsza działająca wersja modułu OgarniaczSM do lokalnych poprawek wizualizacji.
Ten sam projekt można obsługiwać w panelu aplikacji, przeglądarce i przez CLI.
Historia, obrazy, maski i zadania są zapisane na dysku, niezależnie od czatu.

## Start

W lokalnym środowisku opisanym w DEVELOPMENT.md, z katalogu `app/`:

```powershell
..\.venv\Scripts\python.exe main.py --archviz-studio
```

Można też wybrać kafelek **Archviz Studio** na ekranie głównym. Moduł uruchamia
lokalny silnik dopiero przy pierwszym otwarciu. Domyślny adres:
`http://127.0.0.1:8890/`. Zamknięcie okna nie przerywa zadania silnika.
Źródłowy OgarniaczSM zachowuje blokadę aktualizatora produkcyjnej instalacji.

W osobnym worktree można użyć istniejącego lokalnego interpretera repozytorium,
zamiast kopiować `.venv`. Zmienna `OGARNIACZSM_CONFIG` wskazuje własny config lub
`config.example.json`, a `OGARNIACZ_ARCHVIZ_URL` opcjonalnie zmienia adres panelu.
`OGARNIACZ_ARCHVIZ_REGISTRY` może wskazać oddzielny rejestr ostatnich projektów,
np. dla pilota, także gdy silnik jest automatycznie uruchamiany z panelu Qt.
Sposób budowania i instalacji wersji EXE opisuje [RELEASING.md](RELEASING.md).
Rejestr projektów leży w `%LOCALAPPDATA%\StillMotion\ArchvizStudio`, poza
katalogiem aktualizowanych binariów. Dawny rejestr jest migrowany bez usuwania źródła.

## Projekt i codzienna praca

1. Utwórz projekt: wybierz foldery **input**, nowy folder **work** i oddzielny
   **output**. Folder work musi być pusty. Foldery nie mogą nakładać się tak,
   żeby eksport lub dane robocze nadpisały źródła.
2. Zaimportuj obrazy albo bezpośrednią zawartość folderu input. Import zapisuje
   niezmienną kopię bazową w natywnej rozdzielczości. Powtórny import tych samych
   danych nie dubluje kadrów. Oryginalna nazwa określa nazwę eksportowanego JPG.
3. Wybierz kadr i konkretną wersję. Narysuj prostokąt lub użyj pędzla;
   wybierz zaznaczenie na liście i wpisz uwagę. Oznacz zaakceptowane elementy
   jako **Chroń**. Uwagi należą do konkretnej wersji i jej sumy SHA256.
4. Zapisz uwagi, wybierz operację, sprawdź szerokość pasa i kontekst, uruchom
   poprawkę. Nowy wynik jest osobną wersją z zapisanym rodzicem. Kolejna poprawka
   może wychodzić z dowolnej wersji; poprzednie obrazy pozostają niezmienne.
5. Obejrzyj pełny kadr oraz styk w **100%**, używając porównania przed/po.
   Techniczny PASS sprawdza integralność i zakres zmian. Realizm, kolor,
   materiał i jakość krawędzi nadal wymagają oceny wzrokowej.
6. Wybierz **Zatwierdź**, następnie **Eksportuj zatwierdzone JPG**. Eksport używa
   zatwierdzonej wersji każdego kadru, również gdy aktualnie oglądasz inną.
   Nowy kandydat nie zastępuje automatycznie poprzedniego zatwierdzenia.
   Ponowna akceptacja i eksport nadpisują właściwy JPG, zachowując wcześniejszy
   plik i potwierdzenie operacji w work. Niezaakceptowane obrazy nie trafiają
   do output. Kolizja nazw dwóch kadrów zatrzymuje eksport przed zapisem.

## Krawędzie kanapy, dywanu i postaci

Tryb **Krawędzie** naprawia wąski pas wzdłuż zaznaczonego konturu. Dla prostokąta
i wielokąta importowanego przez API jest to obwód, dla pędzla — przebieg kreski. Nie jest to wypełnienie
całego prostokąta. Grubość jest podawana w pikselach obrazu, niezależnie od zoomu.

Model widzi większy wycinek z otoczeniem, ale do pełnego obrazu wraca wyłącznie
dozwolony pas. Maska ochronna ma pierwszeństwo także na półprzezroczystych
brzegach. Kompozycja w liniowym sRGB nie rozmywa całej granicy ani całego kadru.
Zapisywane są maska edycji, ochrony, kontekst, wynik modelu oraz natywne wycinki
przed/po. QA liczy zmienione piksele poza maską i w obszarach chronionych.

Zacznij od jednej problematycznej granicy, nie od wszystkich obrysów mebla naraz.
Zaznaczenie powinno obejmować wadliwe piksele i niewielki fragment obu materiałów.
Zbyt wąski pas może zostawić część starego artefaktu. Zbyt szeroki może dopuścić
zmianę tekstury. To narzędzie ręcznych masek; v1 nie wyznacza automatycznie
semantycznej krawędzi mebla, nie segmentuje osób i nie gwarantuje poprawnego
wyniku każdej generacji. Szeroki kontekst nie powiększa dozwolonej maski.

Przy podmianie osoby obejmij całą poprzednią sylwetkę, również stare włosy,
luźne kosmyki i ich antyaliasing. Krótsza nowa fryzura odsłania tło także wewnątrz
starego obrysu. Wąski kontur wokół głowy może nie objąć kosmyka pod brodą.
Pilot wykazał taki przypadek: czysty wynik modelu nadal dał wadliwy styk po
złożeniu z za ciasną maską. QA odrzuciło go; automatyczne zero zmian poza maską
nie jest dowodem poprawnej sylwetki.

## Operacje i dostawcy

- **Kolor**: lokalna, powtarzalna korekta jasności, nasycenia, tint i temperatury,
  bez płatnej generacji. Ujemny tint ogranicza magentę; dodatnia temperatura
  ociepla. To korekta ręczna, nie automatyczne dopasowanie materiału między ujęciami.
- **Postacie**, **Krawędzie**, **Poprawka lokalna**: jawny
  `gemini-3-pro-image`, `thinkingLevel=HIGH`, domyślnie 2K dla wycinka. Nie ma
  automatycznej zamiany na Flash. Model oraz rzeczywiste ustawienia i usage
  trafiają do potwierdzenia zadania. Klucz `GEMINI_API_KEY` jest odczytywany
  lokalnie z środowiska lub ustawień użytkownika Windows; nie jest wysyłany do UI.
- **Kompozycja lokalna / ComfyUI**: wybór miejsca wykonania końcowej kompozycji.
  Opcja Comfy wysyła rzeczywisty graph do wskazanego istniejącego serwera i zapisuje
  jego historię. Nano Banana nadal wykonuje generację przez API Google; nie jest
  uruchamiana lokalnie na GPU. Nieudana kompozycja nie wymusza nowej generacji.

Limit projektu jest liczbą płatnych wywołań, nie limitem kwoty i nie zastępuje
limitu rozliczeń dostawcy. Domyślnie wynosi 3; można go ustawić na 0. Wyczerpanie
limitu nie blokuje bezpłatnej korekty koloru ani importu zewnętrznego.

## Photoshop / Firefly

Wersja v1 obsługuje ręczny obieg plików, bez sterowania Photoshopem i bez
automatycznego wywołania Firefly:

1. Zaznacz pas naprawy i otwórz **Photoshop / Firefly — poprawka zewnętrzna**.
2. **Przygotuj wycinek i maskę** zapisuje `target.png`, `mask.png` i
   `manifest.json` z wymiarami, maską, kontekstem i SHA rodzica.
3. Otwórz target w Photoshopie. Załaduj białą część maski jako zaznaczenie,
   wykonaj poprawkę Firefly lub ręczny retusz. Zapisz wynik bez zmiany rozmiaru
   wycinka, jako PNG/sRGB. Zachowaj plik bazowy i manifest pakietu.
4. Wskaż wynik w Studio i użyj **Importuj poprawkę**. Program sprawdzi wymiary,
   rodzica i maskę, a następnie złoży nową, niezatwierdzoną wersję. Nawet zmiana
   całego wycinka przez Photoshop nie upoważnia do zmiany pikseli poza maską.
5. Obejrzyj 100%, zaakceptuj i wyeksportuj tak samo jak zwykły wynik.

## Trwałość i wznowienie

`project.json` jest manifestem projektu; zapis odbywa się atomowo z blokadą
między procesami. Obrazy rewizji są niezmienne i mają SHA256. Zadanie zachowuje
maski, rodzica, opcje, etap, receipt i wynik dostawcy przed kompozycją.

Po otwarciu projektu martwy worker z kompletnym, poprawnym wynikiem modelu może
być bezpiecznie wznowiony. GUI pokazuje przycisk wznowienia; jest to jawna akcja.
Znany błąd można świadomie ponowić, wykorzystując zachowany wynik. Żywy worker
nie jest uruchamiany drugi raz. Jeśli płatne żądanie wysłano, ale jego wynik
zaginął, zadanie ma stan **unknown**. Program nie ponawia go automatycznie.
Oczekujący szkic zadania można anulować; anulowanie nie przerywa już wysłanej
płatnej generacji i nie usuwa jej materiałów diagnostycznych.
Przy jawnym wznowieniu GUI używa bieżącego wyboru kompozycji i adresu ComfyUI.
Można więc dokończyć nieudaną kompozycję lokalnie, bez ponownej generacji.
Ta zmiana jest osobno zapisana w historii; prompt, maski i ustawienia modelu
oryginalnego zadania pozostają bez zmian.

## Codex i diagnostyka

Przykłady, z `app/`, tym samym interpreterem co aplikacja:

```powershell
python archviz_cli.py state
python archviz_cli.py inspect --work 'Y:\projekt\studio_work'
python archviz_cli.py diagnose --work 'Y:\projekt\studio_work'
python archviz_cli.py recover --work 'Y:\projekt\studio_work'
python archviz_cli.py resume --work 'Y:\projekt\studio_work' --job ID
python archviz_cli.py resume --work 'Y:\projekt\studio_work' --job ID --compositor local
python archviz_cli.py cancel --work 'Y:\projekt\studio_work' --job ID
```

`recover` tylko analizuje lokalny zapis; nie wykonuje API. `resume` wykorzystuje
konkretne istniejące zadanie. `run` tworzy nowe zadanie, dlatego nie służy do
ponawiania błędu kompozycji. `run/resume` kończą się kodem 1 przy nieudanym lub
nieznanym wyniku. CLI nie zawiera polecenia automatycznej akceptacji.

Przycisk diagnostyki zapisuje ZIP z redagowanym manifestem, zdarzeniami, maskami,
receipt, metadanymi i wycinkami ostatniego zadania (ograniczony rozmiar). Kluczy
nie ma w pakiecie. Duże archiwum wszystkich rewizji pozostaje w work.
Przekazując sprawę Codexowi wystarczy ścieżka work oraz identyfikator zadania.

Lokalne API jest opisane w [ARCHVIZ_STUDIO_CONTRACT.md](ARCHVIZ_STUDIO_CONTRACT.md).
Zapis wymaga tokenu z `/api/bootstrap`; usługa słucha wyłącznie na loopback,
nie udostępnia panelu w LAN. Jedna usługa ma jeden aktualnie otwarty projekt;
zmiana projektu synchronizuje widoki tego samego silnika.

## Pilot Elektrovnia

Dane próbne: `Y:\__PROJECTS\Elektrovnia\wizki\codex_test_poprawek\_archviz_studio_pilot`.
Projekt zawiera kopie 001, 003, 017, 025 i 033. `output_test` jest oddzielny od
zatwierdzonego `do wysylki`. Akceptacje w pilocie są wyłącznie testami programu.
Wyniki nowego retuszu nie zostały uznane za nowe akceptacje klienta.

Sprawdzono osadzenie w rzeczywistym oknie OgarniaczSM oraz działanie edytora,
uwag i porównania 100%, wersjonowanie, prawdziwe Nano Banana Pro HIGH i Comfy,
ręczny import pliku zewnętrznego, eksport JPG, diagnostykę i ponowne otwarcie.
Test roundtripu Photoshop/Firefly wykorzystuje plik kontrolny; nie potwierdza
wykonania generacji przez Firefly. Dowody i zakres niezależnej oceny:
[ARCHVIZ_STUDIO_QA.md](ARCHVIZ_STUDIO_QA.md).

Wizualny PASS dotyczy konkretnego wycinka i wersji, nie każdej przyszłej generacji.
Automatyczny QA pilnuje integralności; ostateczna ocena krawędzi należy do użytkownika.
