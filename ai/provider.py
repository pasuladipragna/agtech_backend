from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from pydantic import BaseModel

class DiseaseDetectionResult(BaseModel):
    is_healthy: bool
    label: str
    confidence: float
    severity: str
    category: str
    bounding_box: Optional[List[float]] = None
    recommended_treatment: str
    recommended_spray_volume_l_per_ha: float
    description: str

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
