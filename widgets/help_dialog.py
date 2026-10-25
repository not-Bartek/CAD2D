"""Dokumentacja dostępna z poziomu aplikacji (Help / F1)."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QTextBrowser,
    QDialogButtonBox,
    QTabWidget,
    QWidget,
)
USER_GUIDE_HTML = """
<h2>Instrukcja obsługi</h2>

<h3>Mysz</h3>
<ul>
<li><b>LPM na wierzchołku / punkcie kontrolnym Béziera</b> — przeciąganie
    (punkt zawsze pod kursorem).</li>
<li><b>LPM na krawędzi</b> — zaznaczenie krawędzi.</li>
<li><b>LPM na wypełnieniu</b> — przesuwanie całego wielokąta.</li>
<li><b>PPM na wierzchołku</b> — usuń wierzchołek / zmień ciągłość (G0, G1, C1).</li>
<li><b>PPM na krawędzi</b> — typ (odcinek / Bézier / łuk), długość, równoległość,
    dodaj wierzchołek, usuń ograniczenia.</li>
</ul>

<h3>Klawiatura</h3>
<ul>
<li><b>G</b> — włącz / wyłącz siatkę.</li>
<li><b>Esc</b> — anuluj wybór pierwszej krawędzi przy dodawaniu równoległości.</li>
<li><b>F1</b> — ta pomoc.</li>
</ul>

<h3>Ograniczenia</h3>
<ul>
<li><b>Długość</b> — tylko dla odcinka; dialog z domyślną wartością = aktualna długość.
    Liczba przy środku krawędzi.</li>
<li><b>Równoległość</b> — wybierz pierwszą krawędź, potem drugą (mogą być z różnych
    wielokątów). Symbol <b>∥</b> i kolor na obu krawędziach.</li>
<li>Na Bézierze i łuku ograniczeń się nie ustawia; konwersja usuwa istniejące.</li>
<li>Dodanie / usunięcie wierzchołka kasuje ograniczenia związane z usuniętymi krawędziami.</li>
</ul>

<h3>Krzywe</h3>
<ul>
<li><b>Bézier</b> — wielobok kreskowany, 2 punkty kontrolne; ciągłość G0 / G1 / C1.
    Domyślnie G1 przy przełączeniu (jeśli nie ustawiono jawnie).</li>
<li><b>Łuk</b> — G0 / G1; tylko jeden koniec z G1. Oba G0 ⇒ promień = połowa cięciwy.</li>
</ul>

<h3>Rysowanie odcinków</h3>
<p>Radio na pasku: algorytm biblioteczny Qt albo własny Bresenham.</p>
"""

ASSUMPTIONS_HTML = """
<h2>Przyjęte założenia</h2>
<ul>
<li>Wielokąty startowe są w kodzie (<code>models/demo_scene.py</code>);
    użytkownik nie musi tworzyć nowych figur.</li>
<li>Samoprzecięcia wielokątów są dozwolone.</li>
<li>Solver jest lokalny (projekcja + propagacja błędu), nie globalny optymalizator —
    przeciągany punkt zostaje pod kursorem.</li>
<li>Dla nazwisk A–K: ograniczenie parami to <b>równoległość</b>, domyślna ciągłość
    przy Bézierze to <b>G1</b>.</li>
<li>Ciągłość jest atrybutem wierzchołka; G1 na wierzchołku dotyczy wszystkich
    incydentnych łuków, ale na jednym łuku G1 może mieć tylko jeden koniec.</li>
<li>UI jest celowo proste — priorytetem są algorytmy i model danych.</li>
</ul>
"""

DATA_MODEL_HTML = """
<h2>Model danych (skrót)</h2>
<ul>
<li><b>Point</b> — (x, y), flaga uchwytu, ciągłość G0/G1/C1.</li>
<li><b>Edge</b> — odcinek / Bézier (p1, c1, c2, p2) / łuk (geometria z końców + ciągłości).</li>
<li><b>Polygon</b> — lista wierzchołków + lista krawędzi w obiegu.</li>
<li><b>ConstraintStore</b> — długości i równoległości; krawędź identyfikowana parą punktów.</li>
<li><b>ConstraintSolver</b> — settle ograniczeń + <code>propagate_repair</code>
    (ciągłości ↔ długości/∥).</li>
</ul>
<p>Szczegóły i złożoności: plik <code>readme.md</code> w katalogu projektu.</p>
"""

ALGORITHMS_HTML = """
<h2>Algorytmy (skrót)</h2>
<ul>
<li><b>Bresenham</b> — raster odcinka całkowitoliczbowego bez dzielenia.</li>
<li><b>Bézier</b> — Bernstein → baza potęgowa, potem forward differencing (przyrostowo).</li>
<li><b>Łuk</b> — półokrąg R = L/2 przy obu G0; przy G1 okrąg ze stycznej sąsiada.</li>
<li><b>Pick buffer</b> — offscreen mapa ID kolorami (O(1) hit-test).</li>
<li><b>Ograniczenia</b> — iteracyjna projekcja (długość na okrąg / równoległość przez
    wyrównanie kierunku), BFS „odległości od przeciąganego punktu”, potem naprzemienna
    propagacja z ciągłościami, aż scena jest spójna albo wyczerpie się limit iteracji.
    Ostateczność przy drag wierzchołka: translacja całego wielokąta.</li>
</ul>
"""


def _readme_html(project_root: Path) -> str:
    path = project_root / "readme.md"
    if not path.is_file():
        return "<p><i>Brak pliku readme.md.</i></p>"
    text = path.read_text(encoding="utf-8")
    # prosty podgląd — unikamy zależności od markdown
    escaped = (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
    return f"<pre style='white-space: pre-wrap; font-family: monospace; font-size: 12px;'>{escaped}</pre>"


class HelpDialog(QDialog):
    def __init__(self, project_root: Path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Dokumentacja — CAD 2D")
        self.resize(640, 520)

        tabs = QTabWidget()
        tabs.addTab(self._page(USER_GUIDE_HTML), "Obsługa")
        tabs.addTab(self._page(ASSUMPTIONS_HTML), "Założenia")
        tabs.addTab(self._page(DATA_MODEL_HTML), "Model danych")
        tabs.addTab(self._page(ALGORITHMS_HTML), "Algorytmy")
        tabs.addTab(self._page(_readme_html(project_root)), "readme.md")

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.accept)

        layout = QVBoxLayout(self)
        layout.addWidget(tabs)
        layout.addWidget(buttons)

    @staticmethod
    def _page(html: str) -> QWidget:
        browser = QTextBrowser()
        browser.setOpenExternalLinks(True)
        browser.setHtml(html)
        return browser
