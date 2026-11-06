"""
Smart AgriTech Rover Platform — Main Entry Point
Modular monolith configuration. Includes CORS, database init, and static media serving.
"""

import asyncio
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from core.database import engine, Base, ensure_database_schema
from modules.router import api_router
from modules.extra_routes import extra_router
from core.config import settings
from services.telegram_bot import TelegramBotPoller
from iot.mqtt import mqtt_bridge

# Ensure tables are created and compatible with any stale SQLite schema
Base.metadata.create_all(bind=engine)
ensure_database_schema(engine)

app = FastAPI(
    title="Smart AgriTech Rover API",
    description="Backend API for managing farms, crop health, rovers, and AI detections.",
    version="1.0.0",
)

# CORS origins are configured per environment through CORS_ORIGINS.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount media directory for local storage fallback
os.makedirs("media_storage", exist_ok=True)
app.mount("/media", StaticFiles(directory="media_storage"), name="media")

# Include main router
app.include_router(api_router, prefix="/api/v1")
app.include_router(extra_router, prefix="/api/v1")

telegram_bot = TelegramBotPoller(settings.TELEGRAM_BOT_TOKEN)


@app.on_event("startup")
async def on_startup() -> None:
    telegram_bot.start()
    # Start the MQTT bridge so the backend can talk to the Raspberry Pi rover(s).
    # The bridge subscribes to telemetry topics and forwards commands from the API.
    loop = asyncio.get_event_loop()
    mqtt_bridge.start(loop)


@app.on_event("shutdown")
def on_shutdown() -> None:
    telegram_bot.stop()
    try:
        mqtt_bridge.client.loop_stop()
        mqtt_bridge.client.disconnect()
    except Exception:
        pass

@app.get("/")
def read_root():
    return {"message": "Smart AgriTech Rover API is running."}

@app.get("/health")
def health_check():
    return {"status": "healthy"}
