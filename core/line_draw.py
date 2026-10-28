from __future__ import annotations

from enum import Enum, auto

from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QPainter, QPen, QColor


class LineAlgorithm(Enum):
    LIBRARY = auto()
    BRESENHAM = auto()


def bresenham_points(x0: int, y0: int, x1: int, y1: int):
    dx = abs(x1 - x0)
    dy = abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx - dy

    x, y = x0, y0
    while True:
        yield x, y
        if x == x1 and y == y1:
            break
        e2 = 2 * err
        if e2 > -dy:
            err -= dy
            x += sx
        if e2 < dx:
            err += dx
            y += sy


def draw_segment(
    painter: QPainter,
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    color: QColor,
    width: float = 1,
    algorithm: LineAlgorithm = LineAlgorithm.LIBRARY,
) -> None:
    if algorithm == LineAlgorithm.LIBRARY:
        painter.setPen(QPen(color, width))
        painter.drawLine(QPointF(x0, y0), QPointF(x1, y1))
        return

    aa = painter.testRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
    w = max(1, int(round(width)))
    painter.setPen(QPen(color, w))
    for x, y in bresenham_points(round(x0), round(y0), round(x1), round(y1)):
        painter.drawPoint(x, y)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, aa)
