from models import Point, Edge, StraightEdge
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QBrush, QColor, QPainter, QPen, QPolygonF

class Polygon:

    def __init__(self, points: list[Point], fill_color: QColor = QColor(186, 186, 186, 20)):
        self.points = points
        self.fill_color = fill_color
        self.edges: list[Edge] = []
        n = len(points)
        for i in range(n):
            # Łączymy punkt i z kolejnym (i+1), a ostatni z pierwszym (% n)
            self.edges.append(StraightEdge(self.points[i], self.points[(i + 1) % n]))

    def move_by(self, dx: float, dy: float):
        """Przesuwa cały wielokąt naraz."""
        for pt in self.points:
            pt.move_by(dx, dy)

    def to_qpolygonf(self) -> QPolygonF:
        """Tworzy reprezentację dla Qt do testowania wnętrza i wypełnienia."""
        qpoly = QPolygonF()
        for pt in self.points:
            qpoly.append(pt.to_qpointf())
        return qpoly

    def contains(self, x: float, y: float) -> bool:
        """Sprawdza, czy punkt (x, y) leży WEWNĄTRZ wielokąta."""
        return self.to_qpolygonf().containsPoint(
            QPointF(x, y), Qt.FillRule.OddEvenFill
        )

    def draw(self, painter: QPainter):
        # 1. Rysujemy półprzezroczyste wypełnienie wnętrza
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(self.fill_color))
        painter.drawPolygon(self.to_qpolygonf())

        # 2. Rysujemy krawędzie
        for edge in self.edges:
            edge.draw(painter)