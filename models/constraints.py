from __future__ import annotations

import math
from abc import ABC, abstractmethod

from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QPainter, QPen, QColor, QFont

from models.point import Point


PARALLEL_PALETTE = [
    QColor(200, 50, 50),
    QColor(40, 150, 70),
    QColor(40, 90, 210),
    QColor(180, 120, 20),
    QColor(140, 50, 180),
    QColor(20, 150, 160),
    QColor(210, 80, 140),
    QColor(90, 90, 90),
]


def same_edge(a1: Point, a2: Point, b1: Point, b2: Point) -> bool:
    return (a1 is b1 and a2 is b2) or (a1 is b2 and a2 is b1)


def midpoint(p1: Point, p2: Point) -> tuple[float, float]:
    return (p1.x + p2.x) / 2, (p1.y + p2.y) / 2


def edge_length(p1: Point, p2: Point) -> float:
    return math.hypot(p1.x - p2.x, p1.y - p2.y)


def edge_normal(p1: Point, p2: Point) -> tuple[float, float]:
    dx, dy = p2.x - p1.x, p2.y - p1.y
    length = math.hypot(dx, dy)
    if length < 1e-9:
        return 0.0, -1.0
    return -dy / length, dx / length


class Constraint(ABC):
    @abstractmethod
    def involves_edge(self, p1: Point, p2: Point) -> bool:
        pass

    @abstractmethod
    def involves_point(self, point: Point) -> bool:
        pass

    @abstractmethod
    def is_satisfied(self, eps: float = 1e-3) -> bool:
        pass

    @abstractmethod
    def draw_icon(self, painter: QPainter) -> None:
        pass


class LengthConstraint(Constraint):
    def __init__(self, p1: Point, p2: Point, length: float):
        self.p1 = p1
        self.p2 = p2
        self.length = length

    def other(self, point: Point) -> Point:
        return self.p2 if point is self.p1 else self.p1

    def involves_edge(self, p1: Point, p2: Point) -> bool:
        return same_edge(self.p1, self.p2, p1, p2)

    def involves_point(self, point: Point) -> bool:
        return point is self.p1 or point is self.p2

    def current_length(self) -> float:
        return edge_length(self.p1, self.p2)

    def is_satisfied(self, eps: float = 1e-3) -> bool:
        return abs(self.current_length() - self.length) <= eps

    def draw_icon(self, painter: QPainter) -> None:
        mx, my = midpoint(self.p1, self.p2)
        nx, ny = edge_normal(self.p1, self.p2)
        cx, cy = mx + nx * 14, my + ny * 14
        painter.setPen(QPen(QColor(180, 90, 20)))
        painter.setFont(QFont("Sans Serif", 9))
        painter.drawText(QPointF(cx - 10, cy + 4), f"{self.length:.1f}")


class ParallelConstraint(Constraint):
    def __init__(self, a1: Point, a2: Point, b1: Point, b2: Point, color: QColor):
        self.a1 = a1
        self.a2 = a2
        self.b1 = b1
        self.b2 = b2
        self.color = color

    def involves_edge(self, p1: Point, p2: Point) -> bool:
        return same_edge(self.a1, self.a2, p1, p2) or same_edge(self.b1, self.b2, p1, p2)

    def involves_point(self, point: Point) -> bool:
        return point is self.a1 or point is self.a2 or point is self.b1 or point is self.b2

    def is_satisfied(self, eps: float = 1e-3) -> bool:
        ax, ay = self.a2.x - self.a1.x, self.a2.y - self.a1.y
        bx, by = self.b2.x - self.b1.x, self.b2.y - self.b1.y
        cross = ax * by - ay * bx
        la = math.hypot(ax, ay)
        lb = math.hypot(bx, by)
        if la < 1e-9 or lb < 1e-9:
            return True
        return abs(cross) <= eps * la * lb

    def draw_icon(self, painter: QPainter) -> None:
        pass


class ConstraintStore:
    def __init__(self):
        self.items: list[Constraint] = []

    def add(self, constraint: Constraint) -> None:
        if isinstance(constraint, LengthConstraint):
            self.items = [
                c for c in self.items
                if not (isinstance(c, LengthConstraint) and c.involves_edge(constraint.p1, constraint.p2))
            ]
        if isinstance(constraint, ParallelConstraint):
            for c in self.items:
                if isinstance(c, ParallelConstraint) and (
                    (same_edge(c.a1, c.a2, constraint.a1, constraint.a2)
                     and same_edge(c.b1, c.b2, constraint.b1, constraint.b2))
                    or (same_edge(c.a1, c.a2, constraint.b1, constraint.b2)
                        and same_edge(c.b1, c.b2, constraint.a1, constraint.a2))
                ):
                    return
        self.items.append(constraint)

    def remove(self, constraint: Constraint) -> None:
        if constraint in self.items:
            self.items.remove(constraint)

    def remove_for_edge(self, p1: Point, p2: Point) -> None:
        self.items = [c for c in self.items if not c.involves_edge(p1, p2)]

    def for_edge(self, p1: Point, p2: Point) -> list[Constraint]:
        return [c for c in self.items if c.involves_edge(p1, p2)]

    def parallels_for_edge(self, p1: Point, p2: Point) -> list[ParallelConstraint]:
        return [c for c in self.all_parallels() if c.involves_edge(p1, p2)]

    def all_lengths(self) -> list[LengthConstraint]:
        return [c for c in self.items if isinstance(c, LengthConstraint)]

    def all_parallels(self) -> list[ParallelConstraint]:
        return [c for c in self.items if isinstance(c, ParallelConstraint)]

    def next_parallel_color(self) -> QColor:
        return PARALLEL_PALETTE[len(self.all_parallels()) % len(PARALLEL_PALETTE)]
