from PyQt6.QtWidgets import QApplication, QMainWindow, QWidget
from PyQt6.QtGui import QPainter, QPen, QBrush, QColor
from PyQt6.QtCore import Qt, QPointF
from models import *

class Canvas(QWidget):
    def __init__(self):
        super().__init__()
        
        # 1. Punkty statyczne do odcinka i okręgu
        self.line_p1 = QPointF(130, 100)
        self.line_p2 = QPointF(100, 50)
        self.circle_center = QPointF(500, 300)
        self.circle_radius = 60.0


        self.points = [
            Point(300, 400),
            Point(350, 200),
            Point(350, 300)
        ]

        self.edges = [
            StraightEdge(self.points[0], self.points[1]),
            StraightEdge(self.points[1], self.points[2]),
        ]

    # --- PĘTLA RYSOWANIA ---
    def paintEvent(self, event):
        painter = QPainter(self)
        # Wygładzanie krawędzi (antyaliasing)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        # Tło
        painter.fillRect(self.rect(), Qt.GlobalColor.white)

        # A. Rysowanie linii między dwoma punktami
        pen_line = QPen(QColor(50, 50, 50), 1)
        painter.setPen(pen_line)
        painter.drawLine(self.line_p1, self.line_p2)

        # B. Rysowanie okręgu
        pen_circle = QPen(QColor(0, 120, 215), 2)
        painter.setPen(pen_circle)
        painter.setBrush(Qt.BrushStyle.NoBrush)  # Bez wypełnienia środka
        painter.drawEllipse(self.circle_center, self.circle_radius, self.circle_radius)

        # C. Punkty końcowe linii: małe, jednolite i bez kolorowego obrysu
        endpoint_color = QColor(50, 50, 50)
        painter.setPen(QPen(endpoint_color, 1))
        painter.setBrush(QBrush(endpoint_color))
        painter.drawEllipse(self.line_p1, 2, 2)
        painter.drawEllipse(self.line_p2, 2, 2)

        for edge in self.edges:
            edge.draw(painter)
        for point in self.points:
            point.draw(painter)
        