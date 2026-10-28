from __future__ import annotations

from models.point import Point
from models.polygon import Polygon
from models.solver import ConstraintSolver
from models.constraints import edge_length
from core.enums import Continuity


POLYGON_SPECS: list[list[tuple[float, float]]] = [
    [(80, 80), (280, 80), (280, 220), (80, 220)],
    [(360, 100), (520, 100), (440, 240)],
]


def build_polygons() -> list[Polygon]:
    return [
        Polygon([Point(x, y) for x, y in coords])
        for coords in POLYGON_SPECS
    ]


def apply_demo_relations(
    polygons: list[Polygon],
    solver: ConstraintSolver,
) -> None:
    if len(polygons) < 2:
        return

    rect, tri = polygons[0], polygons[1]

    top, right, bottom, left = (
        rect.edges[0], rect.edges[1], rect.edges[2], rect.edges[3]
    )
    tri_base, tri_left = tri.edges[0], tri.edges[2]

    rect.set_edge_bezier(right)
    for v in (right.p1, right.p2):
        if not v.continuity_explicit:
            v.continuity = Continuity.G1
            v.continuity_explicit = True

    tri.set_edge_arc(tri_left)

    solver.try_add_length(
        left.p1, left.p2, edge_length(left.p1, left.p2), polygons
    )
    solver.try_add_parallel(top.p1, top.p2, bottom.p1, bottom.p2, polygons)
    solver.try_add_parallel(top.p1, top.p2, tri_base.p1, tri_base.p2, polygons)

    solver.propagate_repair(polygons)
