import sys
from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QRadioButton,
    QButtonGroup,
    QLabel,
    QPushButton,
)
from PyQt6.QtGui import QIcon, QImage, QPainter, QPainterPath, QPixmap, QKeySequence, QAction
from PyQt6.QtCore import Qt, QRectF
from widgets.canvas import Canvas
from widgets.help_dialog import HelpDialog
from core.line_draw import LineAlgorithm

PROJECT_ROOT = Path(__file__).resolve().parent


def load_app_icon(path: Path) -> QIcon:
    src = QImage(str(path)).convertToFormat(QImage.Format.Format_ARGB32)
    size = min(src.width(), src.height())
    radius = size * 0.2237

    rounded = QImage(size, size, QImage.Format.Format_ARGB32)
    rounded.fill(Qt.GlobalColor.transparent)

    painter = QPainter(rounded)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, size, size), radius, radius)
    painter.setClipPath(path)
    painter.drawImage(0, 0, src)
    painter.end()

    icon = QIcon()
    for s in (16, 32, 64, 128, 256, 512, 1024):
        pm = QPixmap.fromImage(
            rounded.scaled(
                s,
                s,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        icon.addPixmap(pm)
    return icon


class MainWindow(QMainWindow):
    def __init__(self, icon: QIcon):
        super().__init__()
        self.setWindowTitle("CAD 2D - Grafika Komputerowa projekt 1")
        self.setWindowIcon(icon)
        self.resize(720, 560)

        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        bar = QHBoxLayout()
        bar.addWidget(QLabel("Rysowanie odcinków:"))
        self.radio_library = QRadioButton("Algorytm biblioteczny")
        self.radio_bresenham = QRadioButton("Bresenham")
        self.radio_library.setChecked(True)

        group = QButtonGroup(self)
        group.addButton(self.radio_library)
        group.addButton(self.radio_bresenham)
        bar.addWidget(self.radio_library)
        bar.addWidget(self.radio_bresenham)
        bar.addStretch()

        help_btn = QPushButton("Dokumentacja")
        help_btn.setToolTip("Instrukcja, założenia, model danych (F1)")
        help_btn.clicked.connect(self._show_help)
        bar.addWidget(help_btn)
        layout.addLayout(bar)

        self.canvas = Canvas()
        layout.addWidget(self.canvas, stretch=1)
        self.setCentralWidget(root)

        self.radio_library.toggled.connect(self._on_algorithm_changed)
        self.radio_bresenham.toggled.connect(self._on_algorithm_changed)

        help_action = QAction("Dokumentacja", self)
        help_action.setShortcut(QKeySequence(Qt.Key.Key_F1))
        help_action.triggered.connect(self._show_help)
        self.addAction(help_action)

    def _show_help(self) -> None:
        HelpDialog(PROJECT_ROOT, self).exec()

    def _on_algorithm_changed(self, checked: bool) -> None:
        if not checked:
            return
        if self.radio_bresenham.isChecked():
            self.canvas.set_line_algorithm(LineAlgorithm.BRESENHAM)
        else:
            self.canvas.set_line_algorithm(LineAlgorithm.LIBRARY)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    icon = load_app_icon(PROJECT_ROOT / "logo.png")
    app.setWindowIcon(icon)
    window = MainWindow(icon)
    window.show()
    sys.exit(app.exec())
