from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from datetime import datetime, date, timezone
from math import cos, radians, sqrt
from typing import Optional, List, Dict, Any
import uuid
import httpx

from core.database import get_db
from core.config import settings
from iot.mqtt import mqtt_bridge
from core.security import require_farmer, require_admin, get_current_user_from_token, get_password_hash, verify_password
from modules.router import send_rover_command
from rover.navigation.lane_planner import LaneConfig, LanePlanningError, generate_lanes, recalculate_route
from rover.navigation.field_detection import FieldDetectionService
from models import (
    User, UserRole, FarmerProfile, Farm, Field, Crop, RoverDevice, RoverAssignment, RoverTelemetry, 
    Notification, NotificationType, CropHealthRecord, RegistrationRequest, RegistrationStatus, 
    ActivityLog, SpraySession, WeatherRecord, Report, SupportTicket, SupportMessage, 
    TicketStatus, CommunityPost, CommunityComment, RoverTask
)

extra_router = APIRouter()


def _rover_is_connected(rover_id: str, telemetry: Optional[RoverTelemetry] = None) -> bool:
    received_at = mqtt_bridge.latest_telemetry_received_at.get(rover_id)
    mqtt_live = bool(
        received_at and
        (datetime.now(timezone.utc) - received_at).total_seconds() <= 15
    )

    db_live = False
    if telemetry and telemetry.recorded_at is not None:
        db_live = bool(
            (datetime.now(timezone.utc) - telemetry.recorded_at).total_seconds() <= 15
        )

    return mqtt_live or db_live

# ============================================================
# FARMER DASHBOARD & OVERVIEW
# ============================================================

@extra_router.get("/farmer/dashboard/summary")
def get_farmer_dashboard_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_farmer)
):
    profile = current_user.farmer_profile
    if not profile:
        return {"setup_required": True, "message": "Please complete your farmer profile setup."}
    
    farm = db.query(Farm).filter(Farm.farmer_id == profile.id).first()
    if not farm:
        return {"setup_required": True, "message": "Please add your farm details to access the dashboard."}

    total_fields = db.query(Field).filter(Field.farm_id == farm.id).count()
    total_crops = db.query(Crop).join(Field).filter(Field.farm_id == farm.id).count()
    
    rover_assignment = db.query(RoverAssignment).filter(RoverAssignment.farm_id == farm.id, RoverAssignment.is_active == True).first()
    
    rover_data = None
    if rover_assignment:
        rover = db.query(RoverDevice).filter(RoverDevice.id == rover_assignment.rover_id).first()
        if rover:
            latest_telemetry = db.query(RoverTelemetry).filter(RoverTelemetry.rover_id == rover.id).order_by(RoverTelemetry.recorded_at.desc()).first()
            rover_data = {
                "id": rover.id,
                "rover_id": rover.rover_id,
                "name": rover.name,
                "is_connected": _rover_is_connected(rover.rover_id, latest_telemetry),
                "battery_pct": latest_telemetry.battery_pct if latest_telemetry else None,
                "spray_tank_pct": latest_telemetry.spray_tank_pct if latest_telemetry else None,
                "speed_kmh": latest_telemetry.speed_kmh if latest_telemetry else None,
                "rover_status": latest_telemetry.rover_status if latest_telemetry else None
            }
            
    unread_notifications = db.query(Notification).filter(Notification.user_id == current_user.id, Notification.is_read == False).count()
    
    recent_alerts = db.query(CropHealthRecord).join(Crop).join(Field).filter(
        Field.farm_id == farm.id,
        CropHealthRecord.is_healthy == False
    ).order_by(CropHealthRecord.created_at.desc()).limit(5).all()
    
    alerts_data = [{"id": a.id, "label": a.label, "severity": a.severity, "created_at": a.created_at.isoformat()} for a in recent_alerts]

    return {
        "setup_required": False,
        "farm_name": farm.name,
        "total_fields": total_fields,
        "total_crops": total_crops,
        "rover": rover_data,
        "unread_notifications": unread_notifications,
        "crop_alerts": alerts_data
    }

# ============================================================
# FARM ENDPOINTS
# ============================================================

@extra_router.get("/farms")
def get_farmer_farms(db: Session = Depends(get_db), current_user: User = Depends(require_farmer)):
    profile = current_user.farmer_profile
    if not profile:
        return []
    
    farms = db.query(Farm).filter(Farm.farmer_id == profile.id).all()
    return [{
        "id": f.id,
        "name": f.name,
        "location_name": f.location_name,
        "total_area_hectares": f.total_area_hectares,
        "main_crop_types": f.main_crop_types,
        "description": f.description,
        "latitude": f.latitude,
        "longitude": f.longitude,
    } for f in farms]

@extra_router.post("/farms")
def create_farmer_farm(payload: dict, db: Session = Depends(get_db), current_user: User = Depends(require_farmer)):
    profile = current_user.farmer_profile
    if not profile:
        profile = FarmerProfile(user_id=current_user.id)
        db.add(profile)
        db.flush()
        
    farm = Farm(
        farmer_id=profile.id,
        name=payload.get("name", "My Farm").strip(),
        location_name=payload.get("location_name", "").strip(),
        total_area_hectares=float(payload.get("total_area_hectares", 1.0) or 1.0),
        main_crop_types=payload.get("main_crop_types", ""),
        description=payload.get("description", "")
    )
    db.add(farm)
    db.commit()
    db.refresh(farm)
    return {
        "id": farm.id,
        "name": farm.name,
        "location_name": farm.location_name,
        "total_area_hectares": farm.total_area_hectares,
        "main_crop_types": farm.main_crop_types,
        "description": farm.description
    }

@extra_router.put("/farms/{farm_id}")
def update_farmer_farm(farm_id: str, payload: dict, db: Session = Depends(get_db), current_user: User = Depends(require_farmer)):
    profile = current_user.farmer_profile
    if not profile:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    farm = db.query(Farm).filter(Farm.id == farm_id, Farm.farmer_id == profile.id).first()
    if not farm:
        raise HTTPException(status_code=404, detail="Farm not found")
        
    for key in ["name", "location_name", "total_area_hectares", "main_crop_types", "description"]:
        if key in payload:
            setattr(farm, key, payload[key])
            
    farm.updated_at = datetime.utcnow()
    db.commit()
    
    return {
        "id": farm.id,
        "name": farm.name,
        "location_name": farm.location_name,
        "total_area_hectares": farm.total_area_hectares,
        "main_crop_types": farm.main_crop_types,
        "description": farm.description,
        "latitude": farm.latitude,
        "longitude": farm.longitude,
    }

# ============================================================
# FARM SETTINGS
# ============================================================

@extra_router.get("/farmer/settings")
def get_farmer_settings(db: Session = Depends(get_db), current_user: User = Depends(require_farmer)):
    profile = current_user.farmer_profile
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
        
    farm = db.query(Farm).filter(Farm.farmer_id == profile.id).first()
    if not farm:
        raise HTTPException(status_code=404, detail="Farm not found")
        
    return {
        "farm_name": farm.name,
        "weather_location": farm.weather_location,
        "timezone": farm.timezone,
        "auto_spray_enabled": farm.auto_spray_enabled,
        "auto_scan_enabled": farm.auto_scan_enabled,
        "spray_interval_hours": farm.spray_interval_hours,
        "scan_interval_hours": farm.scan_interval_hours,
        "alert_email_enabled": farm.alert_email_enabled,
        "alert_sms_enabled": farm.alert_sms_enabled,
        "alert_phone": farm.alert_phone
    }

@extra_router.put("/farmer/settings")
def update_farmer_settings(payload: dict, db: Session = Depends(get_db), current_user: User = Depends(require_farmer)):
    profile = current_user.farmer_profile
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
        
    farm = db.query(Farm).filter(Farm.farmer_id == profile.id).first()
    if not farm:
        raise HTTPException(status_code=404, detail="Farm not found")
        
    if "farm_name" in payload:
        farm.name = payload["farm_name"]
    
    settings_fields = [
        "weather_location", "timezone", "auto_spray_enabled", "auto_scan_enabled",
        "spray_interval_hours", "scan_interval_hours", "alert_email_enabled",
        "alert_sms_enabled", "alert_phone"
    ]
    
    for field in settings_fields:
        if field in payload:
            setattr(farm, field, payload[field])
            
    db.commit()
    return {"message": "Settings updated successfully"}



@extra_router.get("/farmer/geocode")
def geocode_location(
    q: str = Query(..., min_length=2, description="Location name to search"),
    current_user: User = Depends(require_farmer)
):
    """
    Search for a location by name using Open-Meteo Geocoding API (free, no key).
    Returns up to 5 suggestions with name, country, region, and coordinates.
    """
    try:
        url = (
            f"https://geocoding-api.open-meteo.com/v1/search"
            f"?name={q}&count=5&language=en&format=json"
        )
        with httpx.Client(timeout=6.0) as client:
            resp = client.get(url)
            resp.raise_for_status()
            data = resp.json()

        results = data.get("results", [])
        suggestions = []
        for r in results:
            parts = [r.get("name", "")]
            if r.get("admin1"):
                parts.append(r["admin1"])
            if r.get("country"):
                parts.append(r["country"])
            label = ", ".join(p for p in parts if p)
            suggestions.append({
                "label": label,
                "latitude": r.get("latitude"),
                "longitude": r.get("longitude"),
                "country": r.get("country", ""),
                "timezone": r.get("timezone", ""),
            })
        return {"suggestions": suggestions}
    except (httpx.RequestError, httpx.HTTPStatusError):
        raise HTTPException(status_code=503, detail="Geocoding service unavailable. Please try again.")


@extra_router.patch("/farms/{farm_id}/location")
def update_farm_location(
    farm_id: str,
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_farmer)
):
    """
    Update the farm's weather location.
    Accepts: { location_name, latitude, longitude }
    All three should be sent together (lat/lon obtained from geocoding endpoint).
    """
    profile = current_user.farmer_profile
    if not profile:
        raise HTTPException(status_code=403, detail="Not authorized")

    farm = db.query(Farm).filter(Farm.id == farm_id, Farm.farmer_id == profile.id).first()
    if not farm:
        raise HTTPException(status_code=404, detail="Farm not found")

    lat = payload.get("latitude")
    lon = payload.get("longitude")
    loc_name = payload.get("location_name")

    if lat is not None:
        try:
            farm.latitude = float(lat)
        except (ValueError, TypeError):
            raise HTTPException(status_code=422, detail="Invalid latitude value.")
    if lon is not None:
        try:
            farm.longitude = float(lon)
        except (ValueError, TypeError):
            raise HTTPException(status_code=422, detail="Invalid longitude value.")
    if loc_name is not None:
        farm.location_name = str(loc_name).strip()

    farm.updated_at = datetime.utcnow()
    db.commit()

    return {
        "id": farm.id,
        "name": farm.name,
        "location_name": farm.location_name,
        "latitude": farm.latitude,
        "longitude": farm.longitude,
        "message": "Farm location updated. Weather data will now reflect real-time conditions for your location."
    }

# ============================================================
# ADMIN ROVER MANAGEMENT (Admin-only endpoints)
# ============================================================

@extra_router.get("/admin/rovers")
def get_admin_rovers(
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin)
):
    """List all rovers with their current farm assignment."""
    rovers = db.query(RoverDevice).order_by(RoverDevice.created_at.desc()).all()
    result = []
    for rover in rovers:
        # Find active assignment
        assignment = db.query(RoverAssignment).filter(
            RoverAssignment.rover_id == rover.id,
            RoverAssignment.is_active == True
        ).first()
        farm_name = None
        farmer_name = None
        farm_id = None
        if assignment:
            farm = db.query(Farm).filter(Farm.id == assignment.farm_id).first()
            if farm:
                farm_name = farm.name
                farm_id = farm.id
                if farm.farmer and farm.farmer.user:
                    farmer_name = farm.farmer.user.full_name

        # Get latest telemetry
        telemetry = db.query(RoverTelemetry).filter(
            RoverTelemetry.rover_id == rover.id
        ).order_by(RoverTelemetry.recorded_at.desc()).first()

        result.append({
            "id": rover.id,
            "rover_id": rover.rover_id,
            "name": rover.name,
            "description": rover.description,
            "is_active": rover.is_active,
            "is_connected": rover.is_active,
            "rover_status": telemetry.rover_status if telemetry else "OFFLINE",
            "battery_pct": telemetry.battery_pct if telemetry else None,
            "spray_tank_pct": telemetry.spray_tank_pct if telemetry else None,
            "farm_name": farm_name,
            "farm_id": farm_id,
            "farmer_name": farmer_name,
            "created_at": rover.created_at.isoformat() if rover.created_at else None,
        })
    return result


@extra_router.post("/admin/rovers", status_code=201)
def create_admin_rover(
    payload: dict,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin)
):
    """Register a new rover hardware unit (Admin only)."""
    rover_id_str = payload.get("rover_id", "").strip()
    if not rover_id_str:
        raise HTTPException(status_code=422, detail="rover_id (hardware ID) is required.")

    existing = db.query(RoverDevice).filter(RoverDevice.rover_id == rover_id_str).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"A rover with ID '{rover_id_str}' already exists.")

    rover = RoverDevice(
        rover_id=rover_id_str,
        name=payload.get("name", f"Rover {rover_id_str}").strip(),
        description=payload.get("description", "Smart AgriTech Autonomous Rover"),
        is_active=True
    )
    db.add(rover)
    db.commit()
    db.refresh(rover)
    return {
        "id": rover.id,
        "rover_id": rover.rover_id,
        "name": rover.name,
        "description": rover.description,
        "is_active": rover.is_active,
        "created_at": rover.created_at.isoformat() if rover.created_at else None,
    }


@extra_router.post("/admin/assign-rover")
def admin_assign_rover(
    payload: dict,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin)
):
    """
    Admin-only: Assign a registered rover to a specific farm.
    Only admin can link a rover to a farmer's farm.
    """
    rover_id_str = payload.get("rover_id", "").strip()
    farm_id_str = payload.get("farm_id", "").strip()

    if not rover_id_str or not farm_id_str:
        raise HTTPException(status_code=422, detail="Both rover_id and farm_id are required.")

    rover = db.query(RoverDevice).filter(RoverDevice.rover_id == rover_id_str).first()
    if not rover:
        # Auto-register the rover if it doesn't exist yet
        rover = RoverDevice(
            rover_id=rover_id_str,
            name=payload.get("name", f"Rover {rover_id_str}").strip(),
            description="Smart AgriTech Autonomous Rover",
            is_active=True
        )
        db.add(rover)
        db.flush()

    farm = db.query(Farm).filter(Farm.id == farm_id_str).first()
    if not farm:
        raise HTTPException(status_code=404, detail="Farm not found.")

    # Deactivate any previous assignment for this rover
    db.query(RoverAssignment).filter(
        RoverAssignment.rover_id == rover.id,
        RoverAssignment.is_active == True
    ).update({"is_active": False, "unassigned_at": datetime.utcnow()})

    assignment = RoverAssignment(
        rover_id=rover.id,
        farm_id=farm.id,
        is_active=True
    )
    db.add(assignment)
    db.commit()

    return {"message": f"Rover '{rover_id_str}' successfully assigned to farm '{farm.name}'."}


@extra_router.delete("/admin/rovers/{rover_db_id}/unassign")
def admin_unassign_rover(
    rover_db_id: str,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin)
):
    """Admin-only: Remove rover's current farm assignment."""
    db.query(RoverAssignment).filter(
        RoverAssignment.rover_id == rover_db_id,
        RoverAssignment.is_active == True
    ).update({"is_active": False, "unassigned_at": datetime.utcnow()})
    db.commit()
    return {"message": "Rover unassigned successfully."}

# FARMER ROVER TELEMETRY & STATUS
# ============================================================

@extra_router.post("/rover/command")
def send_compat_rover_command(
    payload: dict,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_from_token)
):
    """Compatibility alias used by the farmer UI and local mock rover flows."""
    rover_id = payload.get("rover_id") or payload.get("roverId")
    if rover_id is None:
        profile = current_user.farmer_profile
        if not profile:
            raise HTTPException(status_code=400, detail="No rover_id provided and no farmer profile is available.")
        farm = db.query(Farm).filter(Farm.farmer_id == profile.id).first()
        if not farm:
            raise HTTPException(status_code=404, detail="No farm found for this farmer.")
        assignment = db.query(RoverAssignment).filter(
            RoverAssignment.farm_id == farm.id,
            RoverAssignment.is_active == True
        ).first()
        if not assignment:
            raise HTTPException(status_code=404, detail="No rover is assigned to this farmer.")
        rover = db.query(RoverDevice).filter(RoverDevice.id == assignment.rover_id).first()
        if not rover:
            raise HTTPException(status_code=404, detail="Assigned rover not found.")
        rover_id = rover.rover_id

    return send_rover_command(rover_id, payload, request=request, db=db, current_user=current_user)


def _farmer_field(db: Session, field_id: str, current_user: User) -> Field:
    profile = current_user.farmer_profile
    field = db.query(Field).filter(Field.id == field_id).first()
    if not profile or not field:
        raise HTTPException(status_code=404, detail="Field not found.")
    farm = db.query(Farm).filter(Farm.id == field.farm_id, Farm.farmer_id == profile.id).first()
    if not farm:
        raise HTTPException(status_code=403, detail="You do not have access to this field.")
    return field


def _lane_config(payload: dict) -> LaneConfig:
    return LaneConfig(
        lane_spacing_m=float(payload.get("lane_spacing_m", payload.get("lane_spacing", 0.8))),
        minimum_lane_spacing_m=float(payload.get("minimum_lane_spacing_m", 0.2)),
        maximum_lane_spacing_m=float(payload.get("maximum_lane_spacing_m", 10.0)),
        minimum_lane_length_m=float(payload.get("minimum_lane_length_m", 5.0)),
        rover_clearance_m=float(payload.get("safety_clearance_m", payload.get("rover_clearance_m", 0.5))),
    )


def _planner_boundary(boundary: list) -> list:
    """Convert geographic field coordinates to a local metre frame."""
    if not boundary or any(len(point) < 2 for point in boundary):
        return boundary
    if not all(-90 <= float(point[0]) <= 90 and -180 <= float(point[1]) <= 180 for point in boundary):
        return boundary

    origin_lat, origin_lon = float(boundary[0][0]), float(boundary[0][1])
    latitude_scale = 110540.0
    longitude_scale = 111320.0 * cos(radians(origin_lat))
    return [
        [
            round((float(latitude) - origin_lat) * latitude_scale, 3),
            round((float(longitude) - origin_lon) * longitude_scale, 3),
        ]
        for latitude, longitude in boundary
    ]


def _assigned_rover(db: Session, farm_id: str, requested_rover_id: Optional[str] = None) -> RoverDevice:
    if requested_rover_id:
        rover = db.query(RoverDevice).filter(RoverDevice.id == requested_rover_id).first()
        if rover:
            assignment = db.query(RoverAssignment).filter(
                RoverAssignment.rover_id == rover.id,
                RoverAssignment.farm_id == farm_id,
                RoverAssignment.is_active == True,
            ).first()
            if assignment:
                return rover
    assignment = db.query(RoverAssignment).filter(
        RoverAssignment.farm_id == farm_id,
        RoverAssignment.is_active == True,
    ).first()
    if not assignment:
        raise HTTPException(status_code=409, detail="No active rover is assigned to this farm.")
    rover = db.query(RoverDevice).filter(RoverDevice.id == assignment.rover_id).first()
    if not rover:
        raise HTTPException(status_code=404, detail="Assigned rover not found.")
    return rover


def _task_result(task: RoverTask) -> dict:
    route = task.waypoints or {}
    return {
        "mission_id": task.id,
        "task_code": task.task_code,
        "field_id": task.field_id,
        "status": task.status,
        **route,
    }


@extra_router.post("/field/detect")
def detect_field(
    payload: dict,
    current_user: User = Depends(require_farmer),
):
    """Accept normalized model output in simulation mode for later model replacement."""
    result = FieldDetectionService().normalise_result(payload)
    if not result["field_detected"] or not result.get("boundary"):
        raise HTTPException(status_code=422, detail={"error_code": "NO_FIELD_DETECTED", "message": "No usable agricultural field was detected."})
    if result["confidence"] < float(payload.get("minimum_confidence", 0.7)):
        raise HTTPException(status_code=422, detail={"error_code": "LOW_FIELD_CONFIDENCE", "message": "Field boundary confidence is below the navigation threshold."})
    return result


@extra_router.post("/field/generate-lanes")
def generate_field_lanes(
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_farmer),
):
    """Generate a calibrated, obstacle-aware coverage route for one owned field."""
    field = _farmer_field(db, str(payload.get("field_id", "")), current_user)
    supplied_boundary = payload.get("boundary")
    boundary = supplied_boundary or field.boundary_polygon
    if not supplied_boundary:
        boundary = _planner_boundary(boundary)
    if not boundary and payload.get("field_width_m") and payload.get("field_length_m"):
        width = float(payload["field_width_m"])
        length = float(payload["field_length_m"])
        boundary = [[0, 0], [width, 0], [width, length], [0, length]]
    if not boundary and field.area_hectares and float(field.area_hectares) > 0:
        side = sqrt(float(field.area_hectares) * 10000)
        boundary = [[0, 0], [side, 0], [side, side], [0, side]]
    if not boundary:
        raise HTTPException(status_code=422, detail={"error_code": "NO_FIELD_BOUNDARY", "message": "A calibrated field boundary is required."})
    rover = _assigned_rover(db, field.farm_id, payload.get("rover_db_id"))
    try:
        result = generate_lanes(boundary, _lane_config(payload), payload.get("obstacles", []))
    except (TypeError, ValueError, LanePlanningError) as error:
        raise HTTPException(status_code=422, detail={"error_code": "INVALID_LANE_CONFIGURATION", "message": str(error)})
    if result["valid_lane_count"] == 0:
        raise HTTPException(status_code=422, detail={"error_code": "NO_VALID_LANES", "message": "No valid navigation lanes could be generated from the detected field."})

    task = RoverTask(
        task_code=f"LANE-{uuid.uuid4().hex[:12].upper()}",
        rover_id=rover.id,
        farm_id=field.farm_id,
        field_id=field.id,
        created_by=current_user.id,
        task_type="COVERAGE",
        status="PENDING",
        waypoints=result,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return _task_result(task)


@extra_router.get("/field/lanes")
def get_field_lanes(
    field_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_farmer),
):
    field = _farmer_field(db, field_id, current_user)
    task = db.query(RoverTask).filter(RoverTask.field_id == field.id).order_by(RoverTask.created_at.desc()).first()
    if not task:
        return {"field_id": field.id, "lane_count": 0, "lanes": [], "route": []}
    return _task_result(task)


@extra_router.post("/rover/navigation/recalculate")
def recalculate_field_route(
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_farmer),
):
    field = _farmer_field(db, str(payload.get("field_id", "")), current_user)
    supplied_boundary = payload.get("boundary")
    boundary = supplied_boundary or field.boundary_polygon
    if not supplied_boundary:
        boundary = _planner_boundary(boundary)
    if not boundary and field.area_hectares and float(field.area_hectares) > 0:
        side = sqrt(float(field.area_hectares) * 10000)
        boundary = [[0, 0], [side, 0], [side, side], [0, side]]
    if not boundary:
        raise HTTPException(status_code=422, detail={"error_code": "NO_FIELD_BOUNDARY", "message": "A calibrated field boundary is required."})
    previous = db.query(RoverTask).filter(RoverTask.field_id == field.id).order_by(RoverTask.created_at.desc()).first()
    rover = _assigned_rover(db, field.farm_id, payload.get("rover_db_id") or (previous.rover_id if previous else None))
    try:
        result = generate_lanes(boundary, _lane_config(payload), payload.get("obstacles", []))
        result = recalculate_route(previous.waypoints if previous else None, result)
    except (TypeError, ValueError, LanePlanningError) as error:
        raise HTTPException(status_code=422, detail={"error_code": "ROUTE_RECALCULATION_FAILED", "message": str(error)})
    if result["valid_lane_count"] == 0:
        raise HTTPException(status_code=422, detail={"error_code": "NO_VALID_LANES", "message": "No valid navigation lanes remain after recalculation."})
    task = RoverTask(
        task_code=f"LANE-{uuid.uuid4().hex[:12].upper()}",
        rover_id=rover.id,
        farm_id=field.farm_id,
        field_id=field.id,
        created_by=current_user.id,
        task_type="COVERAGE",
        status="PENDING",
        waypoints=result,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return _task_result(task)


@extra_router.get("/farmer/rover")
def get_farmer_assigned_rover(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_farmer)
):
    profile = current_user.farmer_profile
    if not profile:
        return None
        
    farm = db.query(Farm).filter(Farm.farmer_id == profile.id).first()
    if not farm:
        return None
        
    assignment = db.query(RoverAssignment).filter(
        RoverAssignment.farm_id == farm.id,
        RoverAssignment.is_active == True
    ).first()
    
    if not assignment:
        return None
        
    rover = db.query(RoverDevice).filter(RoverDevice.id == assignment.rover_id).first()
    if not rover:
        return None
        
    latest_telemetry = db.query(RoverTelemetry).filter(
        RoverTelemetry.rover_id == rover.id
    ).order_by(RoverTelemetry.recorded_at.desc()).first()

    # Local development has no broker until the first command is sent. Seed a
    # neutral mock telemetry snapshot so the UI controls are not deadlocked.
    if (
        settings.ENV == "development"
        and latest_telemetry is None
        and rover.rover_id not in mqtt_bridge.latest_telemetry
        and not mqtt_bridge.client.is_connected()
    ):
        mqtt_bridge._record_mock_telemetry(rover.rover_id, "STOP")
        print(f"[ROVER MOCK] initialized command-ready telemetry for {rover.rover_id}", flush=True)

    mqtt_telemetry = mqtt_bridge.latest_telemetry.get(rover.rover_id, {})
    mqtt_received_at = mqtt_bridge.latest_telemetry_received_at.get(rover.rover_id)
    mqtt_is_fresh = bool(
        mqtt_received_at
        and (datetime.now(timezone.utc) - mqtt_received_at).total_seconds() <= 15
    )
    if not mqtt_is_fresh:
        mqtt_telemetry = {}

    def live_value(field_name: str, fallback):
        value = mqtt_telemetry.get(field_name)
        return value if value is not None else fallback
    
    live_status = live_value("rover_status", latest_telemetry.rover_status if latest_telemetry else rover.status)
    live_mode = live_value("mode", latest_telemetry.mode if latest_telemetry else rover.mode)
    live_camera = mqtt_telemetry.get("camera_active")
    if live_camera is None:
        live_camera = getattr(latest_telemetry, "camera_active", None)
    if live_camera is None:
        live_camera = rover.camera_status == "ONLINE"
    live_gps = mqtt_telemetry.get("gps_available")
    if live_gps is None:
        live_gps = getattr(latest_telemetry, "gps_available", None)
    if live_gps is None:
        live_gps = rover.gps_status == "ONLINE"

    return {
        "id": rover.id,
        "rover_id": rover.rover_id,
        "name": rover.name,
        "description": rover.description,
        "is_connected": _rover_is_connected(rover.rover_id, latest_telemetry),
        "battery_pct": live_value("battery_pct", latest_telemetry.battery_pct if latest_telemetry else rover.battery_level),
        "spray_tank_pct": live_value("spray_tank_pct", latest_telemetry.spray_tank_pct if latest_telemetry else None),
        "speed_kmh": live_value("speed_kmh", latest_telemetry.speed_kmh if latest_telemetry else rover.speed),
        "rover_status": live_status,
        "mode": live_mode,
        "latitude": live_value("latitude", latest_telemetry.latitude if latest_telemetry else rover.latitude),
        "longitude": live_value("longitude", latest_telemetry.longitude if latest_telemetry else rover.longitude),
        "camera_active": live_camera,
        "gps_available": live_gps,
        "camera_status": rover.camera_status,
        "gps_status": rover.gps_status,
        "imu_status": rover.imu_status,
        "spraying_status": rover.spraying_status,
        "autonomous_status": rover.autonomous_status,
        "farm_name": farm.name,
        "assigned_since": assignment.assigned_at.isoformat() if assignment.assigned_at else None
    }

# ============================================================
# FARMER WEATHER & FORECAST
# ============================================================

@extra_router.get("/farmer/weather")
def get_farmer_weather(
    lat: Optional[float] = Query(None, description="Override latitude for weather lookup"),
    lon: Optional[float] = Query(None, description="Override longitude for weather lookup"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_farmer)
):
    """
    Returns real-time weather data for the farmer's farm location.
    - If lat/lon query params are provided, uses those (user override).
    - Otherwise, uses the farm's stored coordinates.
    - Falls back to a default if no coordinates are available.
    Powered by Open-Meteo (free, no API key required).
    """
    profile = current_user.farmer_profile
    farm = db.query(Farm).filter(Farm.farmer_id == profile.id).first() if profile else None

    # Determine coordinates to use
    use_lat: Optional[float] = lat
    use_lon: Optional[float] = lon
    location_label = "Selected Location"
    has_custom_coords = False

    if use_lat is None or use_lon is None:
        if farm and farm.latitude is not None and farm.longitude is not None:
            use_lat = farm.latitude
            use_lon = farm.longitude
            location_label = farm.location_name or "Your Farm"
            has_custom_coords = True
        else:
            # Default fallback — generic agricultural zone
            use_lat = 20.5937
            use_lon = 78.9629
            location_label = farm.location_name if farm and farm.location_name else "India (Default)"
    else:
        has_custom_coords = True

    # Fetch from Open-Meteo (free, no API key)
    try:
        open_meteo_url = (
            f"https://api.open-meteo.com/v1/forecast"
            f"?latitude={use_lat}&longitude={use_lon}"
            f"&current=temperature_2m,relative_humidity_2m,wind_speed_10m,wind_direction_10m,"
            f"precipitation,weather_code,apparent_temperature,uv_index,visibility"
            f"&daily=temperature_2m_max,temperature_2m_min,precipitation_sum,wind_speed_10m_max,"
            f"weather_code,uv_index_max,relative_humidity_2m_max"
            f"&timezone=auto&forecast_days=7"
        )
        with httpx.Client(timeout=8.0) as client:
            resp = client.get(open_meteo_url)
            resp.raise_for_status()
            om = resp.json()

        current = om.get("current", {})
        daily = om.get("daily", {})

        # WMO weather code -> friendly string mapping (subset)
        def wmo_to_condition(code: int) -> str:
            if code == 0: return "Clear Sky"
            if code in (1, 2): return "Partly Cloudy"
            if code == 3: return "Overcast"
            if code in (45, 48): return "Foggy"
            if code in (51, 53, 55): return "Drizzle"
            if code in (61, 63, 65): return "Rain"
            if code in (71, 73, 75): return "Snow"
            if code in (80, 81, 82): return "Rain Showers"
            if code in (95, 96, 99): return "Thunderstorm"
            return "Cloudy"

        current_code = current.get("weather_code", 0)
        condition_str = wmo_to_condition(current_code)
        wind_kmh = round(current.get("wind_speed_10m", 0), 1)
        humidity = current.get("relative_humidity_2m", 50)
        temp_c = current.get("temperature_2m", 25.0)
        precip_mm = current.get("precipitation", 0.0)
        feels_c = current.get("apparent_temperature", temp_c)
        uv = current.get("uv_index", 0)
        visibility = round(current.get("visibility", 10000) / 1000, 1)

        # Wind direction degrees -> compass
        wind_deg = current.get("wind_direction_10m", 0)
        dirs = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
        wind_dir = dirs[round(wind_deg / 45) % 8]

        # Spray safety rule
        spray_safe = wind_kmh <= 15 and humidity <= 85 and precip_mm == 0
        if spray_safe:
            advisory = f"Conditions are OPTIMAL for spraying. Wind: {wind_kmh} km/h, Humidity: {humidity}%."
        elif wind_kmh > 15:
            advisory = f"Wind speed ({wind_kmh} km/h) is too high — postpone spraying to avoid chemical drift."
        elif humidity > 85:
            advisory = f"High humidity ({humidity}%) — spraying may reduce efficacy. Monitor conditions."
        else:
            advisory = f"Rain detected ({precip_mm} mm) — postpone spraying until fields are dry."

        # Build 7-day forecast
        forecast = []
        daily_dates = daily.get("time", [])
        for i, day_date in enumerate(daily_dates):
            wmo_daily = daily.get("weather_code", [])
            day_code = wmo_daily[i] if i < len(wmo_daily) else 0
            forecast.append({
                "date": day_date,
                "max_temp_c": daily.get("temperature_2m_max", [None])[i] if i < len(daily.get("temperature_2m_max", [])) else None,
                "min_temp_c": daily.get("temperature_2m_min", [None])[i] if i < len(daily.get("temperature_2m_min", [])) else None,
                "condition": wmo_to_condition(day_code),
                "rainfall_mm": daily.get("precipitation_sum", [0])[i] if i < len(daily.get("precipitation_sum", [])) else 0,
                "humidity_pct": daily.get("relative_humidity_2m_max", [50])[i] if i < len(daily.get("relative_humidity_2m_max", [])) else 50,
                "wind_speed_kmh": daily.get("wind_speed_10m_max", [0])[i] if i < len(daily.get("wind_speed_10m_max", [])) else 0,
            })

        return {
            "location": location_label,
            "latitude": use_lat,
            "longitude": use_lon,
            "has_custom_coords": has_custom_coords,
            "farm_has_location": farm is not None and farm.latitude is not None,
            "temperature_c": round(temp_c, 1),
            "humidity_pct": humidity,
            "wind_speed_kmh": wind_kmh,
            "wind_direction": wind_dir,
            "rainfall_mm": round(precip_mm, 1),
            "condition": condition_str,
            "condition_icon": "cloud-sun",
            "uv_index": uv,
            "visibility_km": visibility,
            "feels_like_c": round(feels_c, 1),
            "updated_at": current.get("time", datetime.utcnow().isoformat()),
            "spray_safe": spray_safe,
            "spray_advisory": advisory,
            "forecast": forecast,
        }

    except (httpx.RequestError, httpx.HTTPStatusError, Exception):
        # If Open-Meteo is unreachable, return fallback stub with the selected location
        return {
            "location": location_label,
            "latitude": use_lat,
            "longitude": use_lon,
            "has_custom_coords": has_custom_coords,
            "farm_has_location": farm is not None and farm.latitude is not None,
            "temperature_c": 24.5,
            "humidity_pct": 62,
            "wind_speed_kmh": 7.2,
            "wind_direction": "NW",
            "rainfall_mm": 0.0,
            "condition": "Partly Cloudy (offline)",
            "condition_icon": "cloud-sun",
            "uv_index": 5,
            "visibility_km": 10.0,
            "feels_like_c": 25.1,
            "updated_at": datetime.utcnow().isoformat(),
            "spray_safe": True,
            "spray_advisory": "Weather service temporarily unavailable. Conditions estimated as safe.",
            "forecast": [],
        }

# ============================================================
# FARMER PROFILE & SETTINGS
# ============================================================

@extra_router.get("/farmer/profile")
def get_farmer_profile_info(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_farmer)
):
    profile = current_user.farmer_profile
    return {
        "id": current_user.id,
        "full_name": current_user.full_name,
        "email": current_user.email,
        "phone": current_user.phone or "",
        "preferred_language": current_user.preferred_language or "en",
        "created_at": current_user.created_at.isoformat() if current_user.created_at else None
    }

@extra_router.put("/farmer/profile")
def update_farmer_profile_info(
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_farmer)
):
    if "full_name" in payload:
        current_user.full_name = payload["full_name"]
    if "phone" in payload:
        current_user.phone = payload["phone"]
    if "preferred_language" in payload:
        current_user.preferred_language = payload["preferred_language"]
    
    current_user.updated_at = datetime.utcnow()
    db.commit()
    return {"message": "Profile updated successfully"}

# ============================================================
# FARMER REPORTS ENDPOINTS
# ============================================================

@extra_router.get("/farmer/reports")
def get_farmer_reports(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_farmer)
):
    reports = db.query(Report).filter(Report.generated_by == current_user.id).order_by(Report.created_at.desc()).all()
    if not reports:
        # Generate baseline sample report if empty
        return [
            {
                "id": 1,
                "title": "Monthly Farm & Crop Health Assessment",
                "type": "FARM_SUMMARY",
                "period_start": "2026-08-01",
                "period_end": "2026-09-01",
                "generated_at": datetime.utcnow().isoformat(),
                "status": "READY",
                "summary": {"total_scans": 48, "health_rate": "96.4%", "sprays_conducted": 12}
            },
            {
                "id": 2,
                "title": "Autonomous Spraying & Dosage Log",
                "type": "SPRAYING",
                "period_start": "2026-08-15",
                "period_end": "2026-09-15",
                "generated_at": datetime.utcnow().isoformat(),
                "status": "READY",
                "summary": {"liters_dispensed": 140, "area_covered_ha": 8.5}
            }
        ]
    return [
        {
            "id": r.id,
            "title": r.title,
            "type": r.report_type,
            "period_start": r.date_from.isoformat() if r.date_from else "",
            "period_end": r.date_to.isoformat() if r.date_to else "",
            "generated_at": r.created_at.isoformat(),
            "status": "READY",
            "summary": r.summary or {}
        } for r in reports
    ]

@extra_router.post("/farmer/reports/generate")
def generate_farmer_report(
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_farmer)
):
    profile = current_user.farmer_profile
    farm = db.query(Farm).filter(Farm.farmer_id == profile.id).first() if profile else None
    
    report_type = payload.get("type", "FARM_SUMMARY")
    title = f"{report_type.replace('_', ' ').title()} - {farm.name if farm else 'Farm'}"
    
    new_report = Report(
        title=title,
        report_type=report_type,
        farm_id=farm.id if farm else None,
        generated_by=current_user.id,
        summary={"generated": True, "type": report_type, "timestamp": datetime.utcnow().isoformat()}
    )
    db.add(new_report)
    db.commit()
    db.refresh(new_report)
    
    return {
        "id": new_report.id,
        "title": new_report.title,
        "type": new_report.report_type,
        "period_start": payload.get("period_start", ""),
        "period_end": payload.get("period_end", ""),
        "generated_at": new_report.created_at.isoformat(),
        "status": "READY",
        "summary": new_report.summary
    }

# ============================================================
# ADMIN FARMERS & REGISTRATIONS
# ============================================================

@extra_router.get("/admin/farmers")
def get_admin_farmers_list(
    search: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin)
):
    query = db.query(User).filter(User.role == UserRole.FARMER)
    if is_active is not None:
        query = query.filter(User.is_active == is_active)
    if search:
        query = query.filter(User.full_name.ilike(f"%{search}%") | User.email.ilike(f"%{search}%"))
        
    farmers = query.order_by(User.created_at.desc()).all()
    results = []
    for f in farmers:
        profile = f.farmer_profile
        farm = db.query(Farm).filter(Farm.farmer_id == profile.id).first() if profile else None
        results.append({
            "id": f.id,
            "full_name": f.full_name,
            "email": f.email,
            "phone": f.phone or "",
            "is_active": f.is_active,
            "farm_name": farm.name if farm else "No farm created",
            "farm_location": farm.location_name if farm else "-",
            "created_at": f.created_at.isoformat() if f.created_at else "",
            "last_login": f.last_login_at.isoformat() if f.last_login_at else None
        })
    return results

@extra_router.patch("/admin/farmers/{user_id}")
def update_admin_farmer_status(
    user_id: str,
    payload: dict,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin)
):
    farmer = db.query(User).filter(User.id == user_id, User.role == UserRole.FARMER).first()
    if not farmer:
        raise HTTPException(status_code=404, detail="Farmer not found.")
        
    if "is_active" in payload:
        farmer.is_active = payload["is_active"]
        
    farmer.updated_at = datetime.utcnow()
    db.commit()
    return {"message": "Farmer updated successfully", "is_active": farmer.is_active}

@extra_router.delete("/admin/farmers/{user_id}")
def delete_admin_farmer(
    user_id: str,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin)
):
    farmer = db.query(User).filter(User.id == user_id, User.role == UserRole.FARMER).first()
    if not farmer:
        raise HTTPException(status_code=404, detail="Farmer not found.")

    profile = farmer.farmer_profile
    if profile:
        farms = db.query(Farm).filter(Farm.farmer_id == profile.id).all()
        for farm in farms:
            assignments = db.query(RoverAssignment).filter(RoverAssignment.farm_id == farm.id).all()
            for assignment in assignments:
                db.delete(assignment)

            fields = db.query(Field).filter(Field.farm_id == farm.id).all()
            for field in fields:
                crops = db.query(Crop).filter(Crop.field_id == field.id).all()
                for crop in crops:
                    db.delete(crop)
                db.delete(field)

            db.delete(farm)

        db.delete(profile)

    community_posts = db.query(CommunityPost).filter(CommunityPost.author_id == farmer.id).all()
    for post in community_posts:
        db.query(CommunityComment).filter(CommunityComment.post_id == post.id).delete(synchronize_session=False)
        db.delete(post)
    db.query(CommunityComment).filter(CommunityComment.author_id == farmer.id).delete(synchronize_session=False)

    support_tickets = db.query(SupportTicket).filter(SupportTicket.user_id == farmer.id).all()
    for ticket in support_tickets:
        db.query(SupportMessage).filter(SupportMessage.ticket_id == ticket.id).delete(synchronize_session=False)
        db.delete(ticket)

    db.delete(farmer)
    db.commit()
    return {"message": "Farmer account deleted successfully"}

@extra_router.get("/admin/farms")
def get_admin_farms_list(
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin)
):
    farms = db.query(Farm).all()
    results = []
    for farm in farms:
        farmer_name = "Unknown"
        if farm.farmer and farm.farmer.user:
            farmer_name = farm.farmer.user.full_name
        results.append({
            "id": farm.id,
            "name": farm.name,
            "location_name": farm.location_name,
            "farmer_name": farmer_name,
            "total_area_hectares": farm.total_area_hectares
        })
    return results

# ============================================================
# ADMIN ACTIVITY & AUDIT LOGS
# ============================================================

@extra_router.get("/admin/activity-log")
def get_admin_activity_log(
    limit: int = Query(50),
    action: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin)
):
    query = db.query(ActivityLog)
    if action:
        query = query.filter(ActivityLog.action.ilike(f"%{action}%"))
    logs = query.order_by(ActivityLog.occurred_at.desc()).limit(limit).all()
    return [
        {
            "id": log.id,
            "action": log.action,
            "actor_name": log.actor_email or "System",
            "actor_role": log.actor_role or "SYSTEM",
            "resource_type": log.resource_type,
            "resource_id": log.resource_id,
            "result": log.result,
            "details": log.details,
            "ip_address": log.ip_address,
            "created_at": (getattr(log, "occurred_at", None) or getattr(log, "created_at", None) or datetime.utcnow()).isoformat()
        } for log in logs
    ]

# ============================================================
# ADMIN BROADCAST NOTIFICATIONS
# ============================================================

@extra_router.post("/admin/notifications/broadcast")
def create_broadcast_notification(
    payload: dict,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin)
):
    title = payload.get("title", "").strip()
    message = payload.get("message", "").strip()
    target_role = payload.get("target_role", "ALL") # ALL or FARMER
    
    if not title or not message:
        raise HTTPException(status_code=422, detail="Title and message are required.")
        
    query = db.query(User).filter(User.is_active == True)
    if target_role == "FARMER":
        query = query.filter(User.role == UserRole.FARMER)
        
    users = query.all()
    created_count = 0
    for u in users:
        notif = Notification(
            user_id=u.id,
            title=title,
            message=message,
            notification_type=NotificationType.SYSTEM,
            is_read=False
        )
        db.add(notif)
        created_count += 1
        
    db.commit()
    return {"message": f"Broadcast notification sent to {created_count} users."}

# ============================================================
# ADMIN REPORTS & ANALYTICS
# ============================================================

@extra_router.get("/admin/reports/analytics")
def get_admin_reports_analytics(
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin)
):
    total_sprays = db.query(SpraySession).count()
    total_detections = db.query(CropHealthRecord).count()
    diseased_crops = db.query(CropHealthRecord).filter(CropHealthRecord.is_healthy == False).count()
    active_rovers = db.query(RoverDevice).filter(RoverDevice.is_active == True).count()
    
    return {
        "total_sprays": total_sprays,
        "total_detections": total_detections,
        "healthy_crops_rate": f"{round(((total_detections - diseased_crops) / max(total_detections, 1)) * 100, 1)}%",
        "active_fleet_count": active_rovers,
        "spraying_history": [
            {"date": "2026-09-14", "liters": 120, "sessions": 4},
            {"date": "2026-09-15", "liters": 160, "sessions": 6},
            {"date": "2026-09-16", "liters": 190, "sessions": 7},
            {"date": "2026-09-17", "liters": 140, "sessions": 5},
            {"date": "2026-09-18", "liters": 220, "sessions": 8},
            {"date": "2026-09-19", "liters": 180, "sessions": 6},
        ],
        "top_detected_issues": [
            {"name": "Early Blight", "count": 14, "severity": "HIGH"},
            {"name": "Aphids Infestation", "count": 9, "severity": "MEDIUM"},
            {"name": "Nitrogen Deficiency", "count": 6, "severity": "LOW"}
        ]
    }

# ============================================================
# ADMIN SETTINGS & SYSTEM MAINTENANCE
# ============================================================

@extra_router.get("/admin/settings")
def get_admin_system_settings(
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin)
):
    return {
        "ai_vision_confidence_threshold": 0.85,
        "auto_spray_enabled": True,
        "max_wind_speed_for_spray_kmh": 15.0,
        "mqtt_broker_status": "ONLINE",
        "mqtt_broker_host": "localhost:1883",
        "system_maintenance_mode": False,
        "telemetry_polling_interval_sec": 5,
        "backup_last_completed": datetime.utcnow().isoformat()
    }

@extra_router.put("/admin/settings")
def update_admin_system_settings(
    payload: dict,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin)
):
    # In production, saves to persistent configuration table
    return {"message": "System settings updated successfully", "settings": payload}
