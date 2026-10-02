from typing import List, Dict, Any
from ai.provider import AIVisionProvider, DiseaseDetectionResult, VideoKeyframeAnalysisResult

MOCK_DISEASES = [
    {
        "is_healthy": False,
        "label": "Tomato Early Blight (Alternaria solani)",
        "confidence": 0.94,
        "severity": "Medium",
        "category": "Fungus",
        "recommended_treatment": "Apply Copper Hydroxide fungicide (2.5g/L). Repeat after 7-10 days if humid conditions persist.",
        "recommended_spray_volume_l_per_ha": 350.0,
        "description": "Concentric dark brown leaf spots detected on lower foliage. Early stage of Alternaria fungal infection."
    },
    {
        "is_healthy": False,
        "label": "Corn Armyworm Infestation (Spodoptera frugiperda)",
        "confidence": 0.91,
        "severity": "High",
        "category": "Pest",
        "recommended_treatment": "Apply Bacillus thuringiensis (Bt) or Chlorantraniliprole precision spray focused on whorls.",
        "recommended_spray_volume_l_per_ha": 400.0,
        "description": "Foliage chewing damage and frass identified in corn canopy whorls."
    },
    {
        "is_healthy": False,
        "label": "Wheat Striped Rust (Puccinia striiformis)",
        "confidence": 0.88,
        "severity": "Critical",
        "category": "Fungus",
        "recommended_treatment": "Immediate application of Tebuconazole + Azoxystrobin systemic fungicide.",
        "recommended_spray_volume_l_per_ha": 500.0,
        "description": "Linear yellow-orange pustules along leaf veins. Rapid leaf tissue necrosis imminent."
    },
    {
        "is_healthy": True,
        "label": "Healthy Foliage (Soybean / Canopy)",
        "confidence": 0.98,
        "severity": "None",
        "category": "Healthy",
        "recommended_treatment": "No chemical treatment required. Maintain current irrigation schedule.",
        "recommended_spray_volume_l_per_ha": 0.0,
        "description": "Vibrant green leaves, uniform chlorophyll density, zero sign of pest or fungal lesions."
    }
]

class MockVisionProvider(AIVisionProvider):
    async def analyze_crop_image(self, image_data: bytes, filename: str) -> DiseaseDetectionResult:
        import random
        # Pick a random mock disease to simulate a real detection
        det = random.choice(MOCK_DISEASES)
        return DiseaseDetectionResult(
            analysis_available=True,
            plant_present=True,
            is_healthy=det["is_healthy"],
            label=det["label"],
            confidence=det["confidence"],
            severity=det["severity"],
            category=det["category"],
            recommended_treatment=det["recommended_treatment"],
            recommended_spray_volume_l_per_ha=det["recommended_spray_volume_l_per_ha"],
            description=det["description"],
        )

    async def analyze_video_keyframes(self, keyframe_images: List[bytes]) -> VideoKeyframeAnalysisResult:
        useful_frames = []
        for idx, img in enumerate(keyframe_images):
            if idx % 2 == 0 or idx == len(keyframe_images) - 1:
                det = MOCK_DISEASES[idx % len(MOCK_DISEASES)]
                useful_frames.append({
                    "frame_index": idx * 15,
                    "timestamp_sec": round(idx * 1.5, 1),
                    "is_useful_evidence": True,
                    "detection": det,
                    "evidence_image_name": f"frame_evidence_{idx+1}.jpg"
                })

        return VideoKeyframeAnalysisResult(
            total_frames_analyzed=len(keyframe_images) * 15,
            useful_evidence_frames=useful_frames,
            summary=f"Extracted {len(useful_frames)} high-value evidence keyframes out of {len(keyframe_images)*15} scanned frames."
        )
