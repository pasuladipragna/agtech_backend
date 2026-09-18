import base64
import time
import io
import math
from typing import Dict, Any
from PIL import Image, ImageDraw

class CameraStreamer:
    def __init__(self):
        self.resolution = (640, 480)
        self.frame_rate = 10
        self.last_capture_time = 0

    def generate_simulated_frame(self, telemetry: Dict[str, Any]) -> str:
        img = Image.new("RGB", self.resolution, color=(34, 52, 34))
        draw = ImageDraw.Draw(img)

        draw.polygon([(100, 480), (280, 200), (360, 200), (540, 480)], fill=(70, 50, 30))
        
        for i in range(5):
            y = 220 + i * 50
            draw.ellipse([60 - i*10, y, 120 + i*5, y + 40], fill=(46, 139, 87))
            draw.ellipse([520 - i*5, y, 580 + i*10, y + 40], fill=(46, 139, 87))

        if math.sin(time.time()) > 0.3:
            draw.rectangle([70, 300, 150, 380], outline=(255, 69, 0), width=3)
            draw.text((75, 280), "AI ALERT: Early Blight (94%)", fill=(255, 69, 0))

        draw.rectangle([0, 0, 640, 40], fill=(0, 0, 0, 180))
        hud_text = (
            f"ROVER: 4WD-01 | BATT: {telemetry.get('battery_pct', 0)}% | "
            f"TANK: {telemetry.get('spray_tank_pct', 0)}% | "
            f"LAT: {telemetry.get('latitude', 0):.4f} LNG: {telemetry.get('longitude', 0):.4f}"
        )
        draw.text((10, 12), hud_text, fill=(255, 255, 255))

        if telemetry.get("pump_active", False):
            draw.rectangle([500, 430, 630, 470], fill=(0, 150, 255))
            draw.text((510, 445), "SPRAY ACTIVE", fill=(255, 255, 255))

        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=75)
        encoded = base64.b64encode(buffer.getvalue()).decode("utf-8")
        return f"data:image/jpeg;base64,{encoded}"
