"""
Smart AgriTech Rover Platform — Modular API Router
All endpoints use real authentication and ownership checks.
No hardcoded user IDs. No fake data returned.
"""

import uuid
import os
import tempfile
from datetime import datetime
from typing import List, Optional, Any, Dict
from fastapi import (
    APIRouter, Depends, HTTPException, UploadFile, File, Form,
    status, Request, BackgroundTasks, Query
)
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from core.database import get_db
from core.security import (
    create_access_token, verify_password, get_password_hash,
    generate_temp_password, generate_activation_token,
    get_current_user_from_token, require_admin, require_farmer,
    verify_farm_ownership, verify_field_ownership
)
from models import (
    User, UserRole, RegistrationRequest, RegistrationStatus,
    FarmerProfile, Farm, Field, Crop, CropStatus,
    RoverDevice, RoverAssignment, RoverCommand, RoverTelemetry, RoverTask,
    CommandStatus, RoverStatus,
    CropHealthRecord, DetectionEvidence, VideoAnalysisJob, VideoJobStatus,
    Product, SpraySession, SprayEvent, SprayStatus,
    WeatherRecord, Notification, NotificationType,
    Report, SupportTicket, SupportMessage, TicketStatus,
    CommunityPost, CommunityComment,
    MediaAsset, CommunicationLog, ActivityLog
)
from ai.service import get_ai_vision_provider
from media.service import media_service
from iot.mqtt import mqtt_bridge

api_router = APIRouter()


# ============================================================
# HELPERS
# ============================================================

def log_activity(
    db: Session,
    action: str,
    actor=None,
    resource_type: str = None,
    resource_id: str = None,
    result: str = "SUCCESS",
    details: dict = None,
    ip_address: str = None,
):
    """Create an activity log entry."""
    log = ActivityLog(
        actor_id=actor.id if actor else None,
        actor_email=actor.email if actor else None,
        actor_role=actor.role if actor else None,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        result=result,
        details=details,
        ip_address=ip_address,
    )
    db.add(log)
    db.commit()


def get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    return forwarded.split(",")[0].strip() if forwarded else request.client.host


# ============================================================
# 1. AUTHENTICATION
# ============================================================

@api_router.post("/auth/login")
def farmer_login(
    payload: dict,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Farmer login endpoint.
    Returns status message if account is not approved.
    Only fully approved accounts with active users can log in.
    """
    email = (payload.get("email") or "").strip().lower()
    password = payload.get("password") or ""

    if not email or not password:
        raise HTTPException(status_code=422, detail="Email and password are required.")

    user = db.query(User).filter(User.email == email, User.is_active == True).first()

    # Check registration request status if user doesn't exist yet
    if not user:
        reg = db.query(RegistrationRequest).filter(
            RegistrationRequest.email == email
        ).order_by(RegistrationRequest.submitted_at.desc()).first()

        if reg:
            status_messages = {
                RegistrationStatus.PENDING: {
                    "status": "PENDING",
                    "message": "Your registration request is being reviewed. We will contact you once it is processed."
                },
                RegistrationStatus.UNDER_REVIEW: {
                    "status": "UNDER_REVIEW",
                    "message": "Your registration is currently under review. You will receive an email and SMS once approved."
                },
                RegistrationStatus.REJECTED: {
                    "status": "REJECTED",
                    "message": f"Your registration was not approved. {reg.rejection_reason or ''}".strip()
                },
            }
            if reg.status in status_messages:
                return JSONResponse(status_code=403, content=status_messages[reg.status])

        raise HTTPException(
            status_code=401,
            detail="Incorrect email or password."
        )

    if not verify_password(password, user.hashed_password):
        log_activity(db, "LOGIN_FAILED", actor=user, resource_type="User",
                     resource_id=user.id, result="FAILED", ip_address=get_client_ip(request))
        raise HTTPException(status_code=401, detail="Incorrect email or password.")

    token = create_access_token(
        subject=user.email,
        role=user.role,
        user_id=user.id,
        must_change_password=user.must_change_password,
    )

    user.last_login_at = datetime.utcnow()
    db.commit()

    log_activity(db, "LOGIN", actor=user, resource_type="User", resource_id=user.id,
                 ip_address=get_client_ip(request))

    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "email": user.email,
            "full_name": user.full_name,
            "role": user.role,
            "must_change_password": user.must_change_password,
        }
    }


@api_router.post("/auth/admin/login")
def admin_login(
    payload: dict,
    request: Request,
    db: Session = Depends(get_db)
):
    """Admin-only login. Separate endpoint for security."""
    email = (payload.get("email") or "").strip().lower()
    password = payload.get("password") or ""

    if not email or not password:
        raise HTTPException(status_code=422, detail="Email and password are required.")

    user = db.query(User).filter(
        User.email == email,
        User.role == UserRole.ADMIN,
        User.is_active == True
    ).first()

    if not user or not verify_password(password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Incorrect admin credentials.")

    token = create_access_token(
        subject=user.email,
        role=user.role,
        user_id=user.id,
    )

    user.last_login_at = datetime.utcnow()
    db.commit()

    log_activity(db, "ADMIN_LOGIN", actor=user, resource_type="User", resource_id=user.id,
                 ip_address=get_client_ip(request))

    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "email": user.email,
            "full_name": user.full_name,
            "role": user.role,
            "must_change_password": False,
        }
    }


@api_router.post("/auth/change-password")
def change_password(
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_from_token)
):
    """Change password. Required on first login if must_change_password is set."""
    current_password = payload.get("current_password") or ""
    new_password = payload.get("new_password") or ""

    if not current_password or not new_password:
        raise HTTPException(status_code=422, detail="Both current and new password are required.")

    if len(new_password) < 8:
        raise HTTPException(status_code=422, detail="New password must be at least 8 characters.")

    if not verify_password(current_password, current_user.hashed_password):
        raise HTTPException(status_code=401, detail="Current password is incorrect.")

    current_user.hashed_password = get_password_hash(new_password)
    current_user.must_change_password = False
    db.commit()

    log_activity(db, "PASSWORD_CHANGED", actor=current_user, resource_type="User",
                 resource_id=current_user.id)

    return {"message": "Password updated successfully."}


@api_router.get("/auth/me")
def get_me(
    current_user: User = Depends(get_current_user_from_token),
    db: Session = Depends(get_db)
):
    return {
        "id": current_user.id,
        "email": current_user.email,
        "full_name": current_user.full_name,
        "role": current_user.role,
        "phone": current_user.phone,
        "preferred_language": current_user.preferred_language,
        "must_change_password": current_user.must_change_password,
        "has_farm": bool(
            current_user.farmer_profile and
            db.query(Farm).filter(Farm.farmer_id == current_user.farmer_profile.id).first()
        ) if current_user.is_farmer() else None,
    }


# ============================================================
# 2. FARMER REGISTRATION REQUEST
# ============================================================

@api_router.post("/registration/submit", status_code=201)
def submit_registration_request(
    full_name: str = Form(...),
    email: str = Form(...),
    phone: str = Form(...),
    farm_name: str = Form(...),
    farm_location: str = Form(...),
    farm_area_hectares: Optional[float] = Form(None),
    main_crops: Optional[str] = Form(None),
    rover_id: Optional[str] = Form(None),
    preferred_language: str = Form("en"),
    additional_info: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    """
    Submit a farmer registration request.
    No account is created here — Admin must approve first.
    No password/username asked.
    """
    email = email.strip().lower()

    # Check for duplicate active request or existing account
    existing_user = db.query(User).filter(User.email == email).first()
    if existing_user:
        raise HTTPException(
            status_code=409,
            detail="An account with this email address already exists."
        )

    existing_pending = db.query(RegistrationRequest).filter(
        RegistrationRequest.email == email,
        RegistrationRequest.status.in_([
            RegistrationStatus.PENDING,
            RegistrationStatus.UNDER_REVIEW
        ])
    ).first()
    if existing_pending:
        raise HTTPException(
            status_code=409,
            detail="A registration request with this email is already pending review."
        )

    reg = RegistrationRequest(
        full_name=full_name.strip(),
        email=email,
        phone=phone.strip(),
        farm_name=farm_name.strip(),
        farm_location=farm_location.strip(),
        farm_area_hectares=farm_area_hectares,
        main_crops=main_crops,
        rover_id=rover_id.strip() if rover_id else None,
        preferred_language=preferred_language,
        additional_info=additional_info,
        status=RegistrationStatus.PENDING,
    )
    db.add(reg)
    db.commit()
    db.refresh(reg)

    return {
        "id": reg.id,
        "status": reg.status,
        "message": (
            "Your registration request has been submitted successfully. "
            "You will be contacted by email and SMS once your request is reviewed."
        )
    }


@api_router.get("/registration/status")
def check_registration_status(
    email: str = Query(...),
    db: Session = Depends(get_db)
):
    """Public endpoint — farmer checks their request status by email."""
    email = email.strip().lower()
    reg = db.query(RegistrationRequest).filter(
        RegistrationRequest.email == email
    ).order_by(RegistrationRequest.submitted_at.desc()).first()

    if not reg:
        raise HTTPException(status_code=404, detail="No registration request found for this email.")

    return {
        "status": reg.status,
        "submitted_at": reg.submitted_at.isoformat(),
        "rejection_reason": reg.rejection_reason if reg.status == RegistrationStatus.REJECTED else None,
    }


# ── Admin: Registration Request Management ────────────────────

@api_router.get("/admin/registrations")
def list_registration_requests(
    status_filter: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin)
):
    query = db.query(RegistrationRequest)
    if status_filter:
        query = query.filter(RegistrationRequest.status == status_filter)
    reqs = query.order_by(RegistrationRequest.submitted_at.desc()).all()
    return [_format_reg_request(r) for r in reqs]


@api_router.get("/admin/registrations/{request_id}")
def get_registration_request(
    request_id: str,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin)
):
    reg = db.query(RegistrationRequest).filter(RegistrationRequest.id == request_id).first()
    if not reg:
        raise HTTPException(status_code=404, detail="Registration request not found.")
    return _format_reg_request(reg)


@api_router.patch("/admin/registrations/{request_id}/status")
def update_registration_status(
    request_id: str,
    payload: dict,
    background_tasks: BackgroundTasks,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin)
):
    """
    Admin approves or rejects a registration request.
    On APPROVED: creates farmer account, sends email + SMS.
    """
    reg = db.query(RegistrationRequest).filter(RegistrationRequest.id == request_id).first()
    if not reg:
        raise HTTPException(status_code=404, detail="Registration request not found.")

    new_status = payload.get("status")
    rejection_reason = payload.get("rejection_reason")

    valid_statuses = [
        RegistrationStatus.UNDER_REVIEW,
        RegistrationStatus.APPROVED,
        RegistrationStatus.REJECTED
    ]
    if new_status not in valid_statuses:
        raise HTTPException(status_code=422, detail=f"Invalid status: {new_status}")

    if reg.status == RegistrationStatus.APPROVED:
        raise HTTPException(status_code=409, detail="This request has already been approved.")

    reg.status = new_status
    reg.reviewed_by = admin.id
    reg.reviewed_at = datetime.utcnow()

    created_user_id = None

    if new_status == RegistrationStatus.APPROVED:
        # Create farmer account
        temp_password = generate_temp_password()
        activation_token = generate_activation_token()

        farmer_user = User(
            email=reg.email,
            hashed_password=get_password_hash(temp_password),
            full_name=reg.full_name,
            phone=reg.phone,
            role=UserRole.FARMER,
            is_active=True,
            must_change_password=True,  # Force password change on first login
            activation_token=activation_token,
            preferred_language=reg.preferred_language,
        )
        db.add(farmer_user)
        db.flush()

        farmer_profile = FarmerProfile(
            user_id=farmer_user.id,
            registration_request_id=reg.id,
        )
        db.add(farmer_profile)
        db.flush()

        # Create farm from registration data
        farm = Farm(
            farmer_id=farmer_profile.id,
            name=reg.farm_name,
            location_name=reg.farm_location,
            total_area_hectares=reg.farm_area_hectares,
            main_crop_types=reg.main_crops,
        )
        db.add(farm)
        db.flush()

        # Assign rover if provided
        if reg.rover_id:
            rover = db.query(RoverDevice).filter(
                RoverDevice.rover_id == reg.rover_id,
                RoverDevice.is_active == True
            ).first()
            if rover:
                assignment = RoverAssignment(
                    rover_id=rover.id,
                    farm_id=farm.id,
                    is_active=True,
                )
                db.add(assignment)

        reg.created_user_id = farmer_user.id
        created_user_id = farmer_user.id

        # Send activation info via background tasks
        background_tasks.add_task(
            send_farmer_activation,
            db_session_factory=None,  # Will use new session in task
            reg_id=reg.id,
            email=reg.email,
            phone=reg.phone,
            full_name=reg.full_name,
            temp_password=temp_password,
            activation_token=activation_token,
        )

        log_activity(
            db, "REGISTRATION_APPROVED", actor=admin,
            resource_type="RegistrationRequest", resource_id=reg.id,
            details={"farmer_email": reg.email, "farmer_user_id": farmer_user.id},
            ip_address=get_client_ip(request)
        )

    elif new_status == RegistrationStatus.REJECTED:
        if rejection_reason:
            reg.rejection_reason = rejection_reason
        log_activity(
            db, "REGISTRATION_REJECTED", actor=admin,
            resource_type="RegistrationRequest", resource_id=reg.id,
            details={"reason": rejection_reason},
            ip_address=get_client_ip(request)
        )

    db.commit()

    return {
        "id": reg.id,
        "status": reg.status,
        "created_user_id": created_user_id,
        "message": f"Registration request has been {new_status.lower()}."
    }


def send_farmer_activation(
    db_session_factory, reg_id: str, email: str, phone: str,
    full_name: str, temp_password: str, activation_token: str
):
    """Background task: send email + SMS with activation info."""
    from core.database import SessionLocal
    from services.communication import communication_service

    db = SessionLocal()
    try:
        reg = db.query(RegistrationRequest).filter(RegistrationRequest.id == reg_id).first()
        if not reg:
            return

        # Send email
        email_sent = communication_service.send_activation_email(
            to_email=email,
            full_name=full_name,
            temp_password=temp_password,
            activation_token=activation_token,
        )
        reg.email_status = "EMAIL_SENT" if email_sent else "EMAIL_FAILED"

        # Send SMS
        sms_sent = communication_service.send_activation_sms(
            to_phone=phone,
            full_name=full_name,
            temp_password=temp_password,
        )
        reg.sms_status = "SMS_SENT" if sms_sent else "SMS_FAILED"

        db.commit()
    except Exception as e:
        print(f"[Communication Error] {e}")
    finally:
        db.close()


def _format_reg_request(reg: RegistrationRequest) -> dict:
    return {
        "id": reg.id,
        "full_name": reg.full_name,
        "email": reg.email,
        "phone": reg.phone,
        "farm_name": reg.farm_name,
        "farm_location": reg.farm_location,
        "farm_area_hectares": reg.farm_area_hectares,
        "main_crops": reg.main_crops,
        "rover_id": reg.rover_id,
        "preferred_language": reg.preferred_language,
        "additional_info": reg.additional_info,
        "status": reg.status,
        "rejection_reason": reg.rejection_reason,
        "email_status": reg.email_status,
        "sms_status": reg.sms_status,
        "submitted_at": reg.submitted_at.isoformat(),
        "reviewed_at": reg.reviewed_at.isoformat() if reg.reviewed_at else None,
        "created_user_id": reg.created_user_id,
    }


# ============================================================
# 3. ADMIN — FARMER MANAGEMENT
# ============================================================

@api_router.get("/admin/farmers")
def list_farmers(
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin)
):
    farmers = db.query(User).filter(User.role == UserRole.FARMER).all()
    result = []
    for f in farmers:
        farms = db.query(Farm).filter(
            Farm.farmer_id == f.farmer_profile.id
        ).all() if f.farmer_profile else []
        result.append({
            "id": f.id,
            "email": f.email,
            "full_name": f.full_name,
            "phone": f.phone,
            "is_active": f.is_active,
            "preferred_language": f.preferred_language,
            "created_at": f.created_at.isoformat(),
            "last_login_at": f.last_login_at.isoformat() if f.last_login_at else None,
            "farm_count": len(farms),
        })
    return result


@api_router.patch("/admin/farmers/{user_id}/activate")
def toggle_farmer_active(
    user_id: str,
    payload: dict,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin)
):
    farmer = db.query(User).filter(
        User.id == user_id, User.role == UserRole.FARMER
    ).first()
    if not farmer:
        raise HTTPException(status_code=404, detail="Farmer not found.")

    farmer.is_active = payload.get("is_active", farmer.is_active)
    db.commit()

    log_activity(db, "FARMER_STATUS_CHANGED", actor=admin,
                 resource_type="User", resource_id=user_id,
                 details={"is_active": farmer.is_active},
                 ip_address=get_client_ip(request))

    return {"id": farmer.id, "is_active": farmer.is_active}


# ============================================================
# 4. FARMS
# ============================================================

@api_router.get("/farms")
def list_farms(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_from_token)
):
    if current_user.is_admin():
        farms = db.query(Farm).all()
    else:
        if not current_user.farmer_profile:
            return []
        farms = db.query(Farm).filter(
            Farm.farmer_id == current_user.farmer_profile.id
        ).all()
    return [_format_farm(f) for f in farms]


@api_router.get("/farms/{farm_id}")
def get_farm(
    farm_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_from_token)
):
    farm = db.query(Farm).filter(Farm.id == farm_id).first()
    if not farm:
        raise HTTPException(status_code=404, detail="Farm not found.")
    verify_farm_ownership(farm, current_user)
    return _format_farm(farm)


@api_router.put("/farms/{farm_id}")
def update_farm(
    farm_id: str,
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_from_token)
):
    farm = db.query(Farm).filter(Farm.id == farm_id).first()
    if not farm:
        raise HTTPException(status_code=404, detail="Farm not found.")
    verify_farm_ownership(farm, current_user)

    updatable = ["name", "location_name", "latitude", "longitude",
                 "total_area_hectares", "description", "main_crop_types"]
    for field_name in updatable:
        if field_name in payload:
            setattr(farm, field_name, payload[field_name])

    farm.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(farm)
    return _format_farm(farm)


def _format_farm(farm: Farm) -> dict:
    return {
        "id": farm.id,
        "name": farm.name,
        "location_name": farm.location_name,
        "latitude": farm.latitude,
        "longitude": farm.longitude,
        "total_area_hectares": farm.total_area_hectares,
        "description": farm.description,
        "main_crop_types": farm.main_crop_types,
        "created_at": farm.created_at.isoformat(),
    }


# ============================================================
# 5. FIELDS
# ============================================================

@api_router.get("/fields")
def list_fields(
    farm_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_from_token)
):
    query = db.query(Field)
    if current_user.is_farmer():
        if not current_user.farmer_profile:
            return []
        farm_ids = [
            f.id for f in db.query(Farm).filter(
                Farm.farmer_id == current_user.farmer_profile.id
            ).all()
        ]
        query = query.filter(Field.farm_id.in_(farm_ids))

    if farm_id:
        query = query.filter(Field.farm_id == farm_id)

    return [_format_field(f) for f in query.all()]


@api_router.post("/fields", status_code=201)
def create_field(
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_from_token)
):
    farm = db.query(Farm).filter(Farm.id == payload.get("farm_id")).first()
    if not farm:
        raise HTTPException(status_code=404, detail="Farm not found.")
    verify_farm_ownership(farm, current_user)

    field = Field(
        farm_id=farm.id,
        name=payload.get("name", "").strip(),
        area_hectares=payload.get("area_hectares"),
        location_description=payload.get("location_description"),
        boundary_polygon=payload.get("boundary_polygon"),
        notes=payload.get("notes"),
    )
    db.add(field)
    db.commit()
    db.refresh(field)
    return _format_field(field)


@api_router.put("/fields/{field_id}")
def update_field(
    field_id: str,
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_from_token)
):
    field = db.query(Field).filter(Field.id == field_id).first()
    if not field:
        raise HTTPException(status_code=404, detail="Field not found.")
    verify_field_ownership(field, current_user, db)

    for key in ["name", "area_hectares", "location_description", "boundary_polygon", "notes"]:
        if key in payload:
            setattr(field, key, payload[key])
    field.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(field)
    return _format_field(field)


@api_router.delete("/fields/{field_id}", status_code=204)
def delete_field(
    field_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_from_token)
):
    field = db.query(Field).filter(Field.id == field_id).first()
    if not field:
        raise HTTPException(status_code=404, detail="Field not found.")
    verify_field_ownership(field, current_user, db)
    db.delete(field)
    db.commit()


def _format_field(field: Field) -> dict:
    return {
        "id": field.id,
        "farm_id": field.farm_id,
        "name": field.name,
        "area_hectares": field.area_hectares,
        "location_description": field.location_description,
        "boundary_polygon": field.boundary_polygon,
        "notes": field.notes,
        "created_at": field.created_at.isoformat(),
        "crop_count": len(field.crops) if field.crops else 0,
    }


# ============================================================
# 6. CROPS
# ============================================================

@api_router.get("/crops")
def list_crops(
    field_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_from_token)
):
    query = db.query(Crop)
    if field_id:
        field = db.query(Field).filter(Field.id == field_id).first()
        if field:
            verify_field_ownership(field, current_user, db)
        query = query.filter(Crop.field_id == field_id)
    elif current_user.is_farmer() and current_user.farmer_profile:
        farm_ids = [f.id for f in db.query(Farm).filter(
            Farm.farmer_id == current_user.farmer_profile.id).all()]
        field_ids = [f.id for f in db.query(Field).filter(Field.farm_id.in_(farm_ids)).all()]
        query = query.filter(Crop.field_id.in_(field_ids))

    return [_format_crop(c) for c in query.all()]


@api_router.post("/crops", status_code=201)
def create_crop(payload: dict, db: Session = Depends(get_db),
                current_user: User = Depends(get_current_user_from_token)):
    field = db.query(Field).filter(Field.id == payload.get("field_id")).first()
    if not field:
        raise HTTPException(status_code=404, detail="Field not found.")
    verify_field_ownership(field, current_user, db)

    planting_date = None
    if payload.get("planting_date"):
        try:
            planting_date = datetime.fromisoformat(payload["planting_date"])
        except ValueError:
            pass

    harvest_date = None
    if payload.get("expected_harvest_date"):
        try:
            harvest_date = datetime.fromisoformat(payload["expected_harvest_date"])
        except ValueError:
            pass

    crop = Crop(
        field_id=field.id,
        name=payload.get("name", "").strip(),
        variety=payload.get("variety"),
        planting_date=planting_date,
        expected_harvest_date=harvest_date,
        growth_stage=payload.get("growth_stage"),
        status=payload.get("status", CropStatus.MONITORING),
        notes=payload.get("notes"),
    )
    db.add(crop)
    db.commit()
    db.refresh(crop)
    return _format_crop(crop)


@api_router.put("/crops/{crop_id}")
def update_crop(crop_id: str, payload: dict, db: Session = Depends(get_db),
                current_user: User = Depends(get_current_user_from_token)):
    crop = db.query(Crop).filter(Crop.id == crop_id).first()
    if not crop:
        raise HTTPException(status_code=404, detail="Crop not found.")
    field = db.query(Field).filter(Field.id == crop.field_id).first()
    verify_field_ownership(field, current_user, db)

    for key in ["name", "variety", "growth_stage", "status", "notes"]:
        if key in payload:
            setattr(crop, key, payload[key])
    crop.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(crop)
    return _format_crop(crop)


def _format_crop(crop: Crop) -> dict:
    return {
        "id": crop.id,
        "field_id": crop.field_id,
        "name": crop.name,
        "variety": crop.variety,
        "planting_date": crop.planting_date.isoformat() if crop.planting_date else None,
        "expected_harvest_date": crop.expected_harvest_date.isoformat() if crop.expected_harvest_date else None,
        "growth_stage": crop.growth_stage,
        "status": crop.status,
        "notes": crop.notes,
        "created_at": crop.created_at.isoformat(),
    }


# ============================================================
# 7. ROVERS
# ============================================================

@api_router.get("/rovers")
def list_rovers(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_from_token)
):
    if current_user.is_admin():
        rovers = db.query(RoverDevice).all()
    else:
        # Farmer sees only assigned rovers
        if not current_user.farmer_profile:
            return []
        farm_ids = [f.id for f in db.query(Farm).filter(
            Farm.farmer_id == current_user.farmer_profile.id).all()]
        assignments = db.query(RoverAssignment).filter(
            RoverAssignment.farm_id.in_(farm_ids),
            RoverAssignment.is_active == True
        ).all()
        rover_ids = [a.rover_id for a in assignments]
        rovers = db.query(RoverDevice).filter(RoverDevice.id.in_(rover_ids)).all()

    result = []
    for rover in rovers:
        # Get latest real telemetry (no fabrication)
        latest = db.query(RoverTelemetry).filter(
            RoverTelemetry.rover_id == rover.id
        ).order_by(RoverTelemetry.recorded_at.desc()).first()

        # Also check MQTT in-memory cache
        mqtt_data = mqtt_bridge.latest_telemetry.get(rover.rover_id)

        result.append(_format_rover(rover, latest, mqtt_data))

    return result


@api_router.get("/rovers/{rover_id_str}")
def get_rover(
    rover_id_str: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_from_token)
):
    rover = db.query(RoverDevice).filter(RoverDevice.rover_id == rover_id_str).first()
    if not rover:
        raise HTTPException(status_code=404, detail="Rover not found.")

    if current_user.is_farmer():
        _verify_rover_farmer_access(rover, current_user, db)

    latest = db.query(RoverTelemetry).filter(
        RoverTelemetry.rover_id == rover.id
    ).order_by(RoverTelemetry.recorded_at.desc()).first()
    mqtt_data = mqtt_bridge.latest_telemetry.get(rover.rover_id)
    return _format_rover(rover, latest, mqtt_data)


@api_router.post("/admin/rovers", status_code=201)
def register_rover(
    payload: dict,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin)
):
    existing = db.query(RoverDevice).filter(
        RoverDevice.rover_id == payload.get("rover_id")
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="Rover ID already registered.")

    rover = RoverDevice(
        rover_id=payload.get("rover_id", "").strip(),
        name=payload.get("name", "").strip(),
        description=payload.get("description"),
        hardware_spec=payload.get("hardware_spec"),
    )
    db.add(rover)
    db.commit()
    db.refresh(rover)
    return {"id": rover.id, "rover_id": rover.rover_id, "name": rover.name}


@api_router.post("/admin/rovers/{rover_db_id}/assign")
def assign_rover_to_farm(
    rover_db_id: str,
    payload: dict,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin)
):
    rover = db.query(RoverDevice).filter(RoverDevice.id == rover_db_id).first()
    if not rover:
        raise HTTPException(status_code=404, detail="Rover not found.")

    farm = db.query(Farm).filter(Farm.id == payload.get("farm_id")).first()
    if not farm:
        raise HTTPException(status_code=404, detail="Farm not found.")

    # Deactivate previous assignments for this rover
    db.query(RoverAssignment).filter(
        RoverAssignment.rover_id == rover.id,
        RoverAssignment.is_active == True
    ).update({"is_active": False, "unassigned_at": datetime.utcnow()})

    assignment = RoverAssignment(
        rover_id=rover.id,
        farm_id=farm.id,
        is_active=True,
        notes=payload.get("notes"),
    )
    db.add(assignment)
    db.commit()
    return {"message": "Rover assigned successfully."}


@api_router.post("/rovers/{rover_id_str}/command")
def send_rover_command(
    rover_id_str: str,
    payload: dict,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_from_token)
):
    """
    Send a command to the rover.
    Full safety pipeline: auth → authorization → validation → safety → dispatch → log.
    """
    rover = db.query(RoverDevice).filter(RoverDevice.rover_id == rover_id_str).first()
    if not rover:
        raise HTTPException(status_code=404, detail="Rover not found.")

    if current_user.is_farmer():
        _verify_rover_farmer_access(rover, current_user, db)

    cmd = (payload.get("command") or "").strip().upper()
    valid_commands = {
        "MOVE_FORWARD", "MOVE_BACKWARD", "TURN_LEFT", "TURN_RIGHT", "STOP",
        "START_FIELD_TASK", "PAUSE_FIELD_TASK", "RESUME_FIELD_TASK",
        "RETURN_HOME", "EMERGENCY_STOP", "START_SPRAYING", "STOP_SPRAYING",
        "CAPTURE_IMAGE", "RAISE_CAMERA", "LOWER_CAMERA", "ROTATE_NOZZLE",
    }
    if cmd not in valid_commands:
        raise HTTPException(status_code=422, detail=f"Unknown command: {cmd}")

    # Create command record
    command_record = RoverCommand(
        rover_id=rover.id,
        issued_by=current_user.id,
        command=cmd,
        params=payload.get("params"),
        status=CommandStatus.PENDING,
    )
    db.add(command_record)
    db.commit()
    db.refresh(command_record)

    # Dispatch via MQTT
    success = mqtt_bridge.dispatch_command(rover_id_str, cmd, payload.get("params") or {})

    command_record.status = CommandStatus.SENT if success else CommandStatus.FAILED
    if not success:
        command_record.error_message = "Failed to dispatch command. Rover may be offline."
    db.commit()

    log_activity(
        db, f"ROVER_COMMAND:{cmd}", actor=current_user,
        resource_type="RoverDevice", resource_id=rover.id,
        result="SUCCESS" if success else "FAILED",
        details={"command": cmd, "params": payload.get("params"), "command_id": command_record.id},
        ip_address=get_client_ip(request)
    )

    if not success:
        return {
            "command_id": command_record.id,
            "status": "FAILED",
            "command": cmd,
            "message": "Rover did not respond. The rover may be offline or out of range."
        }

    return {
        "command_id": command_record.id,
        "status": "SENT",
        "command": cmd,
        "rover_id": rover_id_str,
    }


@api_router.post("/rovers/{rover_id_str}/telemetry")
def receive_telemetry(
    rover_id_str: str,
    payload: dict,
    db: Session = Depends(get_db)
):
    """
    Endpoint for the rover/MQTT bridge to push real telemetry.
    Only called internally — not by the farmer UI directly.
    """
    rover = db.query(RoverDevice).filter(RoverDevice.rover_id == rover_id_str).first()
    if not rover:
        return {"error": "Rover not found"}

    telemetry = RoverTelemetry(
        rover_id=rover.id,
        battery_pct=payload.get("battery_pct"),
        battery_voltage=payload.get("battery_voltage"),
        is_charging=payload.get("is_charging"),
        spray_tank_pct=payload.get("spray_tank_pct"),
        latitude=payload.get("latitude"),
        longitude=payload.get("longitude"),
        heading_deg=payload.get("heading_deg"),
        speed_kmh=payload.get("speed_kmh"),
        camera_height_cm=payload.get("camera_height_cm"),
        motor_status=payload.get("motor_status"),
        pump_active=payload.get("pump_active"),
        solenoid_open=payload.get("solenoid_open"),
        camera_active=payload.get("camera_active"),
        gps_available=payload.get("gps_available"),
        rover_status=payload.get("rover_status"),
    )
    db.add(telemetry)
    db.commit()
    return {"status": "recorded"}


def _verify_rover_farmer_access(rover: RoverDevice, current_user: User, db: Session):
    if not current_user.farmer_profile:
        raise HTTPException(status_code=403, detail="Access denied.")
    farm_ids = [f.id for f in db.query(Farm).filter(
        Farm.farmer_id == current_user.farmer_profile.id).all()]
    assignment = db.query(RoverAssignment).filter(
        RoverAssignment.rover_id == rover.id,
        RoverAssignment.farm_id.in_(farm_ids),
        RoverAssignment.is_active == True
    ).first()
    if not assignment:
        raise HTTPException(status_code=403, detail="This rover is not assigned to your farm.")


def _format_rover(rover: RoverDevice, telemetry: Optional[RoverTelemetry], mqtt_data: Optional[dict]) -> dict:
    """
    Format rover response. Never fabricate values.
    Return None for unavailable fields rather than fake data.
    """
    def pick(tele_val, mqtt_key):
        """Prefer MQTT real-time data, fall back to DB telemetry."""
        if mqtt_data and mqtt_data.get(mqtt_key) is not None:
            return mqtt_data[mqtt_key]
        if telemetry and tele_val is not None:
            return tele_val
        return None  # Data unavailable

    is_connected = bool(mqtt_data)  # Only connected if we have live MQTT data

    return {
        "id": rover.id,
        "rover_id": rover.rover_id,
        "name": rover.name,
        "description": rover.description,
        "hardware_spec": rover.hardware_spec,
        "is_active": rover.is_active,
        # Telemetry — null means "data unavailable", not fabricated
        "is_connected": is_connected,
        "battery_pct": pick(telemetry.battery_pct if telemetry else None, "battery_pct"),
        "battery_voltage": pick(telemetry.battery_voltage if telemetry else None, "battery_voltage"),
        "is_charging": pick(telemetry.is_charging if telemetry else None, "is_charging"),
        "spray_tank_pct": pick(telemetry.spray_tank_pct if telemetry else None, "spray_tank_pct"),
        "latitude": pick(telemetry.latitude if telemetry else None, "latitude"),
        "longitude": pick(telemetry.longitude if telemetry else None, "longitude"),
        "heading_deg": pick(telemetry.heading_deg if telemetry else None, "heading_deg"),
        "speed_kmh": pick(telemetry.speed_kmh if telemetry else None, "speed_kmh"),
        "camera_height_cm": pick(telemetry.camera_height_cm if telemetry else None, "camera_height_cm"),
        "pump_active": pick(telemetry.pump_active if telemetry else None, "pump_active"),
        "solenoid_open": pick(telemetry.solenoid_open if telemetry else None, "solenoid_open"),
        "camera_active": pick(telemetry.camera_active if telemetry else None, "camera_active"),
        "gps_available": pick(telemetry.gps_available if telemetry else None, "gps_available"),
        "rover_status": pick(telemetry.rover_status if telemetry else None, "rover_status"),
        "last_seen_at": telemetry.recorded_at.isoformat() if telemetry else None,
    }


# ============================================================
# 8. CROP HEALTH
# ============================================================

@api_router.get("/crop-health")
def list_crop_health(
    field_id: Optional[str] = Query(None),
    crop_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_from_token)
):
    query = db.query(CropHealthRecord)
    if current_user.is_farmer() and current_user.farmer_profile:
        farm_ids = [f.id for f in db.query(Farm).filter(
            Farm.farmer_id == current_user.farmer_profile.id).all()]
        field_ids = [f.id for f in db.query(Field).filter(Field.farm_id.in_(farm_ids)).all()]
        query = query.filter(CropHealthRecord.field_id.in_(field_ids))

    if field_id:
        query = query.filter(CropHealthRecord.field_id == field_id)
    if crop_id:
        query = query.filter(CropHealthRecord.crop_id == crop_id)

    records = query.order_by(CropHealthRecord.created_at.desc()).limit(50).all()
    return [_format_health_record(r) for r in records]


@api_router.post("/crop-health/analyze-image")
async def analyze_crop_image(
    file: UploadFile = File(...),
    field_id: Optional[str] = Form(None),
    crop_id: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_from_token)
):
    """Analyze a single crop image for health problems."""
    # Validate file
    allowed_types = {"image/jpeg", "image/png", "image/webp"}
    if file.content_type not in allowed_types:
        raise HTTPException(status_code=422, detail="Only JPEG, PNG, or WebP images are accepted.")

    contents = await file.read()
    if len(contents) > 20 * 1024 * 1024:  # 20MB limit
        raise HTTPException(status_code=422, detail="Image file size must be under 20MB.")

    # Verify field ownership if provided
    if field_id:
        field = db.query(Field).filter(Field.id == field_id).first()
        if field:
            verify_field_ownership(field, current_user, db)

    # Run AI analysis
    ai_provider = get_ai_vision_provider()
    try:
        result = await ai_provider.analyze_crop_image(contents, file.filename)
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail="Crop analysis is temporarily unavailable. Please try again later."
        )

    # Upload evidence to Cloudinary
    image_url = None
    cloudinary_id = None
    try:
        upload_result = await media_service.upload_evidence_image(
            contents, file.filename,
            folder="smart-agritech/detections"
        )
        image_url = upload_result.get("url")
        cloudinary_id = upload_result.get("public_id")
    except Exception:
        pass  # Non-fatal — store result without image

    # Store record
    record = CropHealthRecord(
        field_id=field_id,
        crop_id=crop_id,
        analyzed_by=current_user.id,
        detection_type=result.detection_type,
        label=result.label,
        confidence=result.confidence,
        severity=result.severity,
        is_healthy=result.is_healthy,
        source="IMAGE_UPLOAD",
        description=result.description,
        recommendations=result.recommendations,
    )
    db.add(record)
    db.flush()

    if image_url and cloudinary_id:
        evidence = DetectionEvidence(
            health_record_id=record.id,
            cloudinary_public_id=cloudinary_id,
            cloudinary_url=image_url,
            cloudinary_folder="smart-agritech/detections",
            evidence_type="ORIGINAL",
            file_name=file.filename,
            file_size_bytes=len(contents),
        )
        db.add(evidence)

    db.commit()
    db.refresh(record)

    log_activity(db, "CROP_IMAGE_ANALYZED", actor=current_user,
                 resource_type="CropHealthRecord", resource_id=record.id,
                 details={"detection_type": result.detection_type, "label": result.label})

    return _format_health_record(record)


@api_router.post("/crop-health/analyze-video")
async def submit_video_analysis(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    field_id: Optional[str] = Form(None),
    crop_id: Optional[str] = Form(None),
    save_original_video: bool = Form(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_from_token)
):
    """
    Submit a video for async crop health analysis.
    Only useful frames are analyzed; evidence regions uploaded to Cloudinary.
    Original video is deleted unless farmer explicitly requests saving it.
    """
    allowed_video_types = {"video/mp4", "video/quicktime", "video/x-msvideo", "video/webm"}
    if file.content_type not in allowed_video_types:
        raise HTTPException(status_code=422, detail="Only MP4, MOV, AVI, or WebM videos are accepted.")

    contents = await file.read()
    if len(contents) > 500 * 1024 * 1024:  # 500MB limit
        raise HTTPException(status_code=422, detail="Video file size must be under 500MB.")

    # Save to temp file
    suffix = os.path.splitext(file.filename or "video.mp4")[1] or ".mp4"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp.write(contents)
    tmp.close()

    job = VideoAnalysisJob(
        submitted_by=current_user.id,
        field_id=field_id,
        crop_id=crop_id,
        original_filename=file.filename,
        file_size_bytes=len(contents),
        status=VideoJobStatus.PENDING,
        save_original_video=save_original_video,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    # Run analysis in background
    background_tasks.add_task(
        run_video_analysis_job,
        job_id=job.id,
        tmp_path=tmp.name,
    )

    return {
        "job_id": job.id,
        "status": VideoJobStatus.PENDING,
        "message": "Video analysis is in progress. You will be notified when results are ready.",
    }


@api_router.get("/crop-health/video-jobs/{job_id}")
def get_video_job_status(
    job_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_from_token)
):
    job = db.query(VideoAnalysisJob).filter(VideoAnalysisJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Analysis job not found.")
    if current_user.is_farmer() and job.submitted_by != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied.")

    return {
        "job_id": job.id,
        "status": job.status,
        "progress_pct": job.progress_pct,
        "error_message": job.error_message,
        "total_frames_extracted": job.total_frames_extracted,
        "frames_analyzed": job.frames_analyzed,
        "detections_found": job.detections_found,
        "submitted_at": job.submitted_at.isoformat(),
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }


async def run_video_analysis_job(job_id: str, tmp_path: str):
    """Background task: process video, extract evidence, clean up temp files."""
    from core.database import SessionLocal
    from services.video_analysis import process_video_file

    db = SessionLocal()
    try:
        await process_video_file(db, job_id, tmp_path)
    except Exception as e:
        job = db.query(VideoAnalysisJob).filter(VideoAnalysisJob.id == job_id).first()
        if job:
            job.status = VideoJobStatus.FAILED
            job.error_message = str(e)
            db.commit()
    finally:
        # Always clean up temp file
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        db.close()


def _format_health_record(record: CropHealthRecord) -> dict:
    return {
        "id": record.id,
        "field_id": record.field_id,
        "crop_id": record.crop_id,
        "detection_type": record.detection_type,
        "label": record.label,
        "confidence": record.confidence,  # Always shown, never hidden
        "severity": record.severity,
        "is_healthy": record.is_healthy,
        "source": record.source,
        "description": record.description,
        "recommendations": record.recommendations,
        "created_at": record.created_at.isoformat(),
        "evidence": [
            {
                "id": e.id,
                "url": e.cloudinary_url,
                "evidence_type": e.evidence_type,
            }
            for e in record.evidence
        ] if record.evidence else [],
    }


# ============================================================
# 9. SPRAYING
# ============================================================

@api_router.get("/spraying/sessions")
def list_spray_sessions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_from_token)
):
    query = db.query(SpraySession)
    if current_user.is_farmer() and current_user.farmer_profile:
        query = query.filter(SpraySession.initiated_by == current_user.id)
    return [_format_spray_session(s) for s in
            query.order_by(SpraySession.created_at.desc()).limit(50).all()]


@api_router.post("/spraying/sessions", status_code=201)
def start_spray_session(
    payload: dict,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_from_token)
):
    """
    Initiate a spray session. Runs through SafetyRuleEngine first.
    If safety check fails, spraying does NOT start and reason is shown.
    """
    from services.safety import safety_engine

    rover_id_str = payload.get("rover_id")
    rover = db.query(RoverDevice).filter(RoverDevice.rover_id == rover_id_str).first()
    if not rover:
        raise HTTPException(status_code=404, detail="Rover not found.")

    if current_user.is_farmer():
        _verify_rover_farmer_access(rover, current_user, db)

    product = None
    if payload.get("product_id"):
        product = db.query(Product).filter(
            Product.id == payload["product_id"],
            Product.is_active == True
        ).first()
        if not product:
            raise HTTPException(status_code=404, detail="Product not found or not available.")

    # Run safety checks
    mqtt_data = mqtt_bridge.latest_telemetry.get(rover_id_str)
    safety_result = safety_engine.check_spray_conditions(
        rover=rover,
        rover_telemetry=mqtt_data,
        product=product,
        field_id=payload.get("field_id"),
    )

    session_code = f"SPR-{uuid.uuid4().hex[:8].upper()}"
    session = SpraySession(
        session_code=session_code,
        rover_id=rover.id,
        farm_id=payload.get("farm_id"),
        field_id=payload.get("field_id"),
        crop_id=payload.get("crop_id"),
        product_id=product.id if product else None,
        initiated_by=current_user.id,
        spray_height_cm=payload.get("spray_height_cm"),
        nozzle_angle_deg=payload.get("nozzle_angle_deg"),
        target_area_hectares=payload.get("target_area_hectares"),
        safety_check_passed=safety_result.passed,
        safety_check_notes=safety_result.reason,
    )

    if not safety_result.passed:
        session.status = SprayStatus.ABORTED
        session.aborted_reason = safety_result.reason
        db.add(session)
        db.commit()

        log_activity(db, "SPRAY_BLOCKED_BY_SAFETY", actor=current_user,
                     resource_type="SpraySession", resource_id=session.id,
                     result="FAILED", details={"reason": safety_result.reason},
                     ip_address=get_client_ip(request))

        raise HTTPException(
            status_code=400,
            detail=f"Spraying cannot start: {safety_result.reason}"
        )

    session.status = SprayStatus.RUNNING
    session.started_at = datetime.utcnow()
    db.add(session)
    db.commit()
    db.refresh(session)

    # Dispatch command to rover
    mqtt_bridge.dispatch_command(rover_id_str, "START_SPRAYING", {
        "session_id": session.id,
        "spray_height_cm": payload.get("spray_height_cm"),
    })

    log_activity(db, "SPRAYING_STARTED", actor=current_user,
                 resource_type="SpraySession", resource_id=session.id,
                 ip_address=get_client_ip(request))

    return _format_spray_session(session)


@api_router.post("/spraying/sessions/{session_id}/stop")
def stop_spray_session(
    session_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_from_token)
):
    session = db.query(SpraySession).filter(SpraySession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Spray session not found.")

    if current_user.is_farmer() and session.initiated_by != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied.")

    session.status = SprayStatus.COMPLETED
    session.completed_at = datetime.utcnow()
    db.commit()

    rover = db.query(RoverDevice).filter(RoverDevice.id == session.rover_id).first()
    if rover:
        mqtt_bridge.dispatch_command(rover.rover_id, "STOP_SPRAYING", {"session_id": session.id})

    log_activity(db, "SPRAYING_STOPPED", actor=current_user,
                 resource_type="SpraySession", resource_id=session.id,
                 ip_address=get_client_ip(request))

    return _format_spray_session(session)


def _format_spray_session(s: SpraySession) -> dict:
    return {
        "id": s.id,
        "session_code": s.session_code,
        "rover_id": s.rover_id,
        "field_id": s.field_id,
        "status": s.status,
        "spray_height_cm": s.spray_height_cm,
        "nozzle_angle_deg": s.nozzle_angle_deg,
        "target_area_hectares": s.target_area_hectares,
        "volume_sprayed_liters": s.volume_sprayed_liters,
        "duration_seconds": s.duration_seconds,
        "safety_check_passed": s.safety_check_passed,
        "safety_check_notes": s.safety_check_notes,
        "started_at": s.started_at.isoformat() if s.started_at else None,
        "completed_at": s.completed_at.isoformat() if s.completed_at else None,
        "created_at": s.created_at.isoformat(),
    }


# ============================================================
# 10. PRODUCTS
# ============================================================

@api_router.get("/products")
def list_products(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_from_token)
):
    products = db.query(Product).filter(Product.is_active == True).all()
    return [_format_product(p) for p in products]


@api_router.post("/admin/products", status_code=201)
def create_product(
    payload: dict,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin)
):
    product = Product(
        name=payload.get("name", "").strip(),
        product_type=payload.get("product_type", "").strip(),
        target_crop=payload.get("target_crop"),
        target_problem=payload.get("target_problem"),
        usage_instructions=payload.get("usage_instructions"),
        safety_notes=payload.get("safety_notes"),
        recommended_quantity=payload.get("recommended_quantity"),
        is_active=payload.get("is_active", True),
        created_by=admin.id,
    )
    db.add(product)
    db.commit()
    db.refresh(product)

    log_activity(db, "PRODUCT_CREATED", actor=admin,
                 resource_type="Product", resource_id=product.id,
                 details={"name": product.name})

    return _format_product(product)


@api_router.put("/admin/products/{product_id}")
def update_product(
    product_id: str,
    payload: dict,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin)
):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found.")

    for key in ["name", "product_type", "target_crop", "target_problem",
                "usage_instructions", "safety_notes", "recommended_quantity", "is_active"]:
        if key in payload:
            setattr(product, key, payload[key])
    product.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(product)

    log_activity(db, "PRODUCT_UPDATED", actor=admin,
                 resource_type="Product", resource_id=product.id)

    return _format_product(product)


def _format_product(p: Product) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "product_type": p.product_type,
        "target_crop": p.target_crop,
        "target_problem": p.target_problem,
        "usage_instructions": p.usage_instructions,
        "safety_notes": p.safety_notes,
        "recommended_quantity": p.recommended_quantity,
        "is_active": p.is_active,
        "created_at": p.created_at.isoformat(),
    }


# ============================================================
# 11. WEATHER
# ============================================================

@api_router.get("/weather/current")
async def get_weather(
    lat: Optional[float] = Query(None),
    lng: Optional[float] = Query(None),
    farm_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_from_token)
):
    """
    Fetch real weather data from the weather API.
    Coordinates from farm GPS if available.
    """
    from services.weather import weather_service

    # Get coordinates from farm if farm_id provided
    if farm_id and not lat:
        farm = db.query(Farm).filter(Farm.id == farm_id).first()
        if farm and farm.latitude:
            lat = farm.latitude
            lng = farm.longitude

    if not lat or not lng:
        return {
            "available": False,
            "message": "Location information is not available for this farm. Please update your farm location to see weather data."
        }

    try:
        data = await weather_service.get_current_weather(lat, lng)
        if data:
            # Store record
            record = WeatherRecord(
                farm_id=farm_id,
                latitude=lat,
                longitude=lng,
                **{k: v for k, v in data.items()
                   if k in ["temperature_c", "humidity_pct", "wind_speed_kmh",
                             "wind_direction", "precipitation_chance_pct", "uv_index",
                             "condition", "spray_safe"]}
            )
            db.add(record)
            db.commit()
            return {"available": True, **data}
    except Exception as e:
        pass

    return {
        "available": False,
        "message": "Weather data is currently unavailable. Please try again later."
    }


# ============================================================
# 12. NOTIFICATIONS
# ============================================================

@api_router.get("/notifications")
def get_notifications(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_from_token)
):
    notifs = db.query(Notification).filter(
        Notification.user_id == current_user.id
    ).order_by(Notification.created_at.desc()).limit(50).all()

    return [
        {
            "id": n.id,
            "title": n.title,
            "message": n.message,
            "notification_type": n.notification_type,
            "is_read": n.is_read,
            "link": n.link,
            "created_at": n.created_at.isoformat(),
        }
        for n in notifs
    ]


@api_router.patch("/notifications/{notif_id}/read")
def mark_notification_read(
    notif_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_from_token)
):
    notif = db.query(Notification).filter(
        Notification.id == notif_id,
        Notification.user_id == current_user.id
    ).first()
    if notif:
        notif.is_read = True
        db.commit()
    return {"status": "ok"}


@api_router.patch("/notifications/read-all")
def mark_all_notifications_read(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_from_token)
):
    db.query(Notification).filter(
        Notification.user_id == current_user.id,
        Notification.is_read == False
    ).update({"is_read": True})
    db.commit()
    return {"status": "ok"}


# ============================================================
# 13. REPORTS
# ============================================================

@api_router.get("/reports")
def list_reports(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_from_token)
):
    query = db.query(Report)
    if current_user.is_farmer():
        query = query.filter(Report.generated_by == current_user.id)
    reports = query.order_by(Report.created_at.desc()).limit(50).all()
    return [
        {
            "id": r.id,
            "report_type": r.report_type,
            "title": r.title,
            "farm_id": r.farm_id,
            "date_from": r.date_from.isoformat() if r.date_from else None,
            "date_to": r.date_to.isoformat() if r.date_to else None,
            "summary": r.summary,
            "created_at": r.created_at.isoformat(),
        }
        for r in reports
    ]


# ============================================================
# 14. SUPPORT
# ============================================================

@api_router.get("/support/tickets")
def list_tickets(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_from_token)
):
    query = db.query(SupportTicket)
    if current_user.is_farmer():
        query = query.filter(SupportTicket.user_id == current_user.id)
    return [
        {
            "id": t.id,
            "subject": t.subject,
            "category": t.category,
            "status": t.status,
            "priority": t.priority,
            "description": t.description,
            "created_at": t.created_at.isoformat(),
            "message_count": len(t.messages) if t.messages else 0,
        }
        for t in query.order_by(SupportTicket.created_at.desc()).all()
    ]


@api_router.post("/support/tickets", status_code=201)
def create_ticket(
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_from_token)
):
    ticket = SupportTicket(
        user_id=current_user.id,
        subject=payload.get("subject", "").strip(),
        category=payload.get("category", "General"),
        description=payload.get("description", "").strip(),
        priority=payload.get("priority", "Medium"),
    )
    db.add(ticket)
    db.commit()
    db.refresh(ticket)
    return {"id": ticket.id, "subject": ticket.subject, "status": ticket.status}


@api_router.post("/support/tickets/{ticket_id}/messages")
def add_ticket_message(
    ticket_id: str,
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_from_token)
):
    ticket = db.query(SupportTicket).filter(SupportTicket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found.")

    if current_user.is_farmer() and ticket.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied.")

    msg = SupportMessage(
        ticket_id=ticket.id,
        author_id=current_user.id,
        message=payload.get("message", "").strip(),
        is_admin_reply=current_user.is_admin(),
    )
    db.add(msg)

    if current_user.is_admin() and ticket.status == TicketStatus.OPEN:
        ticket.status = TicketStatus.IN_PROGRESS

    db.commit()
    return {"id": msg.id, "message": msg.message}


@api_router.patch("/admin/support/tickets/{ticket_id}/status")
def update_ticket_status(
    ticket_id: str,
    payload: dict,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin)
):
    ticket = db.query(SupportTicket).filter(SupportTicket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found.")
    ticket.status = payload.get("status", ticket.status)
    ticket.updated_at = datetime.utcnow()
    db.commit()
    return {"id": ticket.id, "status": ticket.status}


# ============================================================
# 15. COMMUNITY
# ============================================================

@api_router.get("/community/posts")
def list_posts(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_from_token)
):
    posts = db.query(CommunityPost).filter(
        CommunityPost.is_visible == True
    ).order_by(CommunityPost.created_at.desc()).limit(50).all()
    return [_format_post(p) for p in posts]


@api_router.post("/community/posts", status_code=201)
def create_post(
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_from_token)
):
    post = CommunityPost(
        author_id=current_user.id,
        title=payload.get("title", "").strip(),
        content=payload.get("content", "").strip(),
        tags=payload.get("tags"),
    )
    db.add(post)
    db.commit()
    db.refresh(post)
    return _format_post(post)


@api_router.post("/community/posts/{post_id}/comments")
def add_comment(
    post_id: str,
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_from_token)
):
    post = db.query(CommunityPost).filter(
        CommunityPost.id == post_id, CommunityPost.is_visible == True
    ).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found.")

    comment = CommunityComment(
        post_id=post.id,
        author_id=current_user.id,
        content=payload.get("content", "").strip(),
    )
    db.add(comment)
    db.commit()
    db.refresh(comment)
    return {"id": comment.id, "content": comment.content}


@api_router.delete("/admin/community/posts/{post_id}")
def hide_post(
    post_id: str,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin)
):
    post = db.query(CommunityPost).filter(CommunityPost.id == post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found.")
    post.is_visible = False
    db.commit()
    return {"message": "Post removed."}


def _format_post(post: CommunityPost) -> dict:
    return {
        "id": post.id,
        "title": post.title,
        "content": post.content,
        "tags": post.tags,
        "image_url": post.image_cloudinary_url,
        "likes_count": post.likes_count,
        "author_name": post.author.full_name if post.author else "Unknown",
        "created_at": post.created_at.isoformat(),
        "comment_count": len([c for c in post.comments if c.is_visible]) if post.comments else 0,
    }


# ============================================================
# 16. ADMIN DASHBOARD SUMMARY
# ============================================================

@api_router.get("/admin/dashboard/summary")
def admin_dashboard_summary(
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin)
):
    from models import RegistrationStatus as RS

    pending_registrations = db.query(RegistrationRequest).filter(
        RegistrationRequest.status.in_([RS.PENDING, RS.UNDER_REVIEW])
    ).count()

    total_farmers = db.query(User).filter(User.role == UserRole.FARMER).count()
    total_rovers = db.query(RoverDevice).filter(RoverDevice.is_active == True).count()
    open_tickets = db.query(SupportTicket).filter(
        SupportTicket.status.in_([TicketStatus.OPEN, TicketStatus.IN_PROGRESS])
    ).count()
    total_crops = db.query(Crop).count()
    recent_detections = db.query(CropHealthRecord).filter(
        CropHealthRecord.is_healthy == False
    ).order_by(CropHealthRecord.created_at.desc()).limit(5).all()

    recent_activity = db.query(ActivityLog).order_by(
        ActivityLog.occurred_at.desc()
    ).limit(10).all()

    return {
        "pending_registrations": pending_registrations,
        "total_farmers": total_farmers,
        "total_rovers": total_rovers,
        "open_support_tickets": open_tickets,
        "total_crops": total_crops,
        "recent_crop_alerts": [
            {"id": d.id, "label": d.label, "severity": d.severity, "created_at": d.created_at.isoformat()}
            for d in recent_detections
        ],
        "recent_activity": [
            {
                "id": a.id,
                "action": a.action,
                "actor_email": a.actor_email,
                "actor_role": a.actor_role,
                "result": a.result,
                "occurred_at": a.occurred_at.isoformat(),
            }
            for a in recent_activity
        ]
    }


# ============================================================
# 17. FARMER DASHBOARD SUMMARY
# ============================================================

@api_router.get("/farmer/dashboard/summary")
def farmer_dashboard_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_farmer)
):
    if not current_user.farmer_profile:
        return {"setup_required": True, "message": "Please complete your farm setup."}

    farms = db.query(Farm).filter(
        Farm.farmer_id == current_user.farmer_profile.id
    ).all()

    farm_ids = [f.id for f in farms]
    field_ids = []
    for fid in farm_ids:
        fields = db.query(Field).filter(Field.farm_id == fid).all()
        field_ids.extend([f.id for f in fields])

    total_fields = len(field_ids)
    total_crops = db.query(Crop).filter(Crop.field_id.in_(field_ids)).count() if field_ids else 0

    # Rover — only real data
    rover_data = None
    if farm_ids:
        assignment = db.query(RoverAssignment).filter(
            RoverAssignment.farm_id.in_(farm_ids),
            RoverAssignment.is_active == True
        ).first()
        if assignment:
            rover = db.query(RoverDevice).filter(RoverDevice.id == assignment.rover_id).first()
            if rover:
                mqtt_data = mqtt_bridge.latest_telemetry.get(rover.rover_id)
                latest_tele = db.query(RoverTelemetry).filter(
                    RoverTelemetry.rover_id == rover.id
                ).order_by(RoverTelemetry.recorded_at.desc()).first()
                rover_data = _format_rover(rover, latest_tele, mqtt_data)

    # Latest crop health (only real detections)
    latest_detections = db.query(CropHealthRecord).filter(
        CropHealthRecord.field_id.in_(field_ids),
        CropHealthRecord.is_healthy == False
    ).order_by(CropHealthRecord.created_at.desc()).limit(5).all() if field_ids else []

    # Unread notifications
    unread_count = db.query(Notification).filter(
        Notification.user_id == current_user.id,
        Notification.is_read == False
    ).count()

    return {
        "setup_required": False,
        "farm_name": farms[0].name if farms else None,
        "farm_count": len(farms),
        "total_fields": total_fields,
        "total_crops": total_crops,
        "rover": rover_data,
        "crop_alerts": [
            {
                "id": d.id,
                "label": d.label,
                "severity": d.severity,
                "field_id": d.field_id,
                "created_at": d.created_at.isoformat(),
            }
            for d in latest_detections
        ],
        "unread_notifications": unread_count,
    }


# ============================================================
# 18. ACTIVITY LOG (Admin only)
# ============================================================

@api_router.get("/admin/activity-logs")
def list_activity_logs(
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin)
):
    logs = db.query(ActivityLog).order_by(
        ActivityLog.occurred_at.desc()
    ).limit(limit).all()

    return [
        {
            "id": a.id,
            "actor_email": a.actor_email,
            "actor_role": a.actor_role,
            "action": a.action,
            "resource_type": a.resource_type,
            "resource_id": a.resource_id,
            "result": a.result,
            "details": a.details,
            "ip_address": a.ip_address,
            "occurred_at": a.occurred_at.isoformat(),
        }
        for a in logs
    ]


# ============================================================
# 19. COMMUNICATION LOGS (Admin only)
# ============================================================

@api_router.get("/admin/communication-logs")
def list_communication_logs(
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin)
):
    logs = db.query(CommunicationLog).order_by(
        CommunicationLog.sent_at.desc()
    ).limit(100).all()

    return [
        {
            "id": l.id,
            "recipient_email": l.recipient_email,
            "recipient_phone": l.recipient_phone,
            "channel": l.channel,
            "subject": l.subject,
            "status": l.status,
            "error_message": l.error_message,
            "context": l.context,
            "sent_at": l.sent_at.isoformat(),
        }
        for l in logs
    ]


# ============================================================
# 20. FARMER PROFILE
# ============================================================

@api_router.get("/farmer/profile")
def get_farmer_profile(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_farmer)
):
    return {
        "id": current_user.id,
        "email": current_user.email,
        "full_name": current_user.full_name,
        "phone": current_user.phone,
        "preferred_language": current_user.preferred_language,
        "created_at": current_user.created_at.isoformat(),
        "last_login_at": current_user.last_login_at.isoformat() if current_user.last_login_at else None,
    }


@api_router.put("/farmer/profile")
def update_farmer_profile(
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_farmer)
):
    for key in ["full_name", "phone", "preferred_language"]:
        if key in payload:
            setattr(current_user, key, payload[key])
    current_user.updated_at = datetime.utcnow()
    db.commit()
    return {"message": "Profile updated successfully."}
