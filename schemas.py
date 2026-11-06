from datetime import datetime
from typing import Optional, List, Any
from pydantic import BaseModel

class UserLogin(BaseModel):
    email: str
    password: str

class UserRegister(BaseModel):
    email: str
    password: str
    full_name: str
    role: Optional[str] = "farmer"
    phone: Optional[str] = None

class UserOut(BaseModel):
    id: int
    email: str
    full_name: str
    role: str
    phone: Optional[str]
    is_active: bool
    created_at: datetime
    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str
    user: UserOut

class FarmCreate(BaseModel):
    name: str
    location_name: str
    latitude: float
    longitude: float
    total_area_hectares: Optional[float] = 10.0

class FarmOut(BaseModel):
    id: int
    name: str
    location_name: str
    latitude: float
    longitude: float
    total_area_hectares: float
    created_at: datetime
    class Config:
        from_attributes = True

class FieldCreate(BaseModel):
    farm_id: int
    name: str
    boundary_polygon: Optional[List[List[float]]] = None
    area_hectares: Optional[float] = 2.5
    soil_type: Optional[str] = "Loam"
    irrigation_type: Optional[str] = "Drip"

class FieldOut(BaseModel):
    id: int
    farm_id: int
    name: str
    boundary_polygon: Optional[List[List[float]]]
    area_hectares: float
    soil_type: str
    irrigation_type: str
    created_at: datetime
    class Config:
        from_attributes = True

class CropCreate(BaseModel):
    field_id: int
    name: str
    variety: Optional[str] = None
    planting_date: datetime
    growth_stage: Optional[str] = "Vegetative"

class CropOut(BaseModel):
    id: int
    field_id: int
    name: str
    variety: Optional[str]
    planting_date: datetime
    growth_stage: str
    health_score: float
    class Config:
        from_attributes = True

class RoverCommandRequest(BaseModel):
    command: str
    params: Optional[dict] = None

class RoverOut(BaseModel):
    id: int
    rover_id: str
    name: str
    status: str
    battery_pct: float
    spray_tank_pct: float
    latitude: float
    longitude: float
    heading_deg: float
    camera_height_cm: float
    class Config:
        from_attributes = True

class MissionCreate(BaseModel):
    rover_id: int
    field_id: int
    waypoints: List[dict]

class MissionOut(BaseModel):
    id: int
    mission_code: str
    rover_id: int
    field_id: int
    status: str
    waypoints: List[dict]
    distance_traveled_m: float
    created_at: datetime
    class Config:
        from_attributes = True

class DetectionOut(BaseModel):
    id: int
    field_id: Optional[int]
    crop_name: Optional[str]
    is_healthy: bool
    label: str
    confidence: float
    severity: str
    category: str
    image_url: str
    recommended_treatment: Optional[str]
    recommended_spray_volume_l_per_ha: float
    latitude: Optional[float]
    longitude: Optional[float]
    created_at: datetime
    class Config:
        from_attributes = True

class SprayLogCreate(BaseModel):
    rover_id: int
    chemical_name: str
    volume_sprayed_liters: float
    target_area_hectares: Optional[float] = 0.5
    duration_seconds: Optional[int] = 30
    latitude: Optional[float] = None
    longitude: Optional[float] = None

class SprayLogOut(BaseModel):
    id: int
    rover_id: int
    chemical_name: str
    volume_sprayed_liters: float
    target_area_hectares: float
    duration_seconds: int
    applied_at: datetime
    class Config:
        from_attributes = True

class SupportTicketCreate(BaseModel):
    subject: str
    category: Optional[str] = "General"
    priority: Optional[str] = "Medium"
    description: str

class SupportTicketOut(BaseModel):
    id: int
    user_id: int
    subject: str
    category: str
    status: str
    priority: str
    description: str
    admin_notes: Optional[str]
    created_at: datetime
    class Config:
        from_attributes = True

class CommunityPostCreate(BaseModel):
    title: str
    content: str
    tags: Optional[str] = "General"

class CommunityPostOut(BaseModel):
    id: int
    author_id: int
    title: str
    content: str
    tags: str
    likes_count: int
    created_at: datetime
    class Config:
        from_attributes = True

class ProductOut(BaseModel):
    id: int
    name: str
    category: str
    price: float
    description: Optional[str]
    stock_quantity: int
    image_url: Optional[str]
    class Config:
        from_attributes = True
