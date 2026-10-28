from models.point import Point
from models.edges import Edge, StraightEdge, BezierEdge, ArcEdge
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QBrush, QColor, QPainter, QPen, QPolygonF
from core.line_draw import LineAlgorithm
from core.enums import Continuity
from models.continuity import enforce_continuity_at, recompute_all_arcs


class Polygon:

    def __init__(self, points: list[Point], fill_color: QColor = QColor(186, 186, 186, 20)):
        self.points = points
        self.fill_color = fill_color
        self.edges: list[Edge] = []
        n = len(points)
        for i in range(n):
            self.edges.append(StraightEdge(self.points[i], self.points[(i + 1) % n]))
        self.removed_edge: Edge | None = None

    def is_open(self) -> bool:
        return self.removed_edge is not None

    def remove_edge(self, edge: Edge) -> bool:
        if self.removed_edge is not None:
            return False
        if edge not in self.edges:
            return False
        if len(self.points) < 3:
            return False
        self.edges.remove(edge)
        self.removed_edge = edge
        return True

    def restore_edge(self) -> bool:
        if self.removed_edge is None:
            return False
        edge = self.removed_edge
        self.removed_edge = None
        if not any(p is edge.p1 for p in self.points) or not any(
            p is edge.p2 for p in self.points
        ):
            return False
        self.edges.append(edge)
        self._resort_edges()
        recompute_all_arcs(self.edges)
        return True

    def _resort_edges(self) -> None:
        order = {id(p): i for i, p in enumerate(self.points)}
        self.edges.sort(key=lambda e: order.get(id(e.p1), len(self.points)))

    def ordered_path_points(self) -> list[Point]:
        if self.removed_edge is None:
            return list(self.points)
        gap_next = self.removed_edge.p2
        for i, p in enumerate(self.points):
            if p is gap_next:
                return self.points[i:] + self.points[:i]
        return list(self.points)

    def move_by(self, dx: float, dy: float):
        moved: set[int] = set()
        for pt in self.points:
            if id(pt) in moved:
                continue
            moved.add(id(pt))
            pt.move_by(dx, dy)
        for edge in self.edges:
            for cp in edge.control_points():
                if id(cp) in moved:
                    continue
                moved.add(id(cp))
                cp.move_by(dx, dy)
        recompute_all_arcs(self.edges)

    def to_qpolygonf(self) -> QPolygonF:
        qpoly = QPolygonF()
        for edge in self.edges:
            if isinstance(edge, (BezierEdge, ArcEdge)):
                for x, y in edge.sample_points(48)[:-1]:
                    qpoly.append(QPointF(x, y))
            else:
                qpoly.append(edge.p1.to_qpointf())
        return qpoly

    def contains(self, x: float, y: float) -> bool:
        return self.to_qpolygonf().containsPoint(
            QPointF(x, y), Qt.FillRule.OddEvenFill
        )

    def rebuild_edges(self):
        old: dict[tuple[int, int], Edge] = {}
        for e in self.edges:
            old[(id(e.p1), id(e.p2))] = e

        gap_key = (
            (id(self.removed_edge.p1), id(self.removed_edge.p2))
            if self.removed_edge is not None
            else None
        )

        self.edges = []
        n = len(self.points)
        for i in range(n):
            p1 = self.points[i]
            p2 = self.points[(i + 1) % n]
            key = (id(p1), id(p2))
            if key == gap_key:
                continue
            prev = old.get(key)
            if isinstance(prev, (BezierEdge, ArcEdge)):
                self.edges.append(prev)
            else:
                self.edges.append(StraightEdge(p1, p2))
        recompute_all_arcs(self.edges)

    def can_remove_vertex(self) -> bool:
        return len(self.points) > 3

    def remove_vertex(self, point: Point) -> list[tuple[Point, Point]]:
        if not self.can_remove_vertex():
            return []
        for i, p in enumerate(self.points):
            if p is point:
                n = len(self.points)
                prev_pt = self.points[(i - 1) % n]
                next_pt = self.points[(i + 1) % n]
                removed = [(prev_pt, point), (point, next_pt)]

                merges_gap = self.removed_edge is not None and (
                    self.removed_edge.p1 is point or self.removed_edge.p2 is point
                )

                self.points.pop(i)

                if merges_gap:
                    self.removed_edge = StraightEdge(prev_pt, next_pt)

                self.rebuild_edges()
                return removed
        return []

    def add_vertex_on_edge(self, edge: Edge) -> tuple[Point | None, tuple[Point, Point] | None]:
        if edge not in self.edges:
            return None, None
        removed = (edge.p1, edge.p2)
        if isinstance(edge, (BezierEdge, ArcEdge)):
            pts = edge.sample_points(2)
            mid = Point(pts[1][0], pts[1][1])
        else:
            mid = Point((edge.p1.x + edge.p2.x) / 2, (edge.p1.y + edge.p2.y) / 2)
        idx = next(i for i, p in enumerate(self.points) if p is edge.p1)
        self.points.insert(idx + 1, mid)
        self.rebuild_edges()
        return mid, removed

    def set_edge_bezier(self, edge: Edge) -> BezierEdge | None:
        for i, e in enumerate(self.edges):
            if e is edge:
                if isinstance(e, BezierEdge):
                    return e
                bezier = BezierEdge(e.p1, e.p2, color=e.color, width=e.width)
                self.edges[i] = bezier
                for v in (e.p1, e.p2):
                    if not v.continuity_explicit:
                        v.continuity = Continuity.G1
                enforce_continuity_at(self.edges, e.p1)
                enforce_continuity_at(self.edges, e.p2)
                return bezier
        return None

    def set_edge_arc(self, edge: Edge) -> ArcEdge | None:
        for i, e in enumerate(self.edges):
            if e is edge:
                if isinstance(e, ArcEdge):
                    return e
                for v in (e.p1, e.p2):
                    if not v.continuity_explicit:
                        v.continuity = Continuity.G0
                arc = ArcEdge(e.p1, e.p2, color=e.color, width=e.width)
                arc.ensure_single_g1()
                self.edges[i] = arc
                recompute_all_arcs(self.edges)
                enforce_continuity_at(self.edges, e.p1)
                enforce_continuity_at(self.edges, e.p2)
                return arc
        return None

    def set_edge_straight(self, edge: Edge) -> StraightEdge | None:
        for i, e in enumerate(self.edges):
            if e is edge:
                if isinstance(e, StraightEdge):
                    return e
                straight = StraightEdge(e.p1, e.p2, color=e.color, width=e.width)
                self.edges[i] = straight
                return straight
        return None

    def draw(self, painter: QPainter, algorithm: LineAlgorithm = LineAlgorithm.LIBRARY):
        if not self.is_open():
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(self.fill_color))
            painter.drawPolygon(self.to_qpolygonf())

        for edge in self.edges:
            edge.draw(painter, algorithm)

        for edge in self.edges:
            if isinstance(edge, BezierEdge):
                edge.draw_controls(painter, algorithm)
