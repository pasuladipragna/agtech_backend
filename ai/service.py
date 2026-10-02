from core.config import settings
from ai.provider import AIVisionProvider
from ai.openrouter import OpenRouterVisionProvider
from ai.mock_provider import MockVisionProvider

def get_ai_vision_provider() -> AIVisionProvider:
    if settings.USE_MOCK_AI_PROVIDER or not settings.OPENROUTER_API_KEY:
        return MockVisionProvider()
    return OpenRouterVisionProvider(
        models=settings.OPENROUTER_MODELS,
        strategy=settings.OPENROUTER_MODEL_STRATEGY,
    )
