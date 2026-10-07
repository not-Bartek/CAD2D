from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QPainter, QPen, QBrush, QColor

class Point:
    
    def __init__(self, x, y):
        self.x = x
        self.y = y

    def to_qpointf(self) -> QPointF:
        return QPointF(self.x, self.y)
    
    def __repr__(self):
        return f"Point({self.x}, {self.y})"

    def draw(self, painter: QPainter):
        endpoint_color = QColor(50, 50, 50)
        painter.setPen(QPen(endpoint_color, 1))
        painter.setBrush(QBrush(endpoint_color))
        painter.drawEllipse(self.to_qpointf(), 2, 2)
