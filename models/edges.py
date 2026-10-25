import math
from abc import ABC, abstractmethod

from models.point import Point
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPainter, QColor, QPen
from core.line_draw import LineAlgorithm, draw_segment
from core.bezier_math import cubic_forward_points
from core.arc_math import (
    semicircle_geometry,
    arc_from_tangent,
    sample_arc,
    tangent_on_arc,
)
from core.enums import Continuity


class Edge(ABC):
    def __init__(self, p1: Point, p2: Point, color: QColor = QColor(50, 50, 50), width: int = 1):
        self.p1 = p1
        self.p2 = p2
        self.color = color
        self.width = width
        
    def has_point(self, point: Point) -> bool:
        """Sprawdza, czy ta krawędź jest podpięta pod dany punkt."""
        return self.p1 is point or self.p2 is point

    def length(self) -> float:
        return math.hypot(self.p1.x - self.p2.x, self.p1.y - self.p2.y)

    def control_points(self) -> list[Point]:
        return []
    
    @abstractmethod
    def draw(self, painter: QPainter, algorithm: LineAlgorithm = LineAlgorithm.LIBRARY):
        pass


class StraightEdge(Edge):
    def draw(self, painter: QPainter, algorithm: LineAlgorithm = LineAlgorithm.LIBRARY):
        draw_segment(
            painter,
            self.p1.x,
            self.p1.y,
            self.p2.x,
            self.p2.y,
            self.color,
            self.width,
            algorithm,
        )


class BezierEdge(Edge):
    def __init__(
        self,
        p1: Point,
        p2: Point,
        c1: Point | None = None,
        c2: Point | None = None,
        color: QColor = QColor(50, 50, 50),
        width: int = 1,
    ):
        super().__init__(p1, p2, color, width)
        if c1 is None:
            self.c1 = Point(
                (2 * p1.x + p2.x) / 3,
                (2 * p1.y + p2.y) / 3,
                is_control=True,
            )
        else:
            self.c1 = c1
            self.c1.is_control = True
        if c2 is None:
            self.c2 = Point(
                (p1.x + 2 * p2.x) / 3,
                (p1.y + 2 * p2.y) / 3,
                is_control=True,
            )
        else:
            self.c2 = c2
            self.c2.is_control = True

    def control_points(self) -> list[Point]:
        return [self.c1, self.c2]

    def sample_points(self, steps: int = 64) -> list[tuple[float, float]]:
        return cubic_forward_points(
            (self.p1.x, self.p1.y),
            (self.c1.x, self.c1.y),
            (self.c2.x, self.c2.y),
            (self.p2.x, self.p2.y),
            steps,
        )

    def draw(self, painter: QPainter, algorithm: LineAlgorithm = LineAlgorithm.LIBRARY):
        # mniej próbek = płynniejszy paint; jakość nadal wystarczająca
        pts = self.sample_points(32)
        for i in range(len(pts) - 1):
            draw_segment(
                painter,
                pts[i][0],
                pts[i][1],
                pts[i + 1][0],
                pts[i + 1][1],
                self.color,
                self.width,
                algorithm,
            )

    def draw_controls(self, painter: QPainter, algorithm: LineAlgorithm = LineAlgorithm.LIBRARY):
        pen = QPen(QColor(160, 160, 160), 1, Qt.PenStyle.DashLine)
        painter.setPen(pen)
        if algorithm == LineAlgorithm.LIBRARY:
            painter.drawLine(self.p1.to_qpointf(), self.c1.to_qpointf())
            painter.drawLine(self.c1.to_qpointf(), self.c2.to_qpointf())
            painter.drawLine(self.c2.to_qpointf(), self.p2.to_qpointf())
        else:
            draw_segment(painter, self.p1.x, self.p1.y, self.c1.x, self.c1.y, QColor(160, 160, 160), 1, algorithm)
            draw_segment(painter, self.c1.x, self.c1.y, self.c2.x, self.c2.y, QColor(160, 160, 160), 1, algorithm)
            draw_segment(painter, self.c2.x, self.c2.y, self.p2.x, self.p2.y, QColor(160, 160, 160), 1, algorithm)


class ArcEdge(Edge):
    """
    Łuk okręgu przez p1→p2.
    Geometria: oba G0 → R = |p1p2|/2; jeden koniec G1 → styczna z sąsiada.
    """

    def __init__(
        self,
        p1: Point,
        p2: Point,
        color: QColor = QColor(50, 50, 50),
        width: int = 1,
        side: int = 1,
    ):
        super().__init__(p1, p2, color, width)
        self.side = 1 if side >= 0 else -1
        self._geom: tuple[float, float, float, float, float] | None = None

    def g1_endpoint(self) -> Point | None:
        g1_1 = self.p1.continuity == Continuity.G1
        g1_2 = self.p2.continuity == Continuity.G1
        if g1_1 and g1_2:
            return self.p1
        if g1_1:
            return self.p1
        if g1_2:
            return self.p2
        return None

    def ensure_single_g1(self) -> None:
        """Co najwyżej jeden koniec łuku ma G1 — drugi spada do G0."""
        if (
            self.p1.continuity == Continuity.G1
            and self.p2.continuity == Continuity.G1
        ):
            self.p2.continuity = Continuity.G0
            self.p2.continuity_explicit = True

    def recompute(self, neighbor_tangent: tuple[float, float] | None = None) -> bool:
        """
        Przelicza (cx,cy,r,a0,a1).
        neighbor_tangent — jednostkowa styczna na końcu z G1 (kierunek podróży).
        """
        self.ensure_single_g1()
        p1 = (self.p1.x, self.p1.y)
        p2 = (self.p2.x, self.p2.y)
        g1 = self.g1_endpoint()

        if g1 is None:
            self._geom = semicircle_geometry(p1, p2, self.side)
        elif neighbor_tangent is not None:
            self._geom = arc_from_tangent(
                p1, p2, neighbor_tangent, at_p1=(g1 is self.p1)
            )
        else:
            self._geom = semicircle_geometry(p1, p2, self.side)

        return self._geom is not None

    def geometry(self) -> tuple[float, float, float, float, float] | None:
        if self._geom is None:
            self.recompute()
        return self._geom

    def sample_points(self, steps: int = 64) -> list[tuple[float, float]]:
        g = self.geometry()
        if g is None:
            return [(self.p1.x, self.p1.y), (self.p2.x, self.p2.y)]
        cx, cy, r, a0, a1 = g
        return sample_arc(cx, cy, r, a0, a1, steps)

    def unit_tangent_at(self, vertex: Point) -> tuple[float, float] | None:
        g = self.geometry()
        if g is None:
            return None
        _, _, _, a0, a1 = g
        if vertex is self.p1:
            return tangent_on_arc(a0, a1, at_start=True)
        if vertex is self.p2:
            return tangent_on_arc(a0, a1, at_start=False)
        return None

    def draw(self, painter: QPainter, algorithm: LineAlgorithm = LineAlgorithm.LIBRARY):
        pts = self.sample_points(32)
        for i in range(len(pts) - 1):
            draw_segment(
                painter,
                pts[i][0],
                pts[i][1],
                pts[i + 1][0],
                pts[i + 1][1],
                self.color,
                self.width,
                algorithm,
            )
