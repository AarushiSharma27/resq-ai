from __future__ import annotations

import math

EARTH_R = 6_371_000.0


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_R * math.asin(math.sqrt(a))


def bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    x = math.sin(dl) * math.cos(p2)
    y = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def polyline_length_m(points: list[list[float]]) -> float:
    return sum(haversine_m(a[0], a[1], b[0], b[1]) for a, b in zip(points, points[1:]))


def point_along(points: list[list[float]], fraction: float) -> tuple[float, float, float]:
    """Interpolate (lat, lon, heading) at `fraction` (0..1) of a polyline's length."""
    if not points:
        raise ValueError("empty polyline")
    if len(points) == 1 or fraction <= 0:
        a = points[0]
        b = points[1] if len(points) > 1 else a
        return a[0], a[1], bearing_deg(a[0], a[1], b[0], b[1])
    total = polyline_length_m(points)
    target = min(max(fraction, 0.0), 1.0) * total
    walked = 0.0
    for a, b in zip(points, points[1:]):
        seg = haversine_m(a[0], a[1], b[0], b[1])
        if walked + seg >= target and seg > 0:
            t = (target - walked) / seg
            return a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, bearing_deg(a[0], a[1], b[0], b[1])
        walked += seg
    a, b = points[-2], points[-1]
    return b[0], b[1], bearing_deg(a[0], a[1], b[0], b[1])
