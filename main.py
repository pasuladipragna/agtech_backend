"""
Smart AgriTech Rover Platform — Main Entry Point
Modular monolith configuration. Includes CORS, database init, and static media serving.
"""

import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from core.database import engine, Base
from modules.router import api_router
from core.config import settings

# Ensure tables are created
Base.metadata.create_all(bind=engine)

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

@app.get("/")
def read_root():
    return {"message": "Smart AgriTech Rover API is running."}

@app.get("/health")
def health_check():
    return {"status": "healthy"}
