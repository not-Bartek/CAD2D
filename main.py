import sys
from PyQt6.QtWidgets import QApplication, QMainWindow, QWidget
from PyQt6.QtGui import QPainter, QPen, QBrush, QColor
from PyQt6.QtCore import Qt, QPointF
from widgets import Canvas

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Podstawy PyQt6: Canvas i Rysowanie")
        self.resize(700, 500)
        self.setCentralWidget(Canvas())


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())