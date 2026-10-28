from __future__ import annotations

import math


def rot90_ccw(x: float, y: float) -> tuple[float, float]:
    return (-y, x)


def rot90_cw(x: float, y: float) -> tuple[float, float]:
    return (y, -x)


def angle_of(dx: float, dy: float) -> float:
    return math.atan2(dy, dx)


def normalize_angle(a: float) -> float:
    while a <= -math.pi:
        a += 2 * math.pi
    while a > math.pi:
        a -= 2 * math.pi
    return a


def _angles_p1_p2(
    cx: float, cy: float, p1: tuple[float, float], p2: tuple[float, float]
) -> tuple[float, float]:
    a0 = angle_of(p1[0] - cx, p1[1] - cy)
    a1 = a0 + normalize_angle(angle_of(p2[0] - cx, p2[1] - cy) - a0)
    return a0, a1


def semicircle_geometry(
    p1: tuple[float, float],
    p2: tuple[float, float],
    side: int = 1,
) -> tuple[float, float, float, float, float] | None:
    x1, y1 = p1
    x2, y2 = p2
    chord = math.hypot(x2 - x1, y2 - y1)
    if chord < 1e-9:
        return None
    r = chord / 2.0
    cx, cy = (x1 + x2) / 2.0, (y1 + y2) / 2.0
    a0 = angle_of(x1 - cx, y1 - cy)
    sweep = math.pi if side >= 0 else -math.pi
    return cx, cy, r, a0, a0 + sweep


def arc_from_tangent(
    p1: tuple[float, float],
    p2: tuple[float, float],
    tangent_unit: tuple[float, float],
    *,
    at_p1: bool,
) -> tuple[float, float, float, float, float] | None:
    tx, ty = tangent_unit
    if at_p1:
        ax, ay = p1
        ox, oy = p2
        normals = (rot90_ccw(tx, ty), rot90_cw(tx, ty))
    else:
        ax, ay = p2
        ox, oy = p1
        normals = (rot90_cw(tx, ty), rot90_ccw(tx, ty))

    vx, vy = ax - ox, ay - oy
    chord2 = vx * vx + vy * vy
    best: tuple[float, float, float, float, float] | None = None
    best_abs_sweep = None

    for nx, ny in normals:
        denom = 2.0 * (nx * vx + ny * vy)
        if abs(denom) < 1e-12:
            continue
        r = -chord2 / denom
        if r <= 1e-9:
            continue
        cx, cy = ax + nx * r, ay + ny * r
        a0, a1 = _angles_p1_p2(cx, cy, p1, p2)
        sweep = a1 - a0
        a = a0 if at_p1 else a1
        if sweep >= 0:
            sx, sy = -math.sin(a), math.cos(a)
        else:
            sx, sy = math.sin(a), -math.cos(a)
        if sx * tx + sy * ty < 0.5:
            continue
        key = abs(a1 - a0)
        if best is None or key < best_abs_sweep:
            best = (cx, cy, r, a0, a1)
            best_abs_sweep = key

    return best


def sample_arc(
    cx: float,
    cy: float,
    r: float,
    a0: float,
    a1: float,
    steps: int = 64,
) -> list[tuple[float, float]]:
    if steps < 1:
        steps = 1
    da = a1 - a0
    return [
        (cx + r * math.cos(a0 + da * i / steps), cy + r * math.sin(a0 + da * i / steps))
        for i in range(steps + 1)
    ]


def tangent_on_arc(
    a0: float,
    a1: float,
    at_start: bool,
) -> tuple[float, float] | None:
    a = a0 if at_start else a1
    sweep = a1 - a0
    if sweep >= 0:
        tx, ty = -math.sin(a), math.cos(a)
    else:
        tx, ty = math.sin(a), -math.cos(a)
    length = math.hypot(tx, ty)
    if length < 1e-9:
        return None
    return tx / length, ty / length
