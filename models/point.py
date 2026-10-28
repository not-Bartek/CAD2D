import math

from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QPainter, QPen, QBrush, QColor
from core.enums import Continuity


class Point:
    
    def __init__(self, x, y, *, is_control: bool = False):
        self.x = x
        self.y = y
        self.is_control = is_control
        self.continuity = Continuity.G0
        self.continuity_explicit = False

    def move_to(self, target_x: float, target_y: float):
        self.x = target_x
        self.y = target_y

    def move_by(self, dx: float, dy: float):
        self.x += dx
        self.y += dy

    def distance_to(self, x: float, y: float) -> float:
        return math.hypot(self.x - x, self.y - y)

    def to_qpointf(self) -> QPointF:
        return QPointF(self.x, self.y)
    
    def __repr__(self):
        return f"Point({self.x}, {self.y})"
        
    def draw(self, painter: QPainter, radius: float = 2.0, is_active: bool = False):
        if self.is_control:
            color = QColor(200, 80, 40) if is_active else QColor(180, 100, 40)
            painter.setPen(QPen(color, 1))
            painter.setBrush(QBrush(QColor(255, 255, 255)))
            r = max(2.0, radius)
            painter.drawRect(int(self.x - r), int(self.y - r), int(2 * r), int(2 * r))
            return
        color = QColor(52, 149, 235) if is_active else QColor(50, 50, 50)
        painter.setPen(QPen(color, 1))
        painter.setBrush(QBrush(color))
        painter.drawEllipse(self.to_qpointf(), radius, radius)
