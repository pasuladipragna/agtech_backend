"""Replaceable field-detection and camera-calibration boundary.

The default implementation only consumes model output supplied by a caller. It
does not infer physical dimensions from raw pixels or invent calibration data.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Sequence


@dataclass(frozen=True)
class CameraCalibration:
    camera_matrix: Optional[Sequence[Sequence[float]]] = None
    distortion_coefficients: Optional[Sequence[float]] = None
    homography_matrix: Optional[Sequence[Sequence[float]]] = None
    camera_height_m: Optional[float] = None
    camera_angle_deg: Optional[float] = None

    def validate(self) -> None:
        if self.homography_matrix is not None:
            if len(self.homography_matrix) != 3 or any(len(row) != 3 for row in self.homography_matrix):
                raise ValueError("homography_matrix must be a 3 by 3 matrix")
        if self.camera_height_m is not None and self.camera_height_m <= 0:
            raise ValueError("camera_height_m must be greater than zero")


class FieldDetectionService:
    """Adapter for a future segmentation model and calibrated field mapping."""

    def __init__(self, model: Any = None, calibration: Optional[CameraCalibration] = None):
        self.model = model
        self.calibration = calibration or CameraCalibration()
        self.calibration.validate()

    def detect_field(self, frame: Any) -> Dict[str, Any]:
        if self.model is None:
            return {"field_detected": False, "confidence": 0.0, "reason": "FIELD_MODEL_NOT_CONFIGURED"}
        result = self.model.detect_field(frame)
        return self.normalise_result(result)

    def detect_boundary(self, frame: Any) -> Optional[list]:
        result = self.detect_field(frame)
        return result.get("boundary")

    def estimate_field_width(self, field: Dict[str, Any]) -> Optional[float]:
        return field.get("estimated_width_m")

    def estimate_field_length(self, field: Dict[str, Any]) -> Optional[float]:
        return field.get("estimated_length_m")

    def get_usable_field_area(self, field: Dict[str, Any]) -> Optional[float]:
        return field.get("usable_area_m2")

    def normalise_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        confidence = float(result.get("confidence", 0.0))
        boundary = result.get("boundary") or result.get("field_polygon")
        return {
            "field_detected": bool(result.get("field_detected", boundary is not None)),
            "boundary": boundary,
            "left_boundary": result.get("left_boundary"),
            "right_boundary": result.get("right_boundary"),
            "estimated_width_m": result.get("estimated_width_m"),
            "estimated_length_m": result.get("estimated_length_m"),
            "usable_area_m2": result.get("usable_area_m2"),
            "confidence": max(0.0, min(1.0, confidence)),
        }

    def pixel_to_local(self, point: Sequence[float]) -> list:
        if not self.calibration.homography_matrix:
            raise ValueError("homography_matrix is required for pixel-to-local conversion")
        x, y = float(point[0]), float(point[1])
        matrix = self.calibration.homography_matrix
        denominator = matrix[2][0] * x + matrix[2][1] * y + matrix[2][2]
        if denominator == 0:
            raise ValueError("homography maps the point to infinity")
        return [
            (matrix[0][0] * x + matrix[0][1] * y + matrix[0][2]) / denominator,
            (matrix[1][0] * x + matrix[1][1] * y + matrix[1][2]) / denominator,
        ]