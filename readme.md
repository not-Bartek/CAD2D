# CAD 2D - Grafika Komputerowa, projekt 1

Interaktywny edytor wielokątów 2D w **PyQt6**: odcinki, krzywe Béziera, łuki okręgu, ograniczenia geometryczne (długość, równoległość) oraz ciągłości G0 / G1 / C1. Po każdej zmianie scena jest dogrywana lokalnym solverem z **propagacją błędu**, tak aby ograniczenia i ciągłości nie wykluczały się nawzajem.

---

## Spis treści

1. [Uruchomienie](#1-uruchomienie)
2. [Struktura projektu](#2-struktura-projektu)
3. [Modele danych](#3-modele-danych)
4. [Interfejs użytkownika](#4-interfejs-użytkownika)
5. [Algorytmy rysowania](#5-algorytmy-rysowania)
6. [Hit-testing (pick buffer)](#6-hit-testing-pick-buffer)
7. [Ograniczenia geometryczne i solver](#7-ograniczenia-geometryczne-i-solver)
8. [Ciągłości i krzywe](#8-ciągłości-i-krzywe)
9. [Propagacja błędu (repair)](#9-propagacja-błędu-repair)
10. [Decyzje projektowe - dlaczego tak](#10-decyzje-projektowe--dlaczego-tak)
11. [Złożoności obliczeniowe](#11-złożoności-obliczeniowe)
12. [Skróty i interakcje](#12-skróty-i-interakcje)

---

## 1. Uruchomienie

### Wymagania

- Python 3.10+ (testowane na 3.12)
- PyQt6

### Instalacja i start

```bash
cd CAD_G1
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

`requirements.txt` zawiera wyłącznie `PyQt6` - reszta to standardowa biblioteka Pythona.

Ikona okna pochodzi z `logo.png` (zaokrąglana przy starcie w `main.py`).

---

## 2. Struktura projektu

```
CAD_G1/
├── main.py                 # QApplication, MainWindow, radio Bresenham, F1/Dokumentacja
├── logo.png                # ikona aplikacji
├── requirements.txt
├── readme.md               # pełna dokumentacja (też w oknie Pomocy)
├── core/                   # algorytmy „czyste” (bez Qt-modeli sceny)
│   ├── enums.py            # EdgeType, Continuity
│   ├── line_draw.py        # Bresenham + draw_segment
│   ├── bezier_math.py      # Bernstein → baza potęgowa, forward differencing
│   └── arc_math.py         # geometria łuku (półokrąg / styczna)
├── models/                 # dane sceny + solver
│   ├── point.py
│   ├── edges.py            # Edge, StraightEdge, BezierEdge, ArcEdge
│   ├── polygon.py
│   ├── constraints.py      # LengthConstraint, ParallelConstraint, store
│   ├── continuity.py       # G0/G1/C1, recompute łuków
│   ├── solver.py           # settle, propagacja, drag
│   └── demo_scene.py       # scena startowa (poly + ograniczenia + Bézier/łuk)
└── widgets/
    ├── canvas.py           # UI: mysz, menu, pick buffer, drag
    └── help_dialog.py      # dokumentacja z poziomu aplikacji
```

### Podział odpowiedzialności

| Warstwa | Rola |
|--------|------|
| `core/` | Matematyka i rasteryzacja niezależne od modelu wielokąta |
| `models/` | Stan geometrii, ograniczenia, egzekwowanie ciągłości, solver |
| `widgets/` | Wejście użytkownika, rysowanie Qt, pick buffer |
| `main.py` | Okno i przełącznik algorytmu odcinka |

Cel: solver i ciągłości da się testować / rozumieć bez widgetów; canvas tylko woła `propagate_repair` / `move_point_or_translate`.

---

## 3. Modele danych

### 3.1. `Point`

```text
x, y                 - współrzędne zmiennoprzecinkowe
is_control           - True dla uchwytów Béziera (c1, c2)
continuity           - Continuity.G0 | G1 | C1
continuity_explicit  - czy użytkownik ustawił ciągłość ręcznie
```

Ciągłość jest **na wierzchołku**, nie na krawędzi: przy wierzchołku z dwoma sąsiadami egzekwujemy zgodność stycznych obu krawędzi. Dla łuków: G1 na wierzchołku obowiązuje dla **wszystkich** incydentnych łuków; na jednym łuku może być G1 tylko na jednym końcu.

### 3.2. Hierarchia krawędzi (`Edge`)

```text
Edge (ABC)
├── StraightEdge     - odcinek p1-p2
├── BezierEdge       - sześcienna Béziera: p1, c1, c2, p2
└── ArcEdge          - łuk okręgu przez p1→p2 (geometria wyliczana)
```

Wspólne API: `draw`, `length`, `control_points()`, `has_point`.

**Bézier** trzyma dwa punkty kontrolne (`is_control=True`). Wielobok kontrolny rysowany linią kreskowaną.

**Łuk** nie ma uchwytów. Cache `_geom = (cx, cy, r, a0, a1)` przeliczany w `recompute` / `recompute_all_arcs`:

| Stan końców | Geometria |
|-------------|-----------|
| oba G0 | półokrąg: środek = środek cięciwy, $R = L/2$ |
| jeden koniec G1 | okrąg przez p1, p2 ze zadaną jednostkową styczną na końcu G1 |
| oba G1 | niedozwolone - UI prosi o potwierdzenie i zdejmuje G1 z drugiego końca |

Na **Bézier** i **łuk** nie wolno zakładać długości ani równoległości; przy konwersji ograniczenia z tej krawędzi są usuwane.

### 3.3. `Polygon`

- `points: list[Point]` - wierzchołki w kolejności obiegu
- `edges: list[Edge]` - krawędź $i$ łączy `points[i]` z `points[(i+1) % n]`
- `rebuild_edges()` - po dodaniu/usunięciu wierzchołka **zachowuje** istniejące `BezierEdge` / `ArcEdge` o tych samych końcach
- `to_qpolygonf()` - obrys do wypełnienia i hit-testu: odcinki → wierzchołki, krzywe → próbki

### 3.4. Ograniczenia (`constraints.py`)

```text
ConstraintStore
└── items: list[Constraint]
        ├── LengthConstraint(p1, p2, length)
        └── ParallelConstraint(a1, a2, b1, b2, color)
```

- Długość: jedna na krawędź (ponowne dodanie podmienia wartość).
- Równoległość: parami; kolor z palety do wizualizacji.
- Identyfikacja krawędzi: para punktów (`same_edge`), stabilna po `rebuild_edges`.

Spełnienie:

- długość: $\lvert \lvert p_{1}p_{2} \rvert - L \rvert \le \varepsilon$
- równoległość: $\lvert \vec{a} \times \vec{b} \rvert \le \varepsilon\,\lvert\vec{a}\rvert\,\lvert\vec{b}\rvert$ (iloczyn wektorowy w 2D)

---

## 4. Interfejs użytkownika

Główny widget: `widgets/canvas.py`. Dokumentacja w aplikacji: przycisk **Dokumentacja** / **F1** (`widgets/help_dialog.py`).

### Scena startowa (`models/demo_scene.py`)

Po uruchomieniu widać od razu:

- 2 wielokąty (prostokąt + trójkąt) - nowy = wpis w `POLYGON_SPECS`
- krawędź Béziera (prawy bok prostokąta) z G1
- łuk (lewy bok trójkąta), oba końce G0 ⇒ $R = L/2$
- długość lewego boku prostokąta
- dwie równoległości (góra∥dół prostokąta oraz góra∥podstawa trójkąta)

| Akcja | Zachowanie |
|-------|------------|
| LPM na wierzchołku / CP | przeciąganie (punkt zostaje pod kursorem) |
| LPM na krawędzi | zaznaczenie |
| LPM na wypełnieniu | przesuwanie całego wielokąta |
| PPM na wierzchołku | usuń / zmień ciągłość |
| PPM na krawędzi | typ krzywej, długość, równoległość, dodaj wierzchołek |
| `G` | siatka |
| `Esc` | anuluj wybór pierwszej krawędzi równoległości |

Pasek w `main.py`: **Algorytm biblioteczny** vs **Bresenham** dla wszystkich odcinków (także segmentów aproksymujących krzywe).

---

## 5. Algorytmy rysowania

### 5.1. Odcinek - tryb biblioteczny

`QPainter.drawLine` - antyaliasing Qt. Złożoność po stronie biblioteki; z punktu widzenia aplikacji $O(1)$ wywołanie na segment.

### 5.2. Bresenham (`core/line_draw.py`)

Klasyczny raster odcinka całkowitoliczbowego:

1. $dx = \lvert x_{1}-x_{0} \rvert$, $dy = \lvert y_{1}-y_{0} \rvert$, kroki znakowe $sx$, $sy$
2. $err = dx - dy$
3. W pętli: zapal piksel; aktualizuj $err$ i współrzędne bez dzielenia / float

Współrzędne zmiennoprzecinkowe są zaokrąglane (`round`) przed algorytmem. Antyaliasing jest tymczasowo wyłączany, żeby piksele były ostre.

**Złożoność:** $O(N)$ gdzie $N \approx \max(dx, dy)$ - liczba zapalanych pikseli (liniowa względem długości rastra).

### 5.3. Sześcienna Béziera - forward differencing (`core/bezier_math.py`)

Cel: narysować $B(t)$, $t \in [0,1]$, bez wielokrotnego wyliczania Bernsteinów w każdym kroku.

1. **Bernstein → baza potęgowa**  
   $B(t) = A_{0} + A_{1} t + A_{2} t^{2} + A_{3} t^{3}$ - współczynniki z punktów kontrolnych $P_{0},\ldots,P_{3}$ w $O(1)$.

2. **Forward differencing**  
   Przy kroku $h = 1/S$:
   - początkowe różnice $\Delta$, $\Delta^{2}$, $\Delta^{3}$ z $A_{i}$ i $h$
   - każdy kolejny punkt: kilka dodań (bez potęgowania $t$)

**Złożoność:** $O(S)$ na krzywą przy $S$ krokach (domyślnie 64 przy rysowaniu, 48 przy fill/pick). Lepsze stałe niż naiwne $O(S)$ z pełnym Bernsteinem (mniej mnożeń).

Segmenty między próbkami idą przez `draw_segment` (library lub Bresenham).

### 5.4. Łuk okręgu (`core/arc_math.py` + `ArcEdge`)

1. Wyznaczenie $(c_{x}, c_{y}, R, \alpha_{0}, \alpha_{1})$
2. Próbkowanie kątowe: $S+1$ punktów na łuku
3. Rysowanie jako łańcuch odcinków

**Półokrąg (oba G0):** $R = L/2$, środek w środku cięciwy, sweep $\pm\pi$.

**G1 na jednym końcu:** środek leży na prostej $P + R \cdot n$, gdzie $n \perp \hat{t}$ (dwa sensy obrotu). Z warunku $\lvert C-Q \rvert = R$ wynika

$$
R = -\frac{\lvert P-Q \rvert^{2}}{2 n \cdot (P-Q)}
$$

(dla $R>0$). Wybierany jest wariant ze zdaną zgodnością stycznej i mniejszym $\lvert \mathrm{sweep} \rvert$.

**Złożoność:** geometria $O(1)$; próbki $O(S)$.

---

## 6. Hit-testing (pick buffer)

Zamiast ręcznego testowania odległości do każdej krawędzi/punktu canvas buduje **offscreenowy obraz ID** (`_rebuild_pick_buffer`):

1. Czarne tło
2. Wypełnienia wielokątów - unikalny kolor RGB kodujący ID obiektu
3. Krawędzie grubym piórem (`hit_radius * 2`) - Bézier/łuk jako polyline próbek
4. Punkty kontrolne i wierzchołki - elipsy/kwadraty

Odczyt: `pick_at(x,y)` → kolor piksela → `_pick_map[id]`. Bufor jest dirty po geometrii / resize.

**Dlaczego tak:** stały koszt zapytania $O(1)$ po zbudowaniu bufora; naturalna „grubość” picka dla krzywych; ten sam kształt co fill (próbkowany obrys).

**Złożoność przebudowy:** $O(P + E \cdot S + V)$ rysowania do obrazu rozmiaru $W \times H$ (koszt fill/stroke Qt), gdzie $P$ - wielokąty, $E$ - krawędzie, $S$ - próbki, $V$ - wierzchołki/CP. Zapytanie: $O(1)$.

---

## 7. Ograniczenia geometryczne i solver

Plik: `models/solver.py`. Solver jest **lokalny / iteracyjny** (projekcja na ograniczenia), nie globalny NLP.

### 7.1. Graf odległości

Wierzchołki (i uchwyty Béziera) połączone krawędziami ograniczeń oraz topologią wielokąta tworzą graf. BFS od seeda (przeciągany punkt) daje `dist[id]`. Przy naprawie **rusza się strona dalej od seeda** (wyższy score), żeby zaburzenie lokalne nie cofało kursora.

**Złożoność BFS:** $O(V_{g} + E_{g})$ w komponencie związanej z ograniczeniami / topologią.

### 7.2. Naprawa długości

- Z pinnowanym końcem: rzut drugiego punktu na okrąg o środku w anchorze (`_place_at_length`) - $O(1)$.
- Bez pinów: skalowanie względem środka krawędzi (`_scale_edge_from_mid`) - $O(1)$.

### 7.3. Naprawa równoległości

Wybór krawędzi-referencji vs ruchomej:

1. Więcej końców w `pinned` → lepsza referencja (np. koniec Béziera przy CP)
2. Inaczej: wyższy `dist` sumaryczny → krawędź ruszana
3. `_align_edge`: ustaw kierunek jednostkowy i długość (z constraintu długości albo bieżącej)

**Złożoność jednej naprawy:** $O(1)$.

### 7.4. `settle_all`

Do `SETTLE_ITERS` (800) razy:

- napraw wszystkie niespełnione równoległości
- napraw wszystkie niespełnione długości
- przerwij gdy błąd $\le \varepsilon$

To Gauss-Seidelowska projekcja na zbiory ograniczeń.

**Złożoność:** $O(I_{s} \cdot (L + P))$ gdzie $L$ - liczba długości, $P$ - równoległości, $I_{s} \le 800$. W praktyce zwykle dużo mniej iteracji.

### 7.5. `_propagate_from_fixed`

Szybka ścieżka przy drag: gdy punkt jest „sztywno” związany łańcuchem długości, domykamy kolejne końce jak w constraint propagation na drzewie długości. Jeśli równoległości w komponencie się wywrócą - fail → fallback do `settle_with_pinned` lub translacji całego poly.

**Złożoność:** $O(L \cdot V^{\prime})$ w najgorszym przypadku pętli (typowo blisko $O(L)$).

### 7.6. `move_point_or_translate` (drag wierzchołka)

1. Przywróć snapshot z początku drag
2. Ustaw punkt pod kursor
3. Spróbuj `_propagate_from_fixed`
4. Inaczej `settle_with_pinned`
5. Inaczej **sztywna translacja** wielokąta o $\Delta$ kursora (zachowuje wszystkie relacje względne)

Potem canvas woła propagację ciągłości (`_propagate_after_drag`).

### 7.7. Dodawanie ograniczenia (`try_add_*`)

Snapshot → dodaj → kilka inicjalizacji geometrycznych → `settle_all` + `propagate_repair`. Przy porażce: usuń constraint, przywróć snapshot (transakcja).

---

## 8. Ciągłości i krzywe

Plik: `models/continuity.py`.

### 8.1. Definicje

| Klasa | Warunek na stycznych $\mathbf{t}_{\mathrm{in}}, \mathbf{t}_{\mathrm{out}}$ |
|-------|--------------------------------------------------------------------------|
| **G0** | wspólny wierzchołek (zawsze przy spójnej topologii) |
| **G1** | $\hat{t}_{\mathrm{in}} = \hat{t}_{\mathrm{out}}$ (kierunek jednostkowy) |
| **C1** | $\mathbf{t}_{\mathrm{in}} = \mathbf{t}_{\mathrm{out}}$ (wektor, także długość) - praktycznie tylko przy Bézierze |

Styczne:

- odcinek: wektor wzdłuż krawędzi
- Bézier: $3(P_{1}-P_{0})$ / $3(P_{3}-P_{2})$ (pochodna w końcu)
- łuk: $\pm(-\sin\alpha, \cos\alpha)$ zależnie od znaku sweep

### 8.2. Egzekwowanie przy Bézierze

Preferencja: **najpierw uchwyty**, potem daleki wierzchołek odcinka (`dist` / `prefer_adjust`). Przy drag CP: końce segmentu pinowane, CP pod kursorem; ciągłość dogrywa sąsiadów.

### 8.3. Egzekwowanie przy łuku

Łuk z G1 jest **zdeterminowany** przez styczną sąsiada na końcu G1 - `recompute_all_arcs` przelicza $R$ i środek. Nie ma wolnego uchwytu; „naprawa łuku” = ponowne wyliczenie geometrii. G1 na wierzchołku dotyczy wszystkich incydentnych łuków; drugi koniec każdego z tych łuków musi być G0 (dialog przy konflikcie).

### 8.4. `sync_bezier_handles_from_snap`

Po ruchu końców: $\Delta = P_{\mathrm{now}} - P_{\mathrm{snap}}$, uchwyt $C \leftarrow C_{\mathrm{snap}} + \Delta$, z pominięciem `pinned` (przeciągany CP nie jest nadpisywany).

---

## 9. Propagacja błędu (repair)

`ConstraintSolver.propagate_repair` - wspólna pętla, żeby **równoległość nie psuła Béziera/łuku i odwrotnie**.

Jedna iteracja (do `PROPAGATE_ITERS = 64`):

1. **Ciągłości** (ew. z `prefer_adjust` = przeciągany punkt/CP)
2. **Kolejka dirty** - napraw długości/∥ wokół ruszonych punktów (`drain_dirty`)
3. **`settle_all`** + sync uchwytów
4. Ponownie ciągłości
5. Ponownie settle + sync
6. Ciągłości **tylko na uchwytach** (`handles_only`: wierzchołki zamrożone) - ∥ na odcinkach zostaje

Potem ponowne zakolejkowanie niespełnionych ograniczeń / wierzchołków z krzywymi.

### Drag CP Béziera (lokalnie)

- Pin: CP + `p1` + `p2` segmentu (ruch **względem końców**)
- `allow_translate=False` - bez sztywnego przesuwania całego wielokąta
- Ciągłość G1/C1 obraca/przesuwa przyległe odcinki; równoległość dogrywa **partnera** pary (scoring pinów preferuje krawędź przy końcu Béziera jako referencję)

### Drag wierzchołka

- Pin: przeciągany wierzchołek
- Po solverze geometrycznym: sync uchwytów ze snapu drag + `propagate_repair`
- Ostateczność: translacja poly

---

## 10. Decyzje projektowe - dlaczego tak

| Decyzja | Uzasadnienie |
|---------|----------------|
| Solver lokalny zamiast globalnego optymalizatora | Interakcja w czasie rzeczywistym; przewidywalne zachowanie „punkt pod kursorem” |
| Propagacja naprzemienna ciągłość ↔ ograniczenia | Jednostronne zamrażanie (np. tylko końce ∥) psuło drugą klasę relacji |
| Pick buffer zamiast geometrii analitycznej | Jednolity pick dla odcinków, Béziera i łuków; proste pogrubienie |
| Forward differencing dla Béziera | Wymaganie projektowe + mniej ciężkiej arytmetyki na próbkę |
| Bresenham jako opcja | Porównanie z API biblioteki; dydaktyka rastra |
| Brak constraintów na Bézier/łuk | Stopnie swobody krzywej kolidują z prostymi parami długość/∥ na cięciwie; jasna reguła UX |
| Ciągłość na wierzchołku | Naturalne G1/C1 między dowolnymi typami sąsiadów |
| Jedno G1 na łuku | Jedna styczna + dwa punkty wyznaczają okrąg; dwa G1 przeokreślają |
| Snapshot/restore przy drag i `try_add` | Atomowość: nieudana operacja nie zostawia półstanu |
| Identyfikacja krawędzi parami punktów | Przeżywa `rebuild_edges` bez wiszących referencji na stare `Edge` |

---

## 11. Złożoności obliczeniowe

Oznaczenia (typowy stan sceny):

| Symbol | Znaczenie |
|--------|-----------|
| $V$ | wierzchołki (+ uchwyty Béziera jako punkty) |
| $E$ | krawędzie |
| $L$, $P$ | ograniczenia długości / równoległości |
| $S$ | liczba próbek krzywej (ok. 32-64) |
| $W \times H$ | rozmiar pick buffera |
| $I_{s}$, $I_{p}$ | limity iteracji settle / propagate (800 / 64) |
| $N$ | piksele odcinka Bresenhama |

| Operacja | Złożoność | Uwagi |
|----------|-----------|--------|
| Bresenham 1 odcinek | $O(N)$ | $N$ rzędu długości rastra |
| Bernstein→power | $O(1)$ | |
| Forward diff. Béziera | $O(S)$ | |
| Próbki łuku | $O(S)$ | geometria $O(1)$ |
| Rysowanie sceny | $O(E \cdot S + V)$ | plus koszt Qt |
| Rebuild pick buffer | $O(E \cdot S + V + WH)$ | dominantnie fill |
| `pick_at` | $O(1)$ | |
| BFS `dist` | $O(V+E+L+P)$ | |
| Jedna naprawa length/∥ | $O(1)$ | |
| `settle_all` | $O(I_{s}(L+P))$ | early exit |
| `_propagate_from_fixed` | $O(L \cdot V)$ worst | zwykle dużo mniej |
| `recompute_all_arcs` | $O(E)$ | |
| `enforce_all_continuities` | $O(V)$ + recompute łuków | |
| `propagate_repair` (1 iter) | $O(V + I_{s}(L+P) + E)$ | |
| `propagate_repair` (max) | $O(I_{p} \cdot (\dots))$ | często 1-kilka iteracji |
| Drag frame (wierzchołek) | jak move + propagate | interakcja ~ms na małych scenach |
| Drag frame (CP) | propagate, bez translate poly | końce Béziera pinned |

Dla scen ćwiczeniowych (kilka wielokątów, $V \le 30$) wszystkie ścieżki są praktycznie **liniowe względem rozmiaru lokalnego grafu ograniczeń**, z małymi stałymi limitami iteracji jako bezpiecznikiem.

---

## 12. Skróty i interakcje

### Klawiatura

- **G** - siatka (10 px / 100 px)
- **Esc** - anuluj oczekującą równoległość
- **F1** / przycisk **Dokumentacja** - instrukcja, założenia, model, algorytmy + podgląd `readme.md`

### Menu krawędzi - typ krzywej

- Odcinek
- Krzywa Béziera (usuwa ograniczenia z krawędzi; domyślnie G1 jeśli niejawne)
- Łuk okręgu (usuwa ograniczenia; domyślnie G0 / $R=L/2$)

### Menu wierzchołka - ciągłość

- Przy sąsiedztwie krzywej: G0, G1; **C1** tylko gdy jest sąsiad Béziera
- Konflikt G1 na drugim końcu łuku → dialog potwierdzenia

### Ograniczenia (tylko odcinki)

- Zadaj długość…
- Dodaj równoległość (dwukrokowy wybór krawędzi; kolory na krawędziach)

---

## Szybka mapa plików → tematy

| Temat | Pliki |
|-------|--------|
| Start UI | `main.py`, `widgets/canvas.py` |
| Punkt / poly / krawędzie | `models/point.py`, `polygon.py`, `edges.py` |
| Bresenham | `core/line_draw.py` |
| Bézier (math) | `core/bezier_math.py` |
| Łuk (math) | `core/arc_math.py` |
| Ciągłości | `models/continuity.py` |
| Constraint + settle + repair | `models/constraints.py`, `models/solver.py` |
| Enumy | `core/enums.py` |

---

*Projekt zaliczeniowy z grafiki komputerowej - edytor CAD 2D z ograniczeniami i krzywymi.*
