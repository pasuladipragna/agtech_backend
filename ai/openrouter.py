import base64
import json
import logging
import httpx
from typing import List, Dict, Any
from core.config import settings
from ai.provider import AIVisionProvider, DiseaseDetectionResult, VideoKeyframeAnalysisResult

logger = logging.getLogger("OpenRouterAI")

class OpenRouterVisionProvider(AIVisionProvider):
    def __init__(self, api_key: str = None, model: str = None):
        self.api_key = api_key or settings.OPENROUTER_API_KEY
        self.model = model or settings.OPENROUTER_MODEL
        self.endpoint = "https://openrouter.ai/api/v1/chat/completions"

    async def analyze_crop_image(self, image_data: bytes, filename: str) -> DiseaseDetectionResult:
        if not self.api_key:
            from ai.mock_provider import MockVisionProvider
            return await MockVisionProvider().analyze_crop_image(image_data, filename)

        b64_image = base64.b64encode(image_data).decode("utf-8")
        system_prompt = (
            "You are an expert agricultural plant pathologist AI. Analyze the image of the crop. "
            "Respond ONLY with a JSON object strictly matching this schema: "
            "{\n"
            '  "is_healthy": bool,\n'
            '  "label": string,\n'
            '  "confidence": float (0 to 1),\n'
            '  "severity": "None" | "Low" | "Medium" | "High" | "Critical",\n'
            '  "category": "Healthy" | "Fungus" | "Pest" | "Bacteria" | "Nutrient Deficiency",\n'
            '  "recommended_treatment": string,\n'
            '  "recommended_spray_volume_l_per_ha": float,\n'
            '  "description": string\n'
            "}"
        )

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "HTTP-Referer": "https://agritech-rover.org",
            "X-Title": "Smart AgriTech Rover Platform",
            "Content-Type": "application/json"
        }

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": f"Analyze crop health for file: {filename}"},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_image}"}}
                    ]
                }
            ],
            "response_format": {"type": "json_object"}
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(self.endpoint, headers=headers, json=payload)
                response.raise_for_status()
                res_data = response.json()
                content = res_data["choices"][0]["message"]["content"]
                parsed = json.loads(content)
                return DiseaseDetectionResult(**parsed)
        except Exception as e:
            logger.error(f"OpenRouter API call failed ({e}). Falling back to MockVisionProvider.")
            from ai.mock_provider import MockVisionProvider
            return await MockVisionProvider().analyze_crop_image(image_data, filename)

    async def analyze_video_keyframes(self, keyframe_images: List[bytes]) -> VideoKeyframeAnalysisResult:
        from ai.mock_provider import MockVisionProvider
        return await MockVisionProvider().analyze_video_keyframes(keyframe_images)
