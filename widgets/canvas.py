from PyQt6.QtWidgets import QWidget, QMenu, QInputDialog, QMessageBox
from PyQt6.QtGui import QPainter, QPen, QBrush, QColor, QImage
from PyQt6.QtCore import Qt, QPointF
from models import Point, Edge, BezierEdge, ArcEdge
from models.polygon import Polygon
from models.constraints import (
    ConstraintStore,
    LengthConstraint,
    ParallelConstraint,
    same_edge,
)
from models.solver import ConstraintSolver, snapshot_positions, restore_positions
from models.demo_scene import build_polygons, apply_demo_relations
from models.continuity import (
    sync_bezier_handles_from_snap,
    vertex_has_curve_neighbor,
    vertex_has_bezier_neighbor,
    bezier_for_control,
    clear_other_arc_g1,
    arc_g1_conflicts,
    incident_arcs,
    enforce_after_move,
    recompute_all_arcs,
)
from core.line_draw import LineAlgorithm, draw_segment
from core.enums import Continuity
from core.bspline_construct import build_cubic_bspline
from core.bezier_math import cubic_forward_points


def _id_to_color(pid: int) -> QColor:
    return QColor(pid & 255, (pid >> 8) & 255, (pid >> 16) & 255)


def _color_to_id(c: QColor) -> int:
    if c.red() == 0 and c.green() == 0 and c.blue() == 0:
        return 0
    return c.red() | (c.green() << 8) | (c.blue() << 16)


class Canvas(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.polygons = build_polygons()

        self.dragged_point: Point | None = None
        self.dragged_polygon: Polygon | None = None
        self.last_mouse_pos: QPointF | None = None

        self.hovered_point: Point | None = None
        self.hit_radius: float = 9.0

        self._pick_img: QImage | None = None
        self._pick_map: dict[int, Point | Polygon | Edge] = {}
        self._pick_dirty = True

        self.selected_edges: list[tuple[Point, Point]] = []
        self._parallel_from: tuple[Point, Point] | None = None

        self.constraints = ConstraintStore()
        self.solver = ConstraintSolver(self.constraints)
        apply_demo_relations(self.polygons, self.solver)

        self._drag_snap: dict[int, tuple[float, float]] | None = None
        self._drag_origin: tuple[float, float] | None = None

        self.show_grid = False
        self.line_algorithm = LineAlgorithm.LIBRARY
        self._dragging_control = False

        self.show_bspline = False
        self.show_bspline_helpers = False

        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def set_line_algorithm(self, algorithm: LineAlgorithm) -> None:
        self.line_algorithm = algorithm
        self.update()

    def set_show_bspline(self, on: bool) -> None:
        self.show_bspline = on
        self.update()

    def set_show_bspline_helpers(self, on: bool) -> None:
        self.show_bspline_helpers = on
        self.update()

    def restore_all_edges(self) -> None:
        for poly in self.polygons:
            poly.restore_edge()
        self.solver.propagate_repair(self.polygons)
        self._pick_dirty = True
        self.update()

    def resizeEvent(self, event):
        self._pick_dirty = True
        super().resizeEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_G:
            self.show_grid = not self.show_grid
            self.update()
            return
        if event.key() == Qt.Key.Key_Escape:
            self._parallel_from = None
            self.update()
            return
        super().keyPressEvent(event)

    def _draw_grid(self, painter: QPainter) -> None:
        w, h = self.width(), self.height()
        painter.setPen(QPen(QColor(230, 230, 230), 1))
        for x in range(0, w + 1, 10):
            painter.drawLine(x, 0, x, h)
        for y in range(0, h + 1, 10):
            painter.drawLine(0, y, w, y)
        painter.setPen(QPen(QColor(190, 190, 190), 1.5))
        for x in range(0, w + 1, 100):
            painter.drawLine(x, 0, x, h)
        for y in range(0, h + 1, 100):
            painter.drawLine(0, y, w, y)

    def _edge_selected(self, edge: Edge) -> bool:
        for a, b in self.selected_edges:
            if same_edge(a, b, edge.p1, edge.p2):
                return True
        return False

    def _is_parallel_from(self, edge: Edge) -> bool:
        if self._parallel_from is None:
            return False
        a, b = self._parallel_from
        return same_edge(a, b, edge.p1, edge.p2)

    def _select_edge(self, edge: Edge) -> None:
        self.selected_edges = [(edge.p1, edge.p2)]

    def _drop_constraints_for_edges(self, pairs: list[tuple[Point, Point]]) -> None:
        for p1, p2 in pairs:
            self.constraints.remove_for_edge(p1, p2)
            self.selected_edges = [
                (a, b) for a, b in self.selected_edges if not same_edge(a, b, p1, p2)
            ]
            if self._parallel_from is not None and same_edge(self._parallel_from[0], self._parallel_from[1], p1, p2):
                self._parallel_from = None

    def _draw_parallel_edge_colors(self, painter: QPainter) -> None:
        for poly in self.polygons:
            for edge in poly.edges:
                parallels = self.constraints.parallels_for_edge(edge.p1, edge.p2)
                if not parallels:
                    continue
                n = len(parallels)
                if isinstance(edge, (BezierEdge, ArcEdge)):
                    pts = edge.sample_points(48)
                    chunk = max(1, len(pts) // n)
                    for i, pc in enumerate(parallels):
                        a = i * chunk
                        b = len(pts) - 1 if i == n - 1 else min(len(pts) - 1, (i + 1) * chunk)
                        for j in range(a, b):
                            draw_segment(
                                painter,
                                pts[j][0], pts[j][1], pts[j + 1][0], pts[j + 1][1],
                                pc.color, 2.5, self.line_algorithm,
                            )
                else:
                    x1, y1 = edge.p1.x, edge.p1.y
                    x2, y2 = edge.p2.x, edge.p2.y
                    for i, pc in enumerate(parallels):
                        t0 = i / n
                        t1 = (i + 1) / n
                        draw_segment(
                            painter,
                            x1 + (x2 - x1) * t0,
                            y1 + (y2 - y1) * t0,
                            x1 + (x2 - x1) * t1,
                            y1 + (y2 - y1) * t1,
                            pc.color,
                            2.5,
                            self.line_algorithm,
                        )

    def _rebuild_pick_buffer(self):
        dpr = self.devicePixelRatioF()
        w = max(1, int(self.width() * dpr))
        h = max(1, int(self.height() * dpr))
        img = QImage(w, h, QImage.Format.Format_RGB32)
        img.fill(QColor(0, 0, 0))

        painter = QPainter(img)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        painter.scale(dpr, dpr)

        self._pick_map = {}
        next_id = 1
        seen: set[int] = set()

        painter.setPen(Qt.PenStyle.NoPen)
        for poly in self.polygons:
            self._pick_map[next_id] = poly
            painter.setBrush(QBrush(_id_to_color(next_id)))
            painter.drawPolygon(poly.to_qpolygonf())
            next_id += 1

        painter.setBrush(Qt.BrushStyle.NoBrush)
        for poly in self.polygons:
            for edge in poly.edges:
                self._pick_map[next_id] = edge
                painter.setPen(QPen(_id_to_color(next_id), self.hit_radius * 2))
                if isinstance(edge, (BezierEdge, ArcEdge)):
                    pts = edge.sample_points(32)
                    for i in range(len(pts) - 1):
                        painter.drawLine(
                            QPointF(pts[i][0], pts[i][1]),
                            QPointF(pts[i + 1][0], pts[i + 1][1]),
                        )
                else:
                    painter.drawLine(edge.p1.to_qpointf(), edge.p2.to_qpointf())
                next_id += 1

        painter.setPen(Qt.PenStyle.NoPen)
        for poly in self.polygons:
            for edge in poly.edges:
                for cp in edge.control_points():
                    if id(cp) in seen:
                        continue
                    seen.add(id(cp))
                    self._pick_map[next_id] = cp
                    painter.setBrush(QBrush(_id_to_color(next_id)))
                    painter.drawEllipse(cp.to_qpointf(), self.hit_radius, self.hit_radius)
                    next_id += 1

        for poly in self.polygons:
            for pt in poly.points:
                if id(pt) in seen:
                    continue
                seen.add(id(pt))
                self._pick_map[next_id] = pt
                painter.setBrush(QBrush(_id_to_color(next_id)))
                painter.drawEllipse(pt.to_qpointf(), self.hit_radius, self.hit_radius)
                next_id += 1

        painter.end()
        self._pick_img = img
        self._pick_dirty = False

    def pick_at(self, x: float, y: float) -> Point | Polygon | Edge | None:
        if self._pick_dirty or self._pick_img is None:
            self._rebuild_pick_buffer()
        dpr = self.devicePixelRatioF()
        px = int(x * dpr)
        py = int(y * dpr)
        if px < 0 or py < 0 or px >= self._pick_img.width() or py >= self._pick_img.height():
            return None
        return self._pick_map.get(_color_to_id(self._pick_img.pixelColor(px, py)))

    def _polygon_for_point(self, point: Point) -> Polygon | None:
        for poly in reversed(self.polygons):
            if any(p is point for p in poly.points):
                return poly
        return None

    def _polygon_for_edge(self, edge: Edge) -> Polygon | None:
        for poly in reversed(self.polygons):
            if any(e is edge for e in poly.edges):
                return poly
        return None

    def _update_hover_cursor(self, x: float, y: float):
        obj = self.pick_at(x, y)
        self.hovered_point = obj if isinstance(obj, Point) else None
        if isinstance(obj, Point):
            self.setCursor(Qt.CursorShape.OpenHandCursor)
        elif isinstance(obj, Edge):
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        elif isinstance(obj, Polygon):
            self.setCursor(Qt.CursorShape.SizeAllCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)

    def _translate_poly_of(
        self,
        pt: Point,
        tx: float,
        ty: float,
        snap: dict[int, tuple[float, float]],
        origin: tuple[float, float],
        polys: list[Polygon] | None = None,
    ) -> None:
        restore_positions(self.polygons, snap)
        dx = tx - origin[0]
        dy = ty - origin[1]
        if polys is not None:
            targets = polys
        else:
            targets = [
                poly
                for poly in self.polygons
                if any(p is pt for p in poly.points)
                or any(pt is cp for e in poly.edges for cp in e.control_points())
            ]
        moved: set[int] = set()
        for poly in targets:
            for p in poly.points:
                if id(p) in moved:
                    continue
                moved.add(id(p))
                ox, oy = snap[id(p)]
                p.move_to(ox + dx, oy + dy)
            for edge in poly.edges:
                for p in edge.control_points():
                    if id(p) in moved:
                        continue
                    moved.add(id(p))
                    ox, oy = snap[id(p)]
                    p.move_to(ox + dx, oy + dy)
        pt.move_to(tx, ty)
        for poly in self.polygons:
            recompute_all_arcs(poly.edges)

    def _try_repair_at(
        self,
        pt: Point,
        tx: float,
        ty: float,
        *,
        pinned_extra: set[int] | None = None,
        prefer_adjust: Point | None = None,
        interactive: bool = True,
    ) -> bool:
        if self._drag_snap is None:
            return False
        snap = self._drag_snap
        pinned = {id(pt)} | set(pinned_extra or set())
        pt.move_to(tx, ty)
        for poly in self.polygons:
            sync_bezier_handles_from_snap(poly.edges, snap, pinned=pinned)
        pt.move_to(tx, ty)

        for poly in self.polygons:
            if prefer_adjust is not None and (
                any(p is prefer_adjust for p in poly.points)
                or any(
                    prefer_adjust is h
                    for e in poly.edges
                    for h in e.control_points()
                )
            ):
                enforce_after_move(
                    poly.edges, prefer_adjust, pinned=pinned
                )
        pt.move_to(tx, ty)

        self.solver.propagate_repair(
            self.polygons,
            pinned=pinned,
            seeds=[pt],
            prefer_adjust=prefer_adjust or pt,
            interactive=interactive,
        )
        pt.move_to(tx, ty)
        return self.solver.scene_ok(self.polygons)

    def _propagate_after_drag(
        self,
        pt: Point,
        tx: float,
        ty: float,
        *,
        prefer_adjust: Point | None = None,
        pinned_extra: set[int] | None = None,
        allow_translate: bool = True,
        seeds: list[Point] | None = None,
        interactive: bool = True,
    ) -> None:
        if self._drag_snap is None or self._drag_origin is None:
            return
        prefer = prefer_adjust or pt
        extras = [set(pinned_extra or set())]
        modes = [True, False] if interactive else [False]
        for mode in modes:
            for extra in extras:
                restore_positions(self.polygons, self._drag_snap)
                if self._try_repair_at(
                    pt,
                    tx,
                    ty,
                    pinned_extra=extra,
                    prefer_adjust=prefer,
                    interactive=mode,
                ):
                    return
        if allow_translate:
            self._translate_poly_of(pt, tx, ty, self._drag_snap, self._drag_origin)

    def _apply_continuity_after_vertex_drag(self, tx: float, ty: float) -> None:
        if self.dragged_point is None:
            return
        self._propagate_after_drag(self.dragged_point, tx, ty)

    def _drag_control_point(self, tx: float, ty: float, *, interactive: bool = True) -> None:
        cp = self.dragged_point
        snap = self._drag_snap
        origin = self._drag_origin
        if cp is None or snap is None or origin is None:
            return

        owner: BezierEdge | None = None
        for poly in self.polygons:
            owner = bezier_for_control(poly.edges, cp)
            if owner is not None:
                break

        ends: set[int] = set()
        near_end: set[int] = set()
        if owner is not None:
            ends = {id(owner.p1), id(owner.p2)}
            if cp is owner.c1:
                near_end = {id(owner.p1)}
            elif cp is owner.c2:
                near_end = {id(owner.p2)}
            else:
                near_end = set(ends)

        pin_levels: list[set[int]] = []
        for extra in (ends, near_end, set()):
            key = frozenset(extra)
            if any(frozenset(e) == key for e in pin_levels):
                continue
            pin_levels.append(extra)

        modes = [True, False] if interactive else [False]
        for mode in modes:
            for extra in pin_levels:
                restore_positions(self.polygons, snap)
                if self._try_repair_at(
                    cp, tx, ty, pinned_extra=extra, prefer_adjust=cp, interactive=mode
                ):
                    return

        self._translate_poly_of(cp, tx, ty, snap, origin)

    def _set_vertex_continuity(self, point: Point, continuity: Continuity) -> None:
        if point.continuity == continuity and point.continuity_explicit:
            return

        needs_arc_g1_clear = continuity in (Continuity.G1, Continuity.C1)
        conflicts: list[Point] = []
        if needs_arc_g1_clear:
            for poly in self.polygons:
                if any(p is point for p in poly.points):
                    conflicts.extend(arc_g1_conflicts(poly.edges, point))

        if conflicts:
            n_arcs = 0
            for poly in self.polygons:
                if any(p is point for p in poly.points):
                    n_arcs += len(incident_arcs(poly.edges, point))
            msg = (
                "Na drugim końcu łuku jest już ciągłość G1.\n\n"
                "Ustawienie G1 na tym wierzchołku usunie G1 z drugiego końca "
                "(na każdym łuku może być tylko jeden koniec z G1).\n"
                "G1 na tym wierzchołku będzie obowiązywać dla wszystkich "
                f"incydentnych łuków ({n_arcs}).\n\n"
                "Czy na pewno chcesz kontynuować?"
            )
            reply = QMessageBox.question(
                self,
                "Ciągłość G1 na łuku",
                msg,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        point.continuity = continuity
        point.continuity_explicit = True
        if needs_arc_g1_clear:
            for poly in self.polygons:
                if any(p is point for p in poly.points):
                    clear_other_arc_g1(poly.edges, point)

        self.solver.propagate_repair(
            self.polygons,
            seeds=[point],
            prefer_adjust=point,
        )
        self._pick_dirty = True
        self.update()

    def _set_edge_length(self, edge: Edge) -> None:
        if isinstance(edge, (BezierEdge, ArcEdge)):
            return
        current = edge.length()
        value, ok = QInputDialog.getDouble(
            self,
            "Długość krawędzi",
            "Zadana długość:",
            current,
            0.01,
            100000.0,
            2,
        )
        if not ok:
            return
        if not self.solver.try_add_length(edge.p1, edge.p2, value, self.polygons):
            QMessageBox.warning(
                self,
                "Ograniczenie",
                "Nie można dodać tego ograniczenia — wyklucza się z już istniejącymi.",
            )
            return
        self._pick_dirty = True
        self.update()

    def _handle_parallel_action(self, edge: Edge) -> None:
        if isinstance(edge, (BezierEdge, ArcEdge)):
            return
        key = (edge.p1, edge.p2)
        if self._parallel_from is None:
            self._parallel_from = key
            self.update()
            return

        a1, a2 = self._parallel_from
        if same_edge(a1, a2, edge.p1, edge.p2):
            self._parallel_from = None
            self.update()
            return

        ok = self.solver.try_add_parallel(a1, a2, edge.p1, edge.p2, self.polygons)
        self._parallel_from = None
        if not ok:
            QMessageBox.warning(
                self,
                "Ograniczenie",
                "Nie można dodać równoległości — wyklucza się z już istniejącymi.",
            )
        self._pick_dirty = True
        self.update()

    def contextMenuEvent(self, event):
        pos = event.pos()
        obj = self.pick_at(pos.x(), pos.y())
        menu = QMenu(self)

        if isinstance(obj, Point) and not obj.is_control:
            poly = self._polygon_for_point(obj)
            action_remove = menu.addAction("Usuń wierzchołek")
            action_remove.setEnabled(poly is not None and poly.can_remove_vertex())

            cont_actions = []
            if poly is not None and vertex_has_curve_neighbor(poly.edges, obj):
                cont_menu = menu.addMenu("Zmień ciągłość")
                options = [(Continuity.G0, "G0"), (Continuity.G1, "G1")]
                if vertex_has_bezier_neighbor(poly.edges, obj):
                    options.append((Continuity.C1, "C1"))
                for cont, label in options:
                    act = cont_menu.addAction(label)
                    act.setCheckable(True)
                    act.setChecked(obj.continuity == cont)
                    cont_actions.append((act, cont))

            chosen = menu.exec(event.globalPos())
            if chosen == action_remove and poly is not None:
                removed = poly.remove_vertex(obj)
                self._drop_constraints_for_edges(removed)
                self._pick_dirty = True
                self.update()
            else:
                for act, cont in cont_actions:
                    if chosen == act:
                        self._set_vertex_continuity(obj, cont)
                        break
            return

        if isinstance(obj, Edge):
            poly = self._polygon_for_edge(obj)
            self._select_edge(obj)

            action_add = menu.addAction("Dodaj wierzchołek")

            type_menu = menu.addMenu("Typ krzywej")
            action_straight = type_menu.addAction("Odcinek")
            action_bezier = type_menu.addAction("Krzywa Béziera")
            action_arc = type_menu.addAction("Łuk okręgu")
            action_straight.setCheckable(True)
            action_bezier.setCheckable(True)
            action_arc.setCheckable(True)
            action_straight.setChecked(not isinstance(obj, (BezierEdge, ArcEdge)))
            action_bezier.setChecked(isinstance(obj, BezierEdge))
            action_arc.setChecked(isinstance(obj, ArcEdge))

            menu.addSeparator()
            action_remove_edge = menu.addAction("Usuń krawędź (wielokąt otwarty)")
            action_remove_edge.setEnabled(poly is not None and not poly.is_open())

            action_length = None
            action_parallel = None
            action_clear = None
            remove_actions: list[tuple] = []

            if not isinstance(obj, (BezierEdge, ArcEdge)):
                action_length = menu.addAction("Zadaj długość...")

                if self._parallel_from is None:
                    action_parallel = menu.addAction("Dodaj równoległość")
                elif self._is_parallel_from(obj):
                    action_parallel = menu.addAction("Anuluj wybór równoległości")
                else:
                    action_parallel = menu.addAction("Dodaj równoległość z wybraną krawędzią")

                edge_constraints = self.constraints.for_edge(obj.p1, obj.p2)
                action_clear = menu.addAction("Usuń ograniczenia z krawędzi")
                action_clear.setEnabled(len(edge_constraints) > 0)

                if edge_constraints:
                    menu.addSeparator()
                    for c in edge_constraints:
                        if isinstance(c, LengthConstraint):
                            label = f"Usuń długość ({c.length:.1f})"
                        elif isinstance(c, ParallelConstraint):
                            label = "Usuń równoległość"
                        else:
                            label = "Usuń ograniczenie"
                        remove_actions.append((menu.addAction(label), c))

            chosen = menu.exec(event.globalPos())
            if chosen == action_add and poly is not None:
                _mid, removed = poly.add_vertex_on_edge(obj)
                if removed is not None:
                    self._drop_constraints_for_edges([removed])
                self._pick_dirty = True
                self.update()
            elif chosen == action_straight and poly is not None:
                poly.set_edge_straight(obj)
                self._pick_dirty = True
                self.update()
            elif chosen == action_bezier and poly is not None:
                self._drop_constraints_for_edges([(obj.p1, obj.p2)])
                poly.set_edge_bezier(obj)
                self.solver.propagate_repair(self.polygons)
                self._pick_dirty = True
                self.update()
            elif chosen == action_arc and poly is not None:
                self._drop_constraints_for_edges([(obj.p1, obj.p2)])
                poly.set_edge_arc(obj)
                self.solver.propagate_repair(self.polygons)
                self._pick_dirty = True
                self.update()
            elif chosen == action_remove_edge and poly is not None:
                if poly.remove_edge(obj):
                    self.constraints.remove_for_edge(obj.p1, obj.p2)
                    self.selected_edges = [
                        (a, b)
                        for a, b in self.selected_edges
                        if not same_edge(a, b, obj.p1, obj.p2)
                    ]
                    if self._parallel_from is not None and same_edge(
                        self._parallel_from[0], self._parallel_from[1], obj.p1, obj.p2
                    ):
                        self._parallel_from = None
                    self.solver.propagate_repair(self.polygons)
                    self._pick_dirty = True
                    self.update()
            elif action_length is not None and chosen == action_length:
                self._set_edge_length(obj)
            elif action_parallel is not None and chosen == action_parallel:
                self._handle_parallel_action(obj)
            elif action_clear is not None and chosen == action_clear:
                self.constraints.remove_for_edge(obj.p1, obj.p2)
                self.update()
            else:
                for action, constraint in remove_actions:
                    if chosen == action:
                        self.constraints.remove(constraint)
                        self.update()
                        break
            return

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.position()
            obj = self.pick_at(pos.x(), pos.y())

            if isinstance(obj, Point):
                self.selected_edges.clear()
                self.dragged_point = obj
                self._dragging_control = obj.is_control
                self._drag_snap = snapshot_positions(self.polygons)
                self._drag_origin = (obj.x, obj.y)
                self.setCursor(Qt.CursorShape.ClosedHandCursor)
                self.update()
                return

            if isinstance(obj, Edge):
                self._select_edge(obj)
                self.update()
                return

            if isinstance(obj, Polygon):
                self.selected_edges.clear()
                self.dragged_polygon = obj
                self.last_mouse_pos = pos
                self.setCursor(Qt.CursorShape.SizeAllCursor)
                self.update()
                return

            self.selected_edges.clear()
            self.update()

    def mouseMoveEvent(self, event):
            pos = event.position()

            if (
                self.dragged_point is not None
                and self._dragging_control
                and self._drag_snap is not None
                and self._drag_origin is not None
            ):
                self._drag_control_point(pos.x(), pos.y())
                self.update()
                return

            if self.dragged_point is not None and self._drag_snap is not None and self._drag_origin is not None:
                self._propagate_after_drag(
                    self.dragged_point, pos.x(), pos.y(), interactive=True
                )
                self.update()
                return

            if self.dragged_polygon is not None and self.last_mouse_pos is not None:
                dx = pos.x() - self.last_mouse_pos.x()
                dy = pos.y() - self.last_mouse_pos.y()
                self.dragged_polygon.move_by(dx, dy)
                self.last_mouse_pos = pos
                self.update()
                return

            prev = self.hovered_point
            self._update_hover_cursor(pos.x(), pos.y())

            if self.hovered_point is not prev:
                self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if (
                self.dragged_point is not None
                and self._drag_snap is not None
                and self._drag_origin is not None
            ):
                pt = self.dragged_point
                tx, ty = pt.x, pt.y
                if self._dragging_control:
                    self._drag_control_point(tx, ty, interactive=False)
                else:
                    self._propagate_after_drag(pt, tx, ty, interactive=False)

            self.dragged_point = None
            self.dragged_polygon = None
            self.last_mouse_pos = None
            self._drag_snap = None
            self._drag_origin = None
            self._dragging_control = False
            self._pick_dirty = True

            pos = event.position()
            self._update_hover_cursor(pos.x(), pos.y())
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.fillRect(self.rect(), Qt.GlobalColor.white)

        if self.show_grid:
            self._draw_grid(painter)

        for polygon in self.polygons:
            polygon.draw(painter, self.line_algorithm)

        self._draw_parallel_edge_colors(painter)

        for polygon in self.polygons:
            for edge in polygon.edges:
                for cp in edge.control_points():
                    cp.draw(painter, radius=2.0, is_active=cp is self.dragged_point)
            for pt in polygon.points:
                pt.draw(painter, radius=2.0, is_active=pt is self.dragged_point)

        for poly in self.polygons:
            for edge in poly.edges:
                color = None
                width = 2.5
                if self._is_parallel_from(edge):
                    color, width = QColor(220, 120, 20), 3
                elif self._edge_selected(edge):
                    color, width = QColor(40, 110, 220), 2.5
                if color is None:
                    continue
                if isinstance(edge, (BezierEdge, ArcEdge)):
                    pts = edge.sample_points(48)
                    for i in range(len(pts) - 1):
                        draw_segment(
                            painter, pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1],
                            color, width, self.line_algorithm,
                        )
                else:
                    draw_segment(
                        painter, edge.p1.x, edge.p1.y, edge.p2.x, edge.p2.y,
                        color, width, self.line_algorithm,
                    )

        for constraint in self.constraints.items:
            constraint.draw_icon(painter)

        if self.show_bspline:
            self._draw_bsplines(painter)

    def _draw_bsplines(self, painter: QPainter) -> None:
        helper_color = QColor(140, 230, 120)
        control_poly_pen = QPen(QColor(150, 150, 150), 1, Qt.PenStyle.DashLine)
        hue_i = 0

        for poly in self.polygons:
            if len(poly.points) < 3:
                continue
            if poly.is_open() and len(poly.points) <= 3:
                continue
            vertices = [(p.x, p.y) for p in poly.ordered_path_points()]
            construction = build_cubic_bspline(vertices, closed=not poly.is_open())

            helper_points: list[tuple[float, float]] = []
            seen: set[tuple[float, float]] = set()

            for p0, c1, c2, p3 in construction.segments:
                hue = 200 + (hue_i * 47) % 131
                sat = 180 + ((hue_i // 131) * 37) % 76
                val = 210 + ((hue_i // 131) * 19) % 46
                hue_i += 1
                seg_color = QColor.fromHsv(hue, sat, val)
                pts = cubic_forward_points(p0, c1, c2, p3, 32)
                for i in range(len(pts) - 1):
                    draw_segment(
                        painter,
                        pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1],
                        seg_color, 2.0, self.line_algorithm,
                    )

                if self.show_bspline_helpers:
                    painter.setPen(control_poly_pen)
                    painter.drawLine(QPointF(*p0), QPointF(*c1))
                    painter.drawLine(QPointF(*c1), QPointF(*c2))
                    painter.drawLine(QPointF(*c2), QPointF(*p3))

                for p in (p0, c1, c2, p3):
                    key = (round(p[0], 6), round(p[1], 6))
                    if key in seen:
                        continue
                    seen.add(key)
                    helper_points.append(p)

            if self.show_bspline_helpers:
                painter.setPen(QPen(helper_color, 1))
                painter.setBrush(QBrush(helper_color))
                for hx, hy in helper_points:
                    painter.drawEllipse(QPointF(hx, hy), 2.0, 2.0)
