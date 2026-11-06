import base64
import json
import logging
import re
import httpx
from typing import List, Dict, Any
from core.config import settings
from ai.provider import AIVisionProvider, DiseaseDetectionResult, VideoKeyframeAnalysisResult

logger = logging.getLogger("OpenRouterAI")


def _parse_model_json(content: Any) -> dict:
    """Extract the first JSON object from plain text or a markdown code fence."""
    if isinstance(content, list):
        content = "".join(
            part.get("text", "") if isinstance(part, dict) else str(part)
            for part in content
        )
    if not isinstance(content, str):
        raise ValueError("OpenRouter returned an unsupported response format")

    cleaned = content.strip()
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.IGNORECASE)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(0))


def _extract_response_content(response_data: dict) -> str:
    """Extract text from the response shapes used by OpenRouter providers."""
    choices = response_data.get("choices") or []
    if not choices:
        raise ValueError("OpenRouter response did not contain choices")

    message = choices[0].get("message") or {}
    content = message.get("content")
    if isinstance(content, str) and content.strip():
        return content

    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, dict):
                text = part.get("text") or part.get("content") or part.get("output_text")
                if text:
                    parts.append(str(text))
        if parts:
            return "".join(parts)

    for key in ("output_text", "reasoning"):
        value = message.get(key)
        if isinstance(value, str) and value.strip():
            return value

    raise ValueError("OpenRouter response did not contain usable message text")

class OpenRouterVisionProvider(AIVisionProvider):
    def __init__(self, api_key: str = None, model: str = None, models: str = None, strategy: str = None):
        self.api_key = api_key or settings.OPENROUTER_API_KEY
        self.strategy = (strategy or settings.OPENROUTER_MODEL_STRATEGY).lower()
        configured_models = models if models is not None else settings.OPENROUTER_MODELS
        self.models = self._select_models(configured_models, model or settings.OPENROUTER_MODEL)
        self.endpoint = "https://openrouter.ai/api/v1/chat/completions"

    def _select_models(self, configured_models: str, default_model: str) -> List[str]:
        profiles = {
            "fast": [
                "inclusionai/ling-3.0-flash-vl:free",
                "nex-agi/nex-n2.5-mini:free",
                "qwen/qwen3.8-27b:free",
            ],
            "accurate": [
                "nex-agi/nex-n2.5-pro:free",
                "qwen/qwen3.8-27b:free",
                "inclusionai/ling-3.0-flash-vl:free",
            ],
            "balanced": [
                "inclusionai/ling-3.0-flash-vl:free",
                "nex-agi/nex-n2.5-pro:free",
                "qwen/qwen3.8-27b:free",
            ],
        }
        if configured_models.strip():
            candidates = [item.strip() for item in configured_models.split(",") if item.strip()]
        else:
            candidates = profiles.get(self.strategy, profiles["balanced"])
            if default_model and default_model.endswith(":free") and default_model not in candidates:
                candidates.append(default_model)
        return list(dict.fromkeys(item for item in candidates if item.endswith(":free")))

    async def analyze_crop_image(self, image_data: bytes, filename: str) -> DiseaseDetectionResult:
        if not self.api_key:
            from ai.mock_provider import MockVisionProvider
            return await MockVisionProvider().analyze_crop_image(image_data, filename)

        b64_image = base64.b64encode(image_data).decode("utf-8")
        system_prompt = (
            "You are an expert agricultural plant pathologist AI. Analyze the image conservatively. "
            "First decide whether a recognizable plant or crop tissue is actually visible. "
            "If no plant is visible, set plant_present=false, is_healthy=true, category=Healthy, "
            "label=No plant detected, severity=None, and recommended_spray_volume_l_per_ha=0. "
            "Never call an image a disease without visible evidence of plant tissue and symptoms. "
            "Respond ONLY with a JSON object strictly matching this schema: "
            "{\n"
            '  "plant_present": bool,\n'
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

        async with httpx.AsyncClient(timeout=30.0) as client:
            for model in self.models:
                payload = {
                    "model": model,
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
                }
                try:
                    response = await client.post(self.endpoint, headers=headers, json=payload)
                    if response.is_error:
                        logger.warning(
                            "OpenRouter model '%s' returned %s: %s",
                            model,
                            response.status_code,
                            response.text[:500],
                        )
                    response.raise_for_status()
                    res_data = response.json()
                    content = _extract_response_content(res_data)
                    logger.info("OpenRouter model '%s' response preview: %s", model, content[:240].replace("\n", " "))
                    parsed = _parse_model_json(content)
                    result = DiseaseDetectionResult(**parsed)
                    logger.info("Crop analysis completed with OpenRouter model '%s'.", model)
                    print(
                        "[DISEASE DETECTION] "
                        f"status=SUCCESS model={model} "
                        f"plant_present={result.plant_present} "
                        f"healthy={result.is_healthy} "
                        f"label={result.label!r} "
                        f"confidence={result.confidence:.2f}",
                        flush=True,
                    )
                    return result
                except Exception as e:
                    logger.warning("OpenRouter model '%s' failed: %s. Trying the next model.", model, e)

        logger.error("All configured OpenRouter models failed. Falling back to MockVisionProvider.")
        print(
            "[DISEASE DETECTION] status=UNAVAILABLE "
            "reason=all_configured_openrouter_models_failed",
            flush=True,
        )
        from ai.mock_provider import MockVisionProvider
        return await MockVisionProvider().analyze_crop_image(image_data, filename)

    async def analyze_video_keyframes(self, keyframe_images: List[bytes]) -> VideoKeyframeAnalysisResult:
        from ai.mock_provider import MockVisionProvider
        return await MockVisionProvider().analyze_video_keyframes(keyframe_images)
