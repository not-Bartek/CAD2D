from __future__ import annotations

import html
import re
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
<li><b>LPM na wierzchołku lub punkcie kontrolnym Béziera</b>: przeciąganie.
    Punkt zostaje pod kursorem.</li>
<li><b>LPM na krawędzi</b>: zaznaczenie.</li>
<li><b>LPM na wypełnieniu</b>: przesunięcie całego wielokąta.</li>
<li><b>PPM na wierzchołku</b>: usunięcie wierzchołka albo zmiana ciągłości
    (G0, G1, C1).</li>
<li><b>PPM na krawędzi</b>: typ (odcinek, Bézier, łuk), długość, równoległość,
    dodanie wierzchołka, usunięcie krawędzi (wielokąt otwarty) oraz ograniczeń.</li>
</ul>

<h3>Klawiatura i pasek</h3>
<ul>
<li><b>G</b>: siatka.</li>
<li><b>Esc</b>: anulowanie wyboru pierwszej krawędzi przy równoległości.</li>
<li><b>F1</b>: ta pomoc.</li>
<li><b>Przywróć wszystkie krawędzie</b>: przywraca geometrię usuniętych krawędzi
    (bez ich dawnych ograniczeń).</li>
<li>Checkboxy B-spline: krzywa konstrukcyjna oraz jej punkty pomocnicze.</li>
</ul>

<h3>Ograniczenia</h3>
<ul>
<li><b>Długość</b> dotyczy tylko odcinka. Dialog proponuje aktualną długość;
    wartość widać przy środku krawędzi.</li>
<li><b>Równoległość</b>: najpierw jedna krawędź, potem druga (mogą należeć
    do różnych wielokątów). Na obu pojawia się symbol <b>∥</b> i wspólny kolor.</li>
<li>Na Bézierze i łuku ograniczeń się nie ustawia. Zmiana typu krawędzi
    kasuje ograniczenia z tej pary wierzchołków.</li>
<li>Dodanie albo usunięcie wierzchołka kasuje ograniczenia związane
    z usuniętymi krawędziami.</li>
</ul>

<h3>Krzywe</h3>
<ul>
<li><b>Bézier</b>: kreskowany wielobok kontrolny i dwa uchwyty. Ciągłość
    G0, G1 albo C1. Po przełączeniu na Béziera domyślnie G1, o ile ciągłości
    nie ustawiono wcześniej ręcznie.</li>
<li><b>Łuk</b>: G0 albo G1, przy czym G1 może mieć tylko jeden koniec.
    Gdy oba końce są G0, promień wynosi połowę cięciwy.</li>
</ul>

<h3>Rysowanie odcinków</h3>
<p>Na pasku wybierasz algorytm biblioteczny Qt albo własną implementację
Bresenhama. Wybrany wariant dotyczy wszystkich odcinków, także segmentów
aproksymujących krzywe.</p>
"""

ASSUMPTIONS_HTML = """
<h2>Przyjęte założenia</h2>
<ul>
<li>Figury startowe są zadane w kodzie (<code>models/demo_scene.py</code>).
    Nie trzeba ich tworzyć od zera.</li>
<li>Samoprzecięcia wielokątów są dozwolone.</li>
<li>Solver jest lokalny (projekcja i propagacja błędu), a nie globalny
    optymalizator. Przeciągany punkt zostaje pod kursorem.</li>
<li>Dla nazwisk A-K ograniczenie parami to <b>równoległość</b>, a domyślna
    ciągłość przy Bézierze to <b>G1</b>.</li>
<li>Ciągłość należy do wierzchołka. G1 na wierzchołku obejmuje wszystkie
    incydentne łuki, ale na jednym łuku G1 może mieć tylko jeden koniec.</li>
<li>Interfejs jest celowo prosty. Priorytetem są algorytmy i model danych.</li>
</ul>
"""

DATA_MODEL_HTML = """
<h2>Model danych</h2>
<ul>
<li><b>Point</b>: współrzędne (x, y), flaga uchwytu Béziera oraz ciągłość
    G0, G1 albo C1.</li>
<li><b>Edge</b>: odcinek, Bézier (p1, c1, c2, p2) albo łuk. Geometria łuku
    wynika z końców i ciągłości.</li>
<li><b>Polygon</b>: wierzchołki i krawędzie w kolejności obiegu. Po usunięciu
    krawędzi wielokąt staje się otwarty; krawędź istnieje wirtualnie i można
    ją później przywrócić.</li>
<li><b>ConstraintStore</b>: długości i równoległości. Krawędź identyfikuje
    para punktów, a nie obiekt <code>Edge</code>.</li>
<li><b>ConstraintSolver</b>: najpierw settle ograniczeń, potem
    <code>propagate_repair</code>, które dogrywa ciągłości z długościami
    i równoległościami.</li>
</ul>
"""

ALGORITHMS_HTML = """
<h2>Algorytmy</h2>
<ul>
<li><b>Bresenham</b>: raster odcinka na liczbach całkowitych, bez dzielenia.</li>
<li><b>Bézier</b>: przejście z bazy Bernsteina do bazy potęgowej, potem
    forward differencing (kolejne punkty z samych dodań).</li>
<li><b>Łuk</b>: przy obu końcach G0 półokrąg o promieniu R = L/2. Przy G1
    okrąg ze zadaną styczną sąsiada.</li>
<li><b>B-spline</b>: konstrukcyjny łańcuch Bézierów z podziału odcinków
    między wierzchołkami (nie z rzeczywistego kształtu krawędzi).</li>
<li><b>Pick buffer</b>: offscreenowa mapa identyfikatorów zakodowanych
    w kolorze, więc hit-test jest w czasie stałym.</li>
<li><b>Ograniczenia</b>: iteracyjna projekcja (długość na okrąg, równoległość
    przez wyrównanie kierunku), BFS od przeciąganego punktu i naprzemienna
    naprawa z ciągłościami. Jeśli lokalnie się nie da, wierzchołek ciągnie
    za sobą cały swój wielokąt.</li>
</ul>
"""


def _pretty_tex(src: str) -> str:
    s = src
    s = re.sub(r"\\mathrm\{([^}]+)\}", r"\1", s)
    s = re.sub(r"\\mathbf\{([^}]+)\}", r"\1", s)
    s = re.sub(r"\\vec\{([^}]+)\}", r"\1", s)
    s = re.sub(r"\\hat\{([^}]+)\}", r"\1", s)
    s = re.sub(r"\\frac\{([^}]+)\}\{([^}]+)\}", r"(\1)/(\2)", s)
    for a, b in (
        (r"\cdot", "·"),
        (r"\times", "×"),
        (r"\le", "≤"),
        (r"\geq", "≥"),
        (r"\lesssim", "≲"),
        (r"\varepsilon", "ε"),
        (r"\Delta", "Δ"),
        (r"\alpha", "α"),
        (r"\pm", "±"),
        (r"\pi", "π"),
        (r"\in", "∈"),
        (r"\perp", "⊥"),
        (r"\sim", "~"),
        (r"\ldots", "..."),
        (r"\lvert", "|"),
        (r"\rvert", "|"),
        (r"\,", " "),
        (r"\ ", " "),
    ):
        s = s.replace(a, b)
    return s


def _heading_id(title: str) -> str:
    t = title.lower()
    t = re.sub(r"[^\w\s-]", "", t, flags=re.UNICODE)
    t = re.sub(r"\s+", "-", t.strip())
    return t


def _inline(text: str) -> str:
    slots: list[str] = []

    def stash(frag: str) -> str:
        slots.append(frag)
        return f"\x00{len(slots) - 1}\x00"

    text = re.sub(
        r"`([^`]+)`",
        lambda m: stash(
            f"<code style='color:#f2f2f2;background:#3a3a3a;'>{html.escape(m.group(1))}</code>"
        ),
        text,
    )
    text = re.sub(
        r"\$([^$]+)\$",
        lambda m: stash(f"<i>{html.escape(_pretty_tex(m.group(1)))}</i>"),
        text,
    )
    text = re.sub(
        r"\[([^\]]+)\]\(([^)]+)\)",
        lambda m: stash(
            f'<a href="{html.escape(m.group(2), quote=True)}">{html.escape(m.group(1))}</a>'
        ),
        text,
    )
    text = html.escape(text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<i>\1</i>", text)
    return re.sub(r"\x00(\d+)\x00", lambda m: slots[int(m.group(1))], text)


def _is_table_sep(line: str) -> bool:
    inner = line.strip().strip("|")
    return bool(inner) and all(ch in "-|: " for ch in inner)


def _table_html(rows: list[str]) -> str:
    body: list[str] = []
    header = True
    for row in rows:
        if _is_table_sep(row):
            header = False
            continue
        cells = [c.strip() for c in row.strip().strip("|").split("|")]
        tag = "th" if header else "td"
        inner = "".join(f"<{tag}>{_inline(c)}</{tag}>" for c in cells)
        body.append(f"<tr>{inner}</tr>")
        header = False
    return (
        "<table border='1' cellspacing='0' cellpadding='4' "
        "style='border-collapse:collapse;margin:8px 0;color:#ececec;border-color:#666;'>"
        + "".join(body)
        + "</table>"
    )


def _md_to_html(text: str) -> str:
    lines = text.replace("\r\n", "\n").split("\n")
    out: list[str] = []
    i = 0
    n = len(lines)

    def is_fence(s: str) -> bool:
        return s.startswith("```")

    def is_heading(s: str) -> bool:
        return s.startswith("# ") or s.startswith("## ") or s.startswith("### ")

    while i < n:
        line = lines[i]
        if is_fence(line):
            i += 1
            buf: list[str] = []
            while i < n and not is_fence(lines[i]):
                buf.append(lines[i])
                i += 1
            if i < n:
                i += 1
            out.append(
                "<pre style='background:#2a2a2a;padding:8px;font-size:12px;color:#f2f2f2;'>"
                + html.escape("\n".join(buf))
                + "</pre>"
            )
            continue
        if line.strip() == "$$":
            i += 1
            buf = []
            while i < n and lines[i].strip() != "$$":
                buf.append(lines[i].strip())
                i += 1
            if i < n:
                i += 1
            out.append(
                "<p style='text-align:center;font-style:italic;'>"
                + html.escape(_pretty_tex(" ".join(buf)))
                + "</p>"
            )
            continue
        if line.strip() in ("---", "***"):
            out.append("<hr>")
            i += 1
            continue
        if is_heading(line):
            level = len(line) - len(line.lstrip("#"))
            title = line[level:].strip()
            tag = f"h{min(level, 3)}"
            hid = _heading_id(title)
            out.append(f'<{tag} id="{hid}">{_inline(title)}</{tag}>')
            i += 1
            continue
        if line.startswith("|"):
            rows = []
            while i < n and lines[i].startswith("|"):
                rows.append(lines[i])
                i += 1
            out.append(_table_html(rows))
            continue
        if line.startswith("- "):
            out.append("<ul>")
            while i < n and lines[i].startswith("- "):
                item = lines[i][2:]
                i += 1
                while i < n and lines[i].startswith("  ") and not lines[i].startswith("- "):
                    item += " " + lines[i].strip()
                    i += 1
                out.append(f"<li>{_inline(item)}</li>")
            out.append("</ul>")
            continue
        if re.match(r"^\d+\. ", line):
            out.append("<ol>")
            while i < n and re.match(r"^\d+\. ", lines[i]):
                item = re.sub(r"^\d+\. ", "", lines[i])
                i += 1
                while i < n and lines[i].startswith("  ") and not re.match(r"^\d+\. ", lines[i]):
                    item += " " + lines[i].strip()
                    i += 1
                out.append(f"<li>{_inline(item)}</li>")
            out.append("</ol>")
            continue
        if not line.strip():
            i += 1
            continue
        para: list[str] = []
        while i < n and lines[i].strip():
            s = lines[i]
            if (
                is_fence(s)
                or is_heading(s)
                or s.startswith("|")
                or s.startswith("- ")
                or re.match(r"^\d+\. ", s)
                or s.strip() in ("---", "***", "$$")
            ):
                break
            para.append(s.strip())
            i += 1
        if para:
            out.append(f"<p>{_inline(' '.join(para))}</p>")

    return (
        "<div style='font-size:13px;line-height:1.45;color:#ececec;'>"
        + "".join(out)
        + "</div>"
    )


def _readme_html(project_root: Path) -> str:
    path = project_root / "readme.md"
    if not path.is_file():
        return "<p><i>Brak pliku readme.md.</i></p>"
    return _md_to_html(path.read_text(encoding="utf-8"))


class HelpDialog(QDialog):
    def __init__(self, project_root: Path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Dokumentacja CAD 2D")
        self.resize(720, 560)
        self.setStyleSheet(
            "QDialog, QTabWidget, QTabWidget::pane, QDialogButtonBox {"
            " background-color: #1e1e1e; color: #ececec; }"
            " QTabBar::tab { background: #2a2a2a; color: #ececec; padding: 6px 12px; }"
            " QTabBar::tab:selected { background: #3a3a3a; }"
            " QPushButton { background: #3a3a3a; color: #ececec; }"
        )

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
        browser.setStyleSheet(
            "QTextBrowser { background-color: #1e1e1e; color: #ececec; }"
            " a { color: #8cb4ff; }"
        )
        wrapped = (
            "<html><head><style>"
            "body { background-color:#1e1e1e; color:#ececec; }"
            "p, li, td, th, h1, h2, h3 { color:#ececec; }"
            "a { color:#8cb4ff; }"
            "code, pre { color:#f2f2f2; background-color:#2a2a2a; }"
            "th { background-color:#333333; }"
            "</style></head>"
            "<body style='background-color:#1e1e1e;color:#ececec;'>"
            f"{html}</body></html>"
        )
        browser.setHtml(wrapped)
        return browser
