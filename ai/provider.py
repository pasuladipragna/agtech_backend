from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from pydantic import BaseModel

class DiseaseDetectionResult(BaseModel):
    analysis_available: bool = True
    plant_present: bool = True
    is_healthy: bool
    label: str
    confidence: float
    severity: str
    category: str
    bounding_box: Optional[List[float]] = None
    recommended_treatment: str
    recommended_spray_volume_l_per_ha: float
    description: str

    def model_post_init(self, __context: Any) -> None:
        if not self.plant_present:
            self.is_healthy = True
            self.label = "No plant detected"
            self.confidence = min(self.confidence, 0.99)
            self.severity = "None"
            self.category = "Healthy"
            self.recommended_treatment = "No treatment recommended. Capture a clear image of the plant or leaf."
            self.recommended_spray_volume_l_per_ha = 0.0
            self.description = "No plant or usable crop tissue was detected in the image."

    @property
    def detection_type(self) -> str:
        """Translate provider categories to the database detection vocabulary."""
        category_map = {
            "Healthy": "Healthy",
            "Fungus": "Disease",
            "Bacteria": "Disease",
            "Pest": "Pest",
            "Nutrient Deficiency": "Nutrient Deficiency",
        }
        return category_map.get(self.category, "Other Abnormality")

    @property
    def recommendations(self) -> str:
        """Compatibility name used by persisted crop-health records."""
        return self.recommended_treatment

class VideoKeyframeAnalysisResult(BaseModel):
    total_frames_analyzed: int
    useful_evidence_frames: List[Dict[str, Any]]
    summary: str

class AIVisionProvider(ABC):
    @abstractmethod
    async def analyze_crop_image(self, image_data: bytes, filename: str) -> DiseaseDetectionResult:
        pass

    @abstractmethod
    async def analyze_video_keyframes(self, keyframe_images: List[bytes]) -> VideoKeyframeAnalysisResult:
        pass
