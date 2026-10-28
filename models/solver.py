from __future__ import annotations

import math
from collections import deque

from models.point import Point
from models.polygon import Polygon
from models.constraints import (
    ConstraintStore,
    LengthConstraint,
    ParallelConstraint,
    edge_length,
    same_edge,
)
from models.continuity import (
    enforce_all_continuities,
    enforce_after_move,
    sync_bezier_handles_from_snap,
    continuity_satisfied,
    vertex_has_curve_neighbor,
    recompute_all_arcs,
    bezier_for_control,
    adjacent_edges,
)
from models.edges import ArcEdge, BezierEdge, StraightEdge


EPS = 1e-3
SETTLE_ITERS = 120
SETTLE_ITERS_INTERACTIVE = 32
PROPAGATE_ITERS = 16
PROPAGATE_ITERS_INTERACTIVE = 6


def _all_points(polygons: list[Polygon]):
    seen: set[int] = set()
    for poly in polygons:
        for p in poly.points:
            if id(p) not in seen:
                seen.add(id(p))
                yield p
        for edge in poly.edges:
            for p in edge.control_points():
                if id(p) not in seen:
                    seen.add(id(p))
                    yield p


def _snapshot(polygons: list[Polygon]) -> dict[int, tuple[float, float]]:
    return {id(p): (p.x, p.y) for p in _all_points(polygons)}


def _invalidate_arcs(polygons: list[Polygon]) -> None:
    """Po restore współrzędnych stary _geom łuku nie przechodzi przez końce."""
    for poly in polygons:
        for e in poly.edges:
            if isinstance(e, ArcEdge):
                e._geom = None


def _recompute_arcs(polygons: list[Polygon]) -> None:
    for poly in polygons:
        recompute_all_arcs(poly.edges)


def _restore(polygons: list[Polygon], snap: dict[int, tuple[float, float]]) -> None:
    for p in _all_points(polygons):
        xy = snap.get(id(p))
        if xy is not None:
            p.x, p.y = xy
    _invalidate_arcs(polygons)


def snapshot_positions(polygons: list[Polygon]) -> dict[int, tuple[float, float]]:
    return _snapshot(polygons)


def restore_positions(polygons: list[Polygon], snap: dict[int, tuple[float, float]]) -> None:
    _restore(polygons, snap)
    _recompute_arcs(polygons)


def _place_at_length(anchor: Point, moving: Point, length: float) -> None:
    dx, dy = moving.x - anchor.x, moving.y - anchor.y
    dist = math.hypot(dx, dy)
    if dist < 1e-9:
        moving.move_to(anchor.x + length, anchor.y)
        return
    s = length / dist
    moving.move_to(anchor.x + dx * s, anchor.y + dy * s)


def _scale_edge_from_mid(c: LengthConstraint) -> None:
    mx, my = (c.p1.x + c.p2.x) / 2, (c.p1.y + c.p2.y) / 2
    dx, dy = c.p2.x - c.p1.x, c.p2.y - c.p1.y
    dist = math.hypot(dx, dy)
    if dist < 1e-9:
        c.p1.move_to(mx - c.length / 2, my)
        c.p2.move_to(mx + c.length / 2, my)
        return
    ux, uy = dx / dist, dy / dist
    half = c.length / 2
    c.p1.move_to(mx - ux * half, my - uy * half)
    c.p2.move_to(mx + ux * half, my + uy * half)


def _unit_dir(p1: Point, p2: Point) -> tuple[float, float] | None:
    dx, dy = p2.x - p1.x, p2.y - p1.y
    length = math.hypot(dx, dy)
    if length < 1e-9:
        return None
    return dx / length, dy / length


def _target_length(store: ConstraintStore, p1: Point, p2: Point) -> float:
    for lc in store.all_lengths():
        if lc.involves_edge(p1, p2):
            return lc.length
    return edge_length(p1, p2)


def _align_edge(
    p1: Point,
    p2: Point,
    ux: float,
    uy: float,
    length: float,
    pinned: set[int],
) -> None:
    """Ustawia krawędź w kierunku (ux,uy) z daną długością, nie ruszając pinów jeśli się da."""
    cur = _unit_dir(p1, p2)
    if cur is not None and cur[0] * ux + cur[1] * uy < 0:
        ux, uy = -ux, -uy

    a_pin = id(p1) in pinned
    b_pin = id(p2) in pinned
    if a_pin and b_pin:
        return
    if a_pin:
        p2.move_to(p1.x + ux * length, p1.y + uy * length)
        return
    if b_pin:
        p1.move_to(p2.x - ux * length, p2.y - uy * length)
        return

    mx, my = (p1.x + p2.x) / 2, (p1.y + p2.y) / 2
    half = length / 2
    p1.move_to(mx - ux * half, my - uy * half)
    p2.move_to(mx + ux * half, my + uy * half)


def _edge_move_score(p1: Point, p2: Point, pinned: set[int], dist: dict[int, int]) -> int:
    if id(p1) in pinned and id(p2) in pinned:
        return -1
    return dist.get(id(p1), 0) + dist.get(id(p2), 0)


def _edge_pin_count(p1: Point, p2: Point, pinned: set[int]) -> int:
    return (1 if id(p1) in pinned else 0) + (1 if id(p2) in pinned else 0)


def _edge_key(p1: Point, p2: Point) -> frozenset[int]:
    return frozenset({id(p1), id(p2)})


def _authority_edges_for_cp(
    polygons: list[Polygon],
    prefer_adjust: Point | None,
) -> set[frozenset[int]]:
    """
    Przy przeciąganiu CP: odcinek przyległy do końców związanego z tym CP
    ma autorytet kierunku. ∥ dogrywa partnera, zamiast cofać tę krawędź.
    """
    auth: set[frozenset[int]] = set()
    if prefer_adjust is None or not prefer_adjust.is_control:
        return auth
    for poly in polygons:
        owner = bezier_for_control(poly.edges, prefer_adjust)
        if owner is None:
            continue
        # c1 ↔ p1, c2 ↔ p2 — tylko lokalny koniec, nie oba naraz (∥ góra∥dół)
        if prefer_adjust is owner.c1:
            ends = (owner.p1,)
        elif prefer_adjust is owner.c2:
            ends = (owner.p2,)
        else:
            ends = (owner.p1, owner.p2)
        for v in ends:
            incoming, outgoing = adjacent_edges(poly.edges, v)
            for e in (incoming, outgoing):
                if e is None or e is owner:
                    continue
                if isinstance(e, StraightEdge):
                    auth.add(_edge_key(e.p1, e.p2))
    return auth


def _fix_parallel(
    pc: ParallelConstraint,
    store: ConstraintStore,
    pinned: set[int],
    dist: dict[int, int],
    authority: set[frozenset[int]] | None = None,
) -> None:
    sa = _edge_move_score(pc.a1, pc.a2, pinned, dist)
    sb = _edge_move_score(pc.b1, pc.b2, pinned, dist)
    if sa < 0 and sb < 0:
        return

    authority = authority or set()
    ka = _edge_key(pc.a1, pc.a2)
    kb = _edge_key(pc.b1, pc.b2)
    a_auth = ka in authority
    b_auth = kb in authority

    # 1) krawędź z autorytetem ciągłości (np. po ruchu CP) = referencja
    if a_auth and not b_auth and sb >= 0:
        ref1, ref2, m1, m2 = pc.a1, pc.a2, pc.b1, pc.b2
    elif b_auth and not a_auth and sa >= 0:
        ref1, ref2, m1, m2 = pc.b1, pc.b2, pc.a1, pc.a2
    else:
        # 2) więcej pinów = odniesienie; 3) inaczej wyższy dist = ruchoma
        pa = _edge_pin_count(pc.a1, pc.a2, pinned)
        pb = _edge_pin_count(pc.b1, pc.b2, pinned)
        if pa > pb and sb >= 0:
            ref1, ref2, m1, m2 = pc.a1, pc.a2, pc.b1, pc.b2
        elif pb > pa and sa >= 0:
            ref1, ref2, m1, m2 = pc.b1, pc.b2, pc.a1, pc.a2
        elif sa >= sb:
            ref1, ref2, m1, m2 = pc.b1, pc.b2, pc.a1, pc.a2
        else:
            ref1, ref2, m1, m2 = pc.a1, pc.a2, pc.b1, pc.b2

    direction = _unit_dir(ref1, ref2)
    if direction is None:
        return
    ux, uy = direction
    length = _target_length(store, m1, m2)
    _align_edge(m1, m2, ux, uy, length, pinned)


def _build_adj(store: ConstraintStore, polygons: list[Polygon] | None = None) -> dict[int, list[Point]]:
    adj: dict[int, list[Point]] = {}

    def link(p: Point, q: Point) -> None:
        adj.setdefault(id(p), []).append(q)
        adj.setdefault(id(q), []).append(p)

    for c in store.all_lengths():
        link(c.p1, c.p2)
    for c in store.all_parallels():
        pts = [c.a1, c.a2, c.b1, c.b2]
        for i in range(len(pts)):
            for j in range(i + 1, len(pts)):
                link(pts[i], pts[j])

    if polygons is not None:
        for poly in polygons:
            for edge in poly.edges:
                link(edge.p1, edge.p2)
                if isinstance(edge, BezierEdge):
                    link(edge.p1, edge.c1)
                    link(edge.p2, edge.c2)
                    link(edge.c1, edge.c2)
    return adj


def _graph_distance(
    seeds: list[Point] | Point,
    store: ConstraintStore,
    polygons: list[Polygon] | None = None,
) -> dict[int, int]:
    if isinstance(seeds, Point):
        seeds = [seeds]
    adj = _build_adj(store, polygons)
    dist: dict[int, int] = {}
    queue: deque[Point] = deque()
    for s in seeds:
        dist[id(s)] = 0
        queue.append(s)
    while queue:
        p = queue.popleft()
        for n in adj.get(id(p), []):
            nd = dist[id(p)] + 1
            prev = dist.get(id(n))
            if prev is None or nd < prev:
                dist[id(n)] = nd
                queue.append(n)
    return dist


def _fix_length_minimal(c: LengthConstraint, pinned: set[int], dist: dict[int, int]) -> None:
    a_pin = id(c.p1) in pinned
    b_pin = id(c.p2) in pinned
    if a_pin and b_pin:
        return
    if a_pin:
        _place_at_length(c.p1, c.p2, c.length)
        return
    if b_pin:
        _place_at_length(c.p2, c.p1, c.length)
        return

    d1 = dist.get(id(c.p1), 10**9)
    d2 = dist.get(id(c.p2), 10**9)
    if d1 >= d2:
        _place_at_length(c.p2, c.p1, c.length)
    else:
        _place_at_length(c.p1, c.p2, c.length)


class ConstraintSolver:
    def __init__(self, store: ConstraintStore):
        self.store = store

    def all_satisfied(self) -> bool:
        return all(c.is_satisfied(EPS) for c in self.store.items)

    def scene_ok(self, polygons: list[Polygon]) -> bool:
        for poly in polygons:
            recompute_all_arcs(poly.edges)
        # continuity_satisfied też woła recompute — pomijamy powtórkę
        return self.all_satisfied() and all(
            continuity_satisfied(poly.edges, recompute_arcs=False)
            for poly in polygons
        )

    def _component_satisfied(self, fixed: set[int]) -> bool:
        for c in self.store.all_lengths():
            if id(c.p1) in fixed or id(c.p2) in fixed:
                if not c.is_satisfied(EPS):
                    return False
        for c in self.store.all_parallels():
            if any(id(p) in fixed for p in (c.a1, c.a2, c.b1, c.b2)):
                if not c.is_satisfied(EPS):
                    return False
        return True

    def _propagate_from_fixed(self, seeds: set[Point]) -> bool:
        fixed: set[int] = {id(p) for p in seeds}
        lengths = self.store.all_lengths()

        progress = True
        while progress:
            progress = False
            for c in lengths:
                a_fixed = id(c.p1) in fixed
                b_fixed = id(c.p2) in fixed

                if a_fixed and not b_fixed:
                    _place_at_length(c.p1, c.p2, c.length)
                    fixed.add(id(c.p2))
                    progress = True
                elif b_fixed and not a_fixed:
                    _place_at_length(c.p2, c.p1, c.length)
                    fixed.add(id(c.p1))
                    progress = True
                elif a_fixed and b_fixed:
                    if not c.is_satisfied(EPS):
                        return False

        return self._component_satisfied(fixed)

    def settle_all(
        self,
        priority_length: LengthConstraint | None = None,
        priority_parallel: ParallelConstraint | None = None,
        pinned: set[int] | None = None,
        dist: dict[int, int] | None = None,
        only_ids: set[int] | None = None,
        max_iters: int | None = None,
        authority: set[frozenset[int]] | None = None,
    ) -> bool:
        pinned = pinned or set()
        dist = dist or {}
        authority = authority or set()
        lengths = self.store.all_lengths()
        parallels = self.store.all_parallels()
        limit = SETTLE_ITERS if max_iters is None else max_iters

        if only_ids is not None:
            lengths = [c for c in lengths if id(c.p1) in only_ids or id(c.p2) in only_ids]
            parallels = [
                c for c in parallels
                if any(id(p) in only_ids for p in (c.a1, c.a2, c.b1, c.b2))
            ]

        if not lengths and not parallels:
            return True

        for _ in range(limit):
            if priority_parallel is not None and not priority_parallel.is_satisfied(EPS):
                _fix_parallel(priority_parallel, self.store, pinned, dist, authority)

            for pc in parallels:
                if not pc.is_satisfied(EPS):
                    _fix_parallel(pc, self.store, pinned, dist, authority)

            if priority_length is not None and not priority_length.is_satisfied(EPS):
                if pinned:
                    _fix_length_minimal(priority_length, pinned, dist)
                else:
                    _scale_edge_from_mid(priority_length)

            max_err = 0.0
            for c in lengths:
                err = abs(c.current_length() - c.length)
                max_err = max(max_err, err)
                if err > EPS:
                    if pinned:
                        _fix_length_minimal(c, pinned, dist)
                    else:
                        _scale_edge_from_mid(c)

            for pc in parallels:
                if not pc.is_satisfied(EPS):
                    max_err = max(max_err, 1.0)

            if max_err <= EPS and all(pc.is_satisfied(EPS) for pc in parallels):
                return True

        return (
            all(c.is_satisfied(EPS) for c in lengths)
            and all(pc.is_satisfied(EPS) for pc in parallels)
        )

    def settle_lengths(self, priority: LengthConstraint | None = None) -> bool:
        return self.settle_all(priority_length=priority)

    def settle_with_pinned(self, pinned_point: Point, polygons: list[Polygon] | None = None) -> bool:
        dist = _graph_distance(pinned_point, self.store, polygons)
        only = set(dist.keys())
        if not only:
            only = {id(pinned_point)}
        return self.settle_all(pinned={id(pinned_point)}, dist=dist, only_ids=only)

    def propagate_repair(
        self,
        polygons: list[Polygon],
        *,
        pinned: set[int] | None = None,
        seeds: list[Point] | None = None,
        prefer_adjust: Point | None = None,
        interactive: bool = False,
    ) -> bool:
        """
        Projekcja: ciągłości ↔ długości/∥.
        interactive=True — krótka pętla pod przeciąganie myszą (płynność);
        pełna naprawa przy interactive=False (menu / mouse-up).
        """
        pinned = set(pinned or set())
        seed_pts = list(seeds or [])
        if not seed_pts:
            by_id = {id(p): p for p in _all_points(polygons)}
            seed_pts = [by_id[i] for i in pinned if i in by_id]
        dist = _graph_distance(seed_pts, self.store, polygons) if seed_pts else {}

        outer = PROPAGATE_ITERS_INTERACTIVE if interactive else PROPAGATE_ITERS
        settle_cap = SETTLE_ITERS_INTERACTIVE if interactive else SETTLE_ITERS
        # przy CP: odcinki przyległe mają autorytet kierunku (∥ idzie za ciągłością)
        authority = _authority_edges_for_cp(polygons, prefer_adjust)

        dirty: deque[Point] = deque(seed_pts)
        in_q = {id(p) for p in seed_pts}
        lengths = self.store.all_lengths()
        parallels = self.store.all_parallels()
        has_constraints = bool(lengths or parallels)

        def enqueue(p: Point) -> None:
            if id(p) in pinned:
                return
            if id(p) not in in_q:
                dirty.append(p)
                in_q.add(id(p))

        def enqueue_moved(before: dict[int, tuple[float, float]]) -> None:
            for p in _all_points(polygons):
                xy = before.get(id(p))
                if xy is None:
                    continue
                if abs(p.x - xy[0]) > 1e-9 or abs(p.y - xy[1]) > 1e-9:
                    enqueue(p)

        def apply_continuities(*, handles_only: bool = False) -> None:
            frozen: set[int] = set()
            if handles_only:
                for poly in polygons:
                    for p in poly.points:
                        frozen.add(id(p))
            for poly in polygons:
                if prefer_adjust is not None and (
                    any(p is prefer_adjust for p in poly.points)
                    or any(
                        prefer_adjust is cp
                        for e in poly.edges
                        for cp in e.control_points()
                    )
                ):
                    enforce_after_move(
                        poly.edges,
                        prefer_adjust,
                        pinned=pinned,
                        frozen_verts=frozen,
                        dist=dist,
                    )
                else:
                    enforce_all_continuities(
                        poly.edges, pinned=pinned, frozen_verts=frozen, dist=dist
                    )

        def drain_dirty() -> None:
            while dirty:
                p = dirty.popleft()
                in_q.discard(id(p))
                before = _snapshot(polygons)

                for lc in lengths:
                    if not lc.involves_point(p) or lc.is_satisfied(EPS):
                        continue
                    _fix_length_minimal(lc, pinned, dist)

                for pc in parallels:
                    if not pc.involves_point(p) or pc.is_satisfied(EPS):
                        continue
                    _fix_parallel(pc, self.store, pinned, dist, authority)

                enqueue_moved(before)

        if not has_constraints:
            apply_continuities()
            apply_continuities(handles_only=True)
            return self.scene_ok(polygons)

        for _ in range(outer):
            if self.scene_ok(polygons):
                return True

            # 1) ciągłość ustawia kierunek przyległych odcinków (autorytet)
            before = _snapshot(polygons)
            apply_continuities()
            enqueue_moved(before)

            # 2) ∥ / długości — partnerzy podążają za autorytetem, nie cofają go
            drain_dirty()
            before = _snapshot(polygons)
            self.settle_all(
                pinned=pinned, dist=dist, max_iters=settle_cap, authority=authority
            )
            for poly in polygons:
                sync_bezier_handles_from_snap(poly.edges, before, pinned=pinned)

            # 3) tylko uchwyty — wierzchołki (i kierunki odcinków) zostają
            apply_continuities(handles_only=True)

            if self.scene_ok(polygons):
                return True

            for poly in polygons:
                if not continuity_satisfied(poly.edges, recompute_arcs=False):
                    for v in poly.points:
                        if vertex_has_curve_neighbor(poly.edges, v):
                            enqueue(v)
            for c in self.store.items:
                if c.is_satisfied(EPS):
                    continue
                if isinstance(c, LengthConstraint):
                    enqueue(c.p1)
                    enqueue(c.p2)
                elif isinstance(c, ParallelConstraint):
                    for q in (c.a1, c.a2, c.b1, c.b2):
                        enqueue(q)

        return self.scene_ok(polygons)

    def try_add_length(self, p1: Point, p2: Point, length: float, polygons: list[Polygon]) -> bool:
        snap = _snapshot(polygons)
        constraint = LengthConstraint(p1, p2, length)
        self.store.add(constraint)

        inits = [
            lambda: _scale_edge_from_mid(constraint),
            lambda: _place_at_length(p1, p2, length),
            lambda: _place_at_length(p2, p1, length),
        ]

        for init in inits:
            _restore(polygons, snap)
            init()
            if self.settle_all(priority_length=constraint):
                if self.propagate_repair(polygons):
                    return True

        self.store.remove(constraint)
        _restore(polygons, snap)
        return False

    def try_add_parallel(
        self,
        a1: Point,
        a2: Point,
        b1: Point,
        b2: Point,
        polygons: list[Polygon],
    ) -> bool:
        if same_edge(a1, a2, b1, b2):
            return False

        snap = _snapshot(polygons)
        constraint = ParallelConstraint(a1, a2, b1, b2, self.store.next_parallel_color())
        before = len(self.store.items)
        self.store.add(constraint)
        if len(self.store.items) == before:
            return True

        def align_b_to_a() -> None:
            d = _unit_dir(a1, a2)
            if d is None:
                return
            _align_edge(b1, b2, d[0], d[1], _target_length(self.store, b1, b2), set())

        def align_a_to_b() -> None:
            d = _unit_dir(b1, b2)
            if d is None:
                return
            _align_edge(a1, a2, d[0], d[1], _target_length(self.store, a1, a2), set())

        for init in (align_b_to_a, align_a_to_b):
            _restore(polygons, snap)
            init()
            if self.settle_all(priority_parallel=constraint):
                if self.propagate_repair(polygons):
                    return True

        self.store.remove(constraint)
        _restore(polygons, snap)
        return False

    def move_point_or_translate(
        self,
        point: Point,
        tx: float,
        ty: float,
        polygons: list[Polygon],
        drag_snap: dict[int, tuple[float, float]],
        origin: tuple[float, float],
        *,
        interactive: bool = False,
    ) -> bool:
        """
        Ustaw point pod (tx,ty) bez łamania ograniczeń/ciągłości.
        Translacja własnego wielokąta tylko gdy lokalna naprawa jest niemożliwa.
        Zwraca True gdy scena jest spójna po operacji.
        """
        _restore(polygons, drag_snap)
        dx = tx - origin[0]
        dy = ty - origin[1]

        if abs(dx) < 1e-12 and abs(dy) < 1e-12:
            return self.scene_ok(polygons)

        _restore(polygons, drag_snap)
        point.move_to(tx, ty)
        self.propagate_repair(
            polygons,
            pinned={id(point)},
            seeds=[point],
            prefer_adjust=point,
            interactive=interactive,
        )
        point.move_to(tx, ty)
        if self.scene_ok(polygons):
            return True

        # krótka ścieżka mogła nie dojść — pełna naprawa zanim uznamy „nie da się”
        if interactive:
            _restore(polygons, drag_snap)
            point.move_to(tx, ty)
            self.propagate_repair(
                polygons,
                pinned={id(point)},
                seeds=[point],
                prefer_adjust=point,
                interactive=False,
            )
            point.move_to(tx, ty)
            if self.scene_ok(polygons):
                return True

        # ostateczność: sztywna translacja własnego poly (kierunki ⇒ ∥ OK)
        _restore(polygons, drag_snap)
        moved: set[int] = set()
        for poly in polygons:
            if not any(p is point for p in poly.points):
                continue
            for p in poly.points:
                if id(p) in moved:
                    continue
                moved.add(id(p))
                ox, oy = drag_snap[id(p)]
                p.move_to(ox + dx, oy + dy)
            for edge in poly.edges:
                for p in edge.control_points():
                    if id(p) in moved:
                        continue
                    moved.add(id(p))
                    ox, oy = drag_snap[id(p)]
                    p.move_to(ox + dx, oy + dy)
        point.move_to(tx, ty)
        _recompute_arcs(polygons)
        return self.scene_ok(polygons)
