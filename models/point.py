import math

from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QPainter, QPen, QBrush, QColor

class Point:
    
    def __init__(self, x, y):
        self.x = x
        self.y = y

    def move_to(self, target_x: float, target_y: float):
        """Ustawia pozycję bezwzględną."""
        self.x = target_x
        self.y = target_y

    def move_by(self, dx: float, dy: float):
        """Przemieszcza punkt o wektor (przydatne przy propagacji)."""
        self.x += dx
        self.y += dy

    def distance_to(self, x: float, y: float) -> float:
        """Oblicza odległość euklidesową od podanych współrzędnych."""
        return math.hypot(self.x - x, self.y - y)

    def is_hit(self, x: float, y: float, tolerance: float = 8.0) -> bool:
        """Hit-testing: sprawdza, czy kursor trafił w punkt."""
        return self.distance_to(x, y) <= tolerance


    def to_qpointf(self) -> QPointF:
        return QPointF(self.x, self.y)
    
    def __repr__(self):
        return f"Point({self.x}, {self.y})"
        
    def draw(self, painter: QPainter, radius: float = 2.0, is_active: bool = False):
        color = QColor(52, 149, 235) if is_active else QColor(50, 50, 50)
        painter.setPen(QPen(color, 1))
        painter.setBrush(QBrush(color))
        painter.drawEllipse(self.to_qpointf(), radius, radius)
