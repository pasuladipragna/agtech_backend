"""
Smart AgriTech Rover Platform — Main Entry Point
Modular monolith configuration. Includes CORS, database init, and static media serving.
"""

import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from core.database import engine, Base, ensure_database_schema
from modules.router import api_router
from modules.extra_routes import extra_router
from core.config import settings
from services.telegram_bot import TelegramBotPoller

# Ensure tables are created and compatible with any stale SQLite schema
Base.metadata.create_all(bind=engine)
ensure_database_schema(engine)

app = FastAPI(
    title="Smart AgriTech Rover API",
    description="Backend API for managing farms, crop health, rovers, and AI detections.",
    version="1.0.0",
)

# CORS Middleware (Restrict this in production!)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "*"],  # Update wildcard for production
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
def start_telegram_bot() -> None:
    telegram_bot.start()


@app.on_event("shutdown")
def stop_telegram_bot() -> None:
    telegram_bot.stop()

@app.get("/")
def read_root():
    return {"message": "Smart AgriTech Rover API is running."}

@app.get("/health")
def health_check():
    return {"status": "healthy"}
