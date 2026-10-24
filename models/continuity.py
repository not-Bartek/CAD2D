from __future__ import annotations

from core.enums import Continuity
from core.bezier_math import normalize, vec_len
from models.point import Point
from models.edges import Edge, StraightEdge, BezierEdge, ArcEdge


def _incoming_tangent(edge: Edge, vertex: Point) -> tuple[float, float] | None:
    if isinstance(edge, BezierEdge):
        if edge.p2 is vertex:
            return (3 * (vertex.x - edge.c2.x), 3 * (vertex.y - edge.c2.y))
        if edge.p1 is vertex:
            return (3 * (edge.c1.x - vertex.x), 3 * (edge.c1.y - vertex.y))
    if isinstance(edge, ArcEdge):
        t = edge.unit_tangent_at(vertex)
        if t is None:
            return None
        # w p2 styczna unit_tangent jest w kierunku podróży (= wychodząca z łuku w p2);
        # jako incoming tin = ta sama (kierunek ścieżki)
        return t
    other = edge.p1 if edge.p2 is vertex else edge.p2
    return (vertex.x - other.x, vertex.y - other.y)


def _outgoing_tangent(edge: Edge, vertex: Point) -> tuple[float, float] | None:
    if isinstance(edge, BezierEdge):
        if edge.p1 is vertex:
            return (3 * (edge.c1.x - vertex.x), 3 * (edge.c1.y - vertex.y))
        if edge.p2 is vertex:
            return (3 * (vertex.x - edge.c2.x), 3 * (vertex.y - edge.c2.y))
    if isinstance(edge, ArcEdge):
        return edge.unit_tangent_at(vertex)
    other = edge.p2 if edge.p1 is vertex else edge.p1
    return (other.x - vertex.x, other.y - vertex.y)


def _set_incoming_bezier_handle(
    edge: BezierEdge,
    vertex: Point,
    tx: float,
    ty: float,
    pinned: set[int],
) -> bool:
    if edge.p2 is vertex:
        if id(edge.c2) in pinned:
            return False
        edge.c2.move_to(vertex.x - tx / 3, vertex.y - ty / 3)
        return True
    if edge.p1 is vertex:
        if id(edge.c1) in pinned:
            return False
        edge.c1.move_to(vertex.x + tx / 3, vertex.y + ty / 3)
        return True
    return False


def _set_outgoing_bezier_handle(
    edge: BezierEdge,
    vertex: Point,
    tx: float,
    ty: float,
    pinned: set[int],
) -> bool:
    if edge.p1 is vertex:
        if id(edge.c1) in pinned:
            return False
        edge.c1.move_to(vertex.x + tx / 3, vertex.y + ty / 3)
        return True
    if edge.p2 is vertex:
        if id(edge.c2) in pinned:
            return False
        edge.c2.move_to(vertex.x - tx / 3, vertex.y - ty / 3)
        return True
    return False


def _far_vertex(edge: Edge, vertex: Point) -> Point:
    return edge.p1 if edge.p2 is vertex else edge.p2


def _place_far_for_g1(vertex: Point, far: Point, desired_unit: tuple[float, float], pinned: set[int], frozen: set[int]) -> bool:
    if id(far) in pinned or id(far) in frozen:
        return False
    length = vec_len(vertex.x - far.x, vertex.y - far.y)
    if length < 1e-9:
        length = 1.0
    far.move_to(vertex.x - desired_unit[0] * length, vertex.y - desired_unit[1] * length)
    return True


def _place_far_for_g1_out(vertex: Point, far: Point, desired_unit: tuple[float, float], pinned: set[int], frozen: set[int]) -> bool:
    if id(far) in pinned or id(far) in frozen:
        return False
    length = vec_len(far.x - vertex.x, far.y - vertex.y)
    if length < 1e-9:
        length = 1.0
    far.move_to(vertex.x + desired_unit[0] * length, vertex.y + desired_unit[1] * length)
    return True


def _place_far_for_c1_in(vertex: Point, far: Point, tin_match: tuple[float, float], pinned: set[int], frozen: set[int]) -> bool:
    if id(far) in pinned or id(far) in frozen:
        return False
    far.move_to(vertex.x - tin_match[0], vertex.y - tin_match[1])
    return True


def _place_far_for_c1_out(vertex: Point, far: Point, tout_match: tuple[float, float], pinned: set[int], frozen: set[int]) -> bool:
    if id(far) in pinned or id(far) in frozen:
        return False
    far.move_to(vertex.x + tout_match[0], vertex.y + tout_match[1])
    return True


def adjacent_edges(edges: list[Edge], vertex: Point) -> tuple[Edge | None, Edge | None]:
    incoming = None
    outgoing = None
    for e in edges:
        if e.p2 is vertex:
            incoming = e
        if e.p1 is vertex:
            outgoing = e
    return incoming, outgoing


def vertex_has_bezier_neighbor(edges: list[Edge], vertex: Point) -> bool:
    incoming, outgoing = adjacent_edges(edges, vertex)
    return isinstance(incoming, BezierEdge) or isinstance(outgoing, BezierEdge)


def vertex_has_arc_neighbor(edges: list[Edge], vertex: Point) -> bool:
    incoming, outgoing = adjacent_edges(edges, vertex)
    return isinstance(incoming, ArcEdge) or isinstance(outgoing, ArcEdge)


def vertex_has_curve_neighbor(edges: list[Edge], vertex: Point) -> bool:
    return vertex_has_bezier_neighbor(edges, vertex) or vertex_has_arc_neighbor(edges, vertex)


def bezier_for_control(edges: list[Edge], cp: Point) -> BezierEdge | None:
    for e in edges:
        if isinstance(e, BezierEdge) and (cp is e.c1 or cp is e.c2):
            return e
    return None


def _neighbor_tangent_for_arc_g1(
    edges: list[Edge], arc: ArcEdge, g1: Point
) -> tuple[float, float] | None:
    """Styczna z sąsiedniej (nie-łukowej / już policzonej) krawędzi w końcu G1."""
    incoming, outgoing = adjacent_edges(edges, g1)
    if arc is outgoing and incoming is not None and incoming is not arc:
        if isinstance(incoming, ArcEdge):
            t = incoming.unit_tangent_at(g1)
        else:
            t = _incoming_tangent(incoming, g1)
        if t is None:
            return None
        return normalize(t[0], t[1])
    if arc is incoming and outgoing is not None and outgoing is not arc:
        if isinstance(outgoing, ArcEdge):
            t = outgoing.unit_tangent_at(g1)
        else:
            t = _outgoing_tangent(outgoing, g1)
        if t is None:
            return None
        return normalize(t[0], t[1])
    return None


def recompute_all_arcs(edges: list[Edge]) -> None:
    """Przelicza geometrię łuków (G0→półokrąg, G1→styczna sąsiada)."""
    for e in edges:
        if isinstance(e, ArcEdge):
            e.ensure_single_g1()
            if e.g1_endpoint() is None:
                e.recompute(None)
    for e in edges:
        if not isinstance(e, ArcEdge):
            continue
        g1 = e.g1_endpoint()
        if g1 is None:
            continue
        e.recompute(_neighbor_tangent_for_arc_g1(edges, e, g1))


def incident_arcs(edges: list[Edge], vertex: Point) -> list[ArcEdge]:
    """Wszystkie łuki incydentne do wierzchołka."""
    result: list[ArcEdge] = []
    for e in edges:
        if isinstance(e, ArcEdge) and e.has_point(vertex):
            result.append(e)
    return result


def arc_g1_conflicts(edges: list[Edge], vertex: Point) -> list[Point]:
    """
    Drugie końce łuków incydentnych do vertex, które mają już G1.
    (Na łuku może być tylko jeden koniec z G1.)
    """
    seen: set[int] = set()
    conflicts: list[Point] = []
    for e in incident_arcs(edges, vertex):
        other = e.p2 if e.p1 is vertex else e.p1
        if other.continuity == Continuity.G1 and id(other) not in seen:
            seen.add(id(other))
            conflicts.append(other)
    return conflicts


def clear_other_arc_g1(edges: list[Edge], vertex: Point) -> list[Point]:
    """
    Po ustawieniu G1 na wierzchołku — drugie końce wszystkich incydentnych
    łuków tracą G1 (G1 na vertex obowiązuje dla każdego łuku incydentnego).
    Zwraca listę wierzchołków, którym zdjęto G1.
    """
    cleared: list[Point] = []
    for other in arc_g1_conflicts(edges, vertex):
        other.continuity = Continuity.G0
        other.continuity_explicit = True
        cleared.append(other)
    return cleared


def enforce_continuity_at(
    edges: list[Edge],
    vertex: Point,
    *,
    prefer_adjust: Point | None = None,
    pinned: set[int] | None = None,
    frozen_verts: set[int] | None = None,
    dist: dict[int, int] | None = None,
) -> None:
    """
    Egzekwuje ciągłość. Preferuje uchwyty Béziera; łuki dogrywane przez recompute.
    """
    if vertex.is_control:
        return
    if not vertex_has_curve_neighbor(edges, vertex):
        return

    cont = vertex.continuity
    if cont == Continuity.G0:
        recompute_all_arcs(edges)
        return

    # C1 nie dotyczy łuków — traktuj jak G1 przy sąsiedztwie łuku
    if cont == Continuity.C1 and vertex_has_arc_neighbor(edges, vertex):
        cont = Continuity.G1

    pinned = pinned or set()
    frozen_verts = frozen_verts or set()
    dist = dist or {}

    recompute_all_arcs(edges)

    incoming, outgoing = adjacent_edges(edges, vertex)
    if incoming is None or outgoing is None:
        return

    in_arc = isinstance(incoming, ArcEdge)
    out_arc = isinstance(outgoing, ArcEdge)
    in_bezier = isinstance(incoming, BezierEdge)
    out_bezier = isinstance(outgoing, BezierEdge)

    # Łuk z G1 na tym wierzchołku: geometria ze stycznej drugiej strony — OK po recompute.
    # Dogrywamy stronę nie-łukową / Béziera gdy łuk jest „pasywny” albo G0 na tym końcu.
    tin = _incoming_tangent(incoming, vertex)
    tout = _outgoing_tangent(outgoing, vertex)
    if tin is None or tout is None:
        return

    prefer_out = True
    if prefer_adjust is not None:
        if out_bezier and (prefer_adjust is outgoing.c1 or prefer_adjust is outgoing.c2):
            prefer_out = False
        elif in_bezier and (prefer_adjust is incoming.c1 or prefer_adjust is incoming.c2):
            prefer_out = True
    elif out_arc and not in_arc:
        # łuk wychodzący — trzymaj łuk (recompute), rusz stronę wchodzącą tylko gdy trzeba
        prefer_out = False
    elif in_arc and not out_arc:
        prefer_out = True
    elif in_bezier and not out_bezier:
        prefer_out = False
    elif out_bezier and not in_bezier:
        prefer_out = True
    elif not in_bezier and not out_bezier and not in_arc and not out_arc:
        far_in = _far_vertex(incoming, vertex)
        far_out = _far_vertex(outgoing, vertex)
        prefer_out = dist.get(id(far_out), 0) >= dist.get(id(far_in), 0)

    def fix_out_to_match_in() -> bool:
        if out_arc:
            # łuk dogrywany przez recompute ze stycznej incoming
            recompute_all_arcs(edges)
            return True
        if cont == Continuity.C1:
            if out_bezier:
                return _set_outgoing_bezier_handle(outgoing, vertex, tin[0], tin[1], pinned)
            far = _far_vertex(outgoing, vertex)
            return _place_far_for_c1_out(vertex, far, tin, pinned, frozen_verts)
        nin = normalize(tin[0], tin[1])
        if nin is None:
            return False
        if out_bezier:
            length = vec_len(tout[0], tout[1])
            return _set_outgoing_bezier_handle(
                outgoing, vertex, nin[0] * length, nin[1] * length, pinned
            )
        far = _far_vertex(outgoing, vertex)
        return _place_far_for_g1_out(vertex, far, nin, pinned, frozen_verts)

    def fix_in_to_match_out() -> bool:
        if in_arc:
            recompute_all_arcs(edges)
            return True
        if cont == Continuity.C1:
            if in_bezier:
                return _set_incoming_bezier_handle(incoming, vertex, tout[0], tout[1], pinned)
            far = _far_vertex(incoming, vertex)
            return _place_far_for_c1_in(vertex, far, tout, pinned, frozen_verts)
        nout = normalize(tout[0], tout[1])
        if nout is None:
            return False
        if in_bezier:
            length = vec_len(tin[0], tin[1])
            return _set_incoming_bezier_handle(
                incoming, vertex, nout[0] * length, nout[1] * length, pinned
            )
        far = _far_vertex(incoming, vertex)
        return _place_far_for_g1(vertex, far, nout, pinned, frozen_verts)

    if prefer_out:
        if not fix_out_to_match_in():
            fix_in_to_match_out()
    else:
        if not fix_in_to_match_out():
            fix_out_to_match_in()

    recompute_all_arcs(edges)


def enforce_all_continuities(
    edges: list[Edge],
    pinned: set[int] | None = None,
    frozen_verts: set[int] | None = None,
    dist: dict[int, int] | None = None,
) -> None:
    recompute_all_arcs(edges)
    seen: set[int] = set()
    for e in edges:
        for v in (e.p1, e.p2):
            if id(v) in seen or v.is_control:
                continue
            seen.add(id(v))
            enforce_continuity_at(
                edges, v, pinned=pinned, frozen_verts=frozen_verts, dist=dist
            )
    recompute_all_arcs(edges)


def enforce_after_move(
    edges: list[Edge],
    moved: Point,
    *,
    pinned: set[int] | None = None,
    frozen_verts: set[int] | None = None,
    dist: dict[int, int] | None = None,
) -> None:
    pinned = set(pinned or set())
    frozen_verts = set(frozen_verts or set())

    if moved.is_control:
        pinned.add(id(moved))
        owner = bezier_for_control(edges, moved)
        if owner is not None:
            enforce_continuity_at(
                edges, owner.p1, prefer_adjust=moved, pinned=pinned,
                frozen_verts=frozen_verts, dist=dist,
            )
            enforce_continuity_at(
                edges, owner.p2, prefer_adjust=moved, pinned=pinned,
                frozen_verts=frozen_verts, dist=dist,
            )
            enforce_all_continuities(
                edges, pinned=pinned, frozen_verts=frozen_verts, dist=dist
            )
        return

    enforce_continuity_at(
        edges, moved, pinned=pinned, frozen_verts=frozen_verts, dist=dist
    )
    incoming, outgoing = adjacent_edges(edges, moved)
    for e in (incoming, outgoing):
        if isinstance(e, (BezierEdge, ArcEdge)):
            other = e.p2 if e.p1 is moved else e.p1
            enforce_continuity_at(
                edges, other, pinned=pinned, frozen_verts=frozen_verts, dist=dist
            )
    enforce_all_continuities(
        edges, pinned=pinned, frozen_verts=frozen_verts, dist=dist
    )


def sync_bezier_handles_from_snap(
    edges: list[Edge],
    snap: dict[int, tuple[float, float]],
    pinned: set[int] | None = None,
) -> None:
    pinned = pinned or set()
    for e in edges:
        if not isinstance(e, BezierEdge):
            continue
        if id(e.p1) in snap and id(e.c1) in snap and id(e.c1) not in pinned:
            dx = e.p1.x - snap[id(e.p1)][0]
            dy = e.p1.y - snap[id(e.p1)][1]
            e.c1.move_to(snap[id(e.c1)][0] + dx, snap[id(e.c1)][1] + dy)
        if id(e.p2) in snap and id(e.c2) in snap and id(e.c2) not in pinned:
            dx = e.p2.x - snap[id(e.p2)][0]
            dy = e.p2.y - snap[id(e.p2)][1]
            e.c2.move_to(snap[id(e.c2)][0] + dx, snap[id(e.c2)][1] + dy)
    recompute_all_arcs(edges)


def continuity_satisfied(edges: list[Edge], eps: float = 1e-3) -> bool:
    recompute_all_arcs(edges)
    for e in edges:
        if isinstance(e, ArcEdge):
            if (
                e.p1.continuity == Continuity.G1
                and e.p2.continuity == Continuity.G1
            ):
                return False
            if e.geometry() is None:
                return False
        for v in (e.p1, e.p2):
            if v.is_control or not vertex_has_curve_neighbor(edges, v):
                continue
            if v.continuity == Continuity.G0:
                continue
            incoming, outgoing = adjacent_edges(edges, v)
            if incoming is None or outgoing is None:
                continue
            tin = _incoming_tangent(incoming, v)
            tout = _outgoing_tangent(outgoing, v)
            if tin is None or tout is None:
                continue
            use_c1 = (
                v.continuity == Continuity.C1
                and not isinstance(incoming, ArcEdge)
                and not isinstance(outgoing, ArcEdge)
            )
            if use_c1:
                if abs(tin[0] - tout[0]) > eps or abs(tin[1] - tout[1]) > eps:
                    return False
            else:
                nin = normalize(tin[0], tin[1])
                nout = normalize(tout[0], tout[1])
                if nin is None or nout is None:
                    continue
                if abs(nin[0] - nout[0]) > eps or abs(nin[1] - nout[1]) > eps:
                    return False
    return True
