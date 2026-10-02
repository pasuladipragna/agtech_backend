"""Replaceable obstacle detection adapter used by lane validation."""

from typing import Any, Dict, Iterable, List


class ObstacleDetectionService:
    def __init__(self, model: Any = None):
        self.model = model

    def detect_obstacles(self, frame: Any) -> List[Dict[str, Any]]:
        if self.model is None:
            return []
        return [self._normalise(item) for item in self.model.detect_obstacles(frame)]

    def get_obstacle_coordinates(self, obstacles: Iterable[Dict[str, Any]]) -> List[List[float]]:
        return [list(obstacle["position"]) for obstacle in obstacles if obstacle.get("position")]

    def _normalise(self, obstacle: Dict[str, Any]) -> Dict[str, Any]:
        position = obstacle.get("position") or obstacle.get("center")
        if not position or len(position) < 2:
            raise ValueError("obstacle position must contain x and y")
        return {
            "type": obstacle.get("type", "UNKNOWN"),
            "position": [float(position[0]), float(position[1])],
            "radius_m": max(0.0, float(obstacle.get("radius_m", obstacle.get("radius", 0.0)))),
            "confidence": max(0.0, min(1.0, float(obstacle.get("confidence", 1.0)))),
        }