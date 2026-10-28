from __future__ import annotations

import math


def bernstein_to_power(
    p0: tuple[float, float],
    p1: tuple[float, float],
    p2: tuple[float, float],
    p3: tuple[float, float],
) -> tuple[tuple[float, float], tuple[float, float], tuple[float, float], tuple[float, float]]:
    """B(t) = A0 + A1 t + A2 t² + A3 t³ (z formy Bernsteina)."""
    a0 = p0
    a1 = (3 * (p1[0] - p0[0]), 3 * (p1[1] - p0[1]))
    a2 = (
        3 * (p2[0] - 2 * p1[0] + p0[0]),
        3 * (p2[1] - 2 * p1[1] + p0[1]),
    )
    a3 = (
        p3[0] - 3 * p2[0] + 3 * p1[0] - p0[0],
        p3[1] - 3 * p2[1] + 3 * p1[1] - p0[1],
    )
    return a0, a1, a2, a3


def cubic_forward_points(
    p0: tuple[float, float],
    p1: tuple[float, float],
    p2: tuple[float, float],
    p3: tuple[float, float],
    steps: int = 64,
) -> list[tuple[float, float]]:
    """
    Przyrostowe wyznaczanie punktów krzywej sześciennej:
    baza potęgowa - różnice skończone (forward differencing).
    """
    if steps < 1:
        steps = 1
    a0, a1, a2, a3 = bernstein_to_power(p0, p1, p2, p3)
    h = 1.0 / steps
    h2 = h * h
    h3 = h2 * h

    points = [a0]
    x, y = a0
    dx = a1[0] * h + a2[0] * h2 + a3[0] * h3
    dy = a1[1] * h + a2[1] * h2 + a3[1] * h3
    ddx = 2 * a2[0] * h2 + 6 * a3[0] * h3
    ddy = 2 * a2[1] * h2 + 6 * a3[1] * h3
    dddx = 6 * a3[0] * h3
    dddy = 6 * a3[1] * h3

    for _ in range(steps):
        x += dx
        y += dy
        dx += ddx
        dy += ddy
        ddx += dddx
        ddy += dddy
        points.append((x, y))
    return points


def vec_len(x: float, y: float) -> float:
    return math.hypot(x, y)


def normalize(x: float, y: float) -> tuple[float, float] | None:
    length = math.hypot(x, y)
    if length < 1e-9:
        return None
    return x / length, y / length
