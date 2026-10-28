from __future__ import annotations

Point2D = tuple[float, float]
BezierSegment = tuple[Point2D, Point2D, Point2D, Point2D]


def _lerp(a: Point2D, b: Point2D, t: float) -> Point2D:
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


def _mid(a: Point2D, b: Point2D) -> Point2D:
    return ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)


def _division_points(a: Point2D, b: Point2D, parts: int) -> list[Point2D]:
    if parts <= 1:
        return []
    return [_lerp(a, b, k / parts) for k in range(1, parts)]


class BSplineConstruction:
    def __init__(self, segments: list[BezierSegment], helper_points: list[Point2D]):
        self.segments = segments
        self.helper_points = helper_points


def build_closed_cubic_bspline(vertices: list[Point2D]) -> BSplineConstruction:
    n = len(vertices)
    if n < 3:
        return BSplineConstruction([], [])

    edge_pts = [_division_points(vertices[i], vertices[(i + 1) % n], 3) for i in range(n)]
    helper_points = [p for pts in edge_pts for p in pts]

    def near_start(i: int) -> Point2D:
        pts = edge_pts[i]
        return pts[0] if pts else vertices[i]

    def near_end(i: int) -> Point2D:
        pts = edge_pts[i]
        return pts[-1] if pts else vertices[(i + 1) % n]

    anchors = [_mid(near_end((i - 1) % n), near_start(i)) for i in range(n)]
    segments = [(anchors[i], near_start(i), near_end(i), anchors[(i + 1) % n]) for i in range(n)]
    return BSplineConstruction(segments, helper_points)


def build_open_cubic_bspline(vertices: list[Point2D]) -> BSplineConstruction:
    m = len(vertices) - 1
    if m < 1:
        return BSplineConstruction([], [])
    if m == 1:
        v0, v1 = vertices
        return BSplineConstruction([(v0, v0, v1, v1)], [])

    def parts_for_edge(i: int) -> int:
        d = min(i - 1, m - i)
        if d == 0:
            return 1
        if d == 1:
            return 2
        return 3

    edge_pts = [
        _division_points(vertices[i - 1], vertices[i], parts_for_edge(i))
        for i in range(1, m + 1)
    ]
    helper_points = [p for pts in edge_pts for p in pts]

    def near_start(i: int) -> Point2D:
        pts = edge_pts[i - 1]
        return pts[0] if pts else vertices[i - 1]

    def near_end(i: int) -> Point2D:
        pts = edge_pts[i - 1]
        return pts[-1] if pts else vertices[i]

    def edge_anchor(i: int) -> Point2D:
        return _mid(near_end(i), near_start(i + 1))

    if m == 2:
        segments = [(vertices[0], near_end(1), near_start(2), vertices[2])]
    elif m == 3:
        segments = [(vertices[0], near_end(1), near_start(3), vertices[3])]
    else:
        start_seg = (vertices[0], near_end(1), near_start(2), edge_anchor(2))
        end_seg = (edge_anchor(m - 2), near_start(m - 1), near_start(m), vertices[m])
        middle = [
            (edge_anchor(i - 1), near_start(i), near_end(i), edge_anchor(i))
            for i in range(3, m - 1)
        ]
        segments = [start_seg, *middle, end_seg]

    return BSplineConstruction(segments, helper_points)


def build_cubic_bspline(vertices: list[Point2D], closed: bool) -> BSplineConstruction:
    if closed:
        return build_closed_cubic_bspline(vertices)
    return build_open_cubic_bspline(vertices)
