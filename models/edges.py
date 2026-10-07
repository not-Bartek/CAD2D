from abc import abstractmethod

from models import Point
from core.enums import EdgeType
from PyQt6.QtGui import QPainter, QPen, QColor, QPainterPath
from models.edges import *
from PyQt6.QtGui import QPainter, QPen, QColor, QPainterPath

class Edge:
    def __init__(self, p1: Point, p2: Point, color: QColor = QColor(50, 50, 50), width: int = 1):
        self.p1 = p1
        self.p2 = p2
        self.color = color
        self.width = width

    @abstractmethod
    def draw(self, painter: QPainter):
        pass

class StraightEdge(Edge):
    def draw(self, painter: QPainter):
        painter.setPen(QPen(self.color, self.width))
        painter.drawLine(self.p1.to_qpointf(), self.p2.to_qpointf())