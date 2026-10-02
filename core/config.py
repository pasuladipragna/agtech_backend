import os
from pathlib import Path
from typing import List
from pydantic_settings import BaseSettings

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BASE_DIR / ".env"

if ENV_FILE.exists():
    from dotenv import load_dotenv
    load_dotenv(ENV_FILE, override=False)

class Settings(BaseSettings):
    ENV: str = os.getenv("ENV", "development")
    PROJECT_NAME: str = "Smart AgriTech Platform API"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"
    
    SECRET_KEY: str = os.getenv("SECRET_KEY", "agritech-super-secret-key-change-in-production-2026")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days
    
    # CORS
    CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "*"
    ]
    
    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./smart_agritech.db")
    
    # MQTT Settings
    MQTT_BROKER_HOST: str = os.getenv("MQTT_BROKER_HOST", "localhost")
    MQTT_BROKER_PORT: int = int(os.getenv("MQTT_BROKER_PORT", "1883"))
    MQTT_TOPIC_PREFIX: str = os.getenv("MQTT_TOPIC_PREFIX", "agritech/rover")
    
    # Cloudinary
    CLOUDINARY_CLOUD_NAME: str = os.getenv("CLOUDINARY_CLOUD_NAME", "demo_agritech")
    CLOUDINARY_API_KEY: str = os.getenv("CLOUDINARY_API_KEY", "")
    CLOUDINARY_API_SECRET: str = os.getenv("CLOUDINARY_API_SECRET", "")
    USE_LOCAL_MEDIA_FALLBACK: bool = os.getenv("USE_LOCAL_MEDIA_FALLBACK", "true").lower() == "true"

    # Email / SMS notification settings
    EMAIL_SMTP_HOST: str = os.getenv("EMAIL_SMTP_HOST", "")
    EMAIL_SMTP_PORT: int = int(os.getenv("EMAIL_SMTP_PORT", "587"))
    EMAIL_SMTP_USER: str = os.getenv("EMAIL_SMTP_USER", "")
    EMAIL_SMTP_PASSWORD: str = os.getenv("EMAIL_SMTP_PASSWORD", "")
    EMAIL_FROM: str = os.getenv("EMAIL_FROM", "")
    EMAIL_FROM_NAME: str = os.getenv("EMAIL_FROM_NAME", "Smart AgriTech Rover")

    SMS_FAST2SMS_API_KEY: str = os.getenv("SMS_FAST2SMS_API_KEY", "")
    SMS_FAST2SMS_ROUTE: str = os.getenv("SMS_FAST2SMS_ROUTE", "q")
    SMS_TWILIO_ACCOUNT_SID: str = os.getenv("SMS_TWILIO_ACCOUNT_SID", "")
    SMS_TWILIO_AUTH_TOKEN: str = os.getenv("SMS_TWILIO_AUTH_TOKEN", "")
    SMS_FROM_PHONE: str = os.getenv("SMS_FROM_PHONE", "")
    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID", "")
    NEXT_PUBLIC_APP_URL: str = os.getenv("NEXT_PUBLIC_APP_URL", "http://localhost:3000")
    
    # AI OpenRouter
    OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")
    OPENROUTER_MODEL: str = os.getenv("OPENROUTER_MODEL", "inclusionai/ling-3.0-flash-vl:free")
    OPENROUTER_MODELS: str = os.getenv("OPENROUTER_MODELS", "")
    OPENROUTER_MODEL_STRATEGY: str = os.getenv("OPENROUTER_MODEL_STRATEGY", "balanced")
    USE_MOCK_AI_PROVIDER: bool = os.getenv("USE_MOCK_AI_PROVIDER", "true").lower() == "true"

    class Config:
        case_sensitive = True

settings = Settings()
