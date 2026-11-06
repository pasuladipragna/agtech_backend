"""Geometry-based field lane generation and coverage planning.

Coordinates are local metres. Camera/GPS calibration belongs at the boundary of
this module; the planner deliberately does not interpret image pixels.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import floor, hypot
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

Point = Tuple[float, float]


class LanePlanningError(ValueError):
    """Raised when field geometry or lane configuration is not usable."""


@dataclass(frozen=True)
class LaneConfig:
    lane_spacing_m: float = 0.8
    minimum_lane_spacing_m: float = 0.2
    maximum_lane_spacing_m: float = 10.0
    minimum_lane_length_m: float = 5.0
    rover_clearance_m: float = 0.5

    def validate(self) -> None:
        if not self.minimum_lane_spacing_m > 0:
            raise LanePlanningError("minimum lane spacing must be greater than zero")
        if self.maximum_lane_spacing_m < self.minimum_lane_spacing_m:
            raise LanePlanningError("maximum lane spacing must not be below the minimum")
        if not self.minimum_lane_spacing_m <= self.lane_spacing_m <= self.maximum_lane_spacing_m:
            raise LanePlanningError("lane spacing is outside the configured limits")
        if self.minimum_lane_length_m < 0 or self.rover_clearance_m < 0:
            raise LanePlanningError("minimum lane length and rover clearance cannot be negative")


def _normalise_polygon(polygon: Sequence[Sequence[float]]) -> List[Point]:
    if len(polygon) > 1 and polygon[0] == polygon[-1]:
        polygon = polygon[:-1]
    points = [(float(point[0]), float(point[1])) for point in polygon if len(point) >= 2]
    if len(points) < 3:
        raise LanePlanningError("field boundary must contain at least three points")
    return points


def _scanline_intervals(polygon: Sequence[Point], x: float) -> List[Tuple[float, float]]:
    intersections: List[float] = []
    for start, end in zip(polygon, polygon[1:] + polygon[:1]):
        x1, y1 = start
        x2, y2 = end
        if x1 == x2:
            continue
        if (x1 <= x < x2) or (x2 <= x < x1):
            intersections.append(y1 + (x - x1) * (y2 - y1) / (x2 - x1))
    intersections.sort()
    return [
        (intersections[index], intersections[index + 1])
        for index in range(0, len(intersections) - 1, 2)
        if intersections[index + 1] > intersections[index]
    ]


def _point_in_polygon(point: Point, polygon: Sequence[Point]) -> bool:
    x, y = point
    inside = False
    for first, second in zip(polygon, polygon[1:] + polygon[:1]):
        x1, y1 = first
        x2, y2 = second
        crosses = (y1 > y) != (y2 > y)
        if crosses and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


def _distance_to_segment(point: Point, start: Point, end: Point) -> float:
    dx, dy = end[0] - start[0], end[1] - start[1]
    if dx == 0 and dy == 0:
        return hypot(point[0] - start[0], point[1] - start[1])
    ratio = max(0.0, min(1.0, ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / (dx * dx + dy * dy)))
    closest = (start[0] + ratio * dx, start[1] + ratio * dy)
    return hypot(point[0] - closest[0], point[1] - closest[1])


def _lane_blocked(start: Point, end: Point, obstacles: Iterable[Dict[str, Any]], clearance: float) -> bool:
    for obstacle in obstacles:
        position = obstacle.get("position") or obstacle.get("center")
        if not position or len(position) < 2:
            continue
        radius = float(obstacle.get("radius_m", obstacle.get("radius", 0.0))) + clearance
        if _distance_to_segment((float(position[0]), float(position[1])), start, end) <= radius:
            return True
    return False


def generate_lanes(
    boundary: Sequence[Sequence[float]],
    config: LaneConfig,
    obstacles: Optional[Iterable[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Generate clipped parallel lanes and a boustrophedon route."""
    config.validate()
    polygon = _normalise_polygon(boundary)
    obstacles = list(obstacles or [])
    min_x = min(point[0] for point in polygon)
    max_x = max(point[0] for point in polygon)
    min_y = min(point[1] for point in polygon)
    max_y = max(point[1] for point in polygon)
    usable_width = max_x - min_x
    usable_length = max_y - min_y
    expected_count = floor(usable_width / config.lane_spacing_m)

    lanes: List[Dict[str, Any]] = []
    for index in range(expected_count):
        x = min_x + (index + 0.5) * config.lane_spacing_m
        intervals = _scanline_intervals(polygon, x)
        if not intervals:
            continue
        start_y, end_y = max(intervals, key=lambda pair: pair[1] - pair[0])
        if end_y - start_y < config.minimum_lane_length_m:
            continue
        start, end = (x, start_y), (x, end_y)
        blocked = _lane_blocked(start, end, obstacles, config.rover_clearance_m)
        lanes.append({
            "lane_id": len(lanes) + 1,
            "start": [round(start[0], 3), round(start[1], 3)],
            "end": [round(end[0], 3), round(end[1], 3)],
            "length_m": round(end_y - start_y, 3),
            "direction": "FORWARD" if len(lanes) % 2 == 0 else "REVERSE",
            "status": "BLOCKED" if blocked else "PENDING",
            "blocked": blocked,
            "coverage": 0.0,
        })

    valid_lanes = [lane for lane in lanes if not lane["blocked"]]
    route: List[Dict[str, float]] = []
    for lane in valid_lanes:
        points = (lane["start"], lane["end"]) if lane["direction"] == "FORWARD" else (lane["end"], lane["start"])
        route.extend({"x": point[0], "y": point[1], "lane_id": lane["lane_id"]} for point in points)

    return {
        "boundary": [[point[0], point[1]] for point in polygon],
        "usable_width_m": round(usable_width, 3),
        "usable_length_m": round(usable_length, 3),
        "usable_area_m2": round(_polygon_area(polygon), 3),
        "lane_spacing_m": config.lane_spacing_m,
        "lane_count": len(lanes),
        "valid_lane_count": len(valid_lanes),
        "lanes": lanes,
        "route": route,
    }


def _polygon_area(polygon: Sequence[Point]) -> float:
    return abs(sum(first[0] * second[1] - second[0] * first[1] for first, second in zip(polygon, polygon[1:] + polygon[:1])) / 2)


def recalculate_route(previous: Optional[Dict[str, Any]], current: Dict[str, Any]) -> Dict[str, Any]:
    """Preserve completed lanes by stable geometry identity during recalculation."""
    completed = {
        (tuple(lane["start"]), tuple(lane["end"]))
        for lane in (previous or {}).get("lanes", [])
        if lane.get("status") == "COMPLETED"
    }
    for lane in current.get("lanes", []):
        if (tuple(lane["start"]), tuple(lane["end"])) in completed:
            lane["status"] = "COMPLETED"
            lane["coverage"] = 100.0
    return current