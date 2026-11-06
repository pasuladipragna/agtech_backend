import os
import io
import uuid
import logging
import cloudinary
import cloudinary.uploader
from PIL import Image
from core.config import settings

logger = logging.getLogger("MediaService")

if settings.CLOUDINARY_API_KEY and settings.CLOUDINARY_CLOUD_NAME:
    cloudinary.config(
        cloud_name=settings.CLOUDINARY_CLOUD_NAME,
        api_key=settings.CLOUDINARY_API_KEY,
        api_secret=settings.CLOUDINARY_API_SECRET,
        secure=True
    )

class MediaStorageService:
    def __init__(self):
        self.upload_dir = os.path.join(os.getcwd(), "uploads")
        os.makedirs(self.upload_dir, exist_ok=True)

    async def upload_evidence_image(self, image_data: bytes, filename: str) -> str:
        if settings.CLOUDINARY_API_KEY and not settings.USE_LOCAL_MEDIA_FALLBACK:
            try:
                res = cloudinary.uploader.upload(
                    image_data,
                    folder="agritech_evidence",
                    public_id=f"evidence_{uuid.uuid4().hex[:8]}"
                )
                logger.info(f"Uploaded evidence image to Cloudinary: {res.get('secure_url')}")
                return {
                    "url": res.get("secure_url"),
                    "public_id": res.get("public_id"),
                }
            except Exception as e:
                logger.error(f"Cloudinary upload failed ({e}). Falling back to local storage.")

        file_ext = os.path.splitext(filename)[1] or ".jpg"
        unique_name = f"{uuid.uuid4().hex[:12]}{file_ext}"
        file_path = os.path.join(self.upload_dir, unique_name)
        
        with open(file_path, "wb") as f:
            f.write(image_data)
            
        local_url = f"/static/uploads/{unique_name}"
        logger.info(f"Saved evidence image locally: {local_url}")
        return {"url": local_url, "public_id": None}

media_service = MediaStorageService()
