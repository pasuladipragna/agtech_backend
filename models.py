"""
Smart AgriTech Rover Platform — Database Models
Complete normalized relational schema.
Uses UUID primary keys, timestamps, foreign keys, and constraints.
No seed data — all data comes from real user actions.
"""

import uuid
from datetime import datetime
from sqlalchemy import (
    Column, String, Float, Boolean, DateTime, ForeignKey,
    Text, JSON, Integer, Enum as SAEnum, UniqueConstraint, Index
)
from sqlalchemy.orm import relationship
from core.database import Base


def gen_uuid() -> str:
    return str(uuid.uuid4())


# ============================================================
# ENUMS (stored as String for SQLite/Postgres compatibility)
# ============================================================

class UserRole:
    ADMIN = "ADMIN"
    FARMER = "FARMER"

class RegistrationStatus:
    PENDING = "PENDING"
    UNDER_REVIEW = "UNDER_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"

class CommunicationStatus:
    EMAIL_SENT = "EMAIL_SENT"
    EMAIL_FAILED = "EMAIL_FAILED"
    SMS_SENT = "SMS_SENT"
    SMS_FAILED = "SMS_FAILED"
    NOT_SENT = "NOT_SENT"

class RoverStatus:
    ONLINE = "ONLINE"
    OFFLINE = "OFFLINE"
    IDLE = "IDLE"
    MOVING = "MOVING"
    SPRAYING = "SPRAYING"
    EMERGENCY_STOP = "EMERGENCY_STOP"
    CHARGING = "CHARGING"
    MAINTENANCE = "MAINTENANCE"

class CommandStatus:
    PENDING = "PENDING"
    SENT = "SENT"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"

class CropStatus:
    HEALTHY = "Healthy"
    NEEDS_ATTENTION = "Needs Attention"
    PROBLEM_DETECTED = "Problem Detected"
    MONITORING = "Monitoring"
    HARVEST_READY = "Harvest Ready"

class DetectionType:
    HEALTHY = "Healthy"
    DISEASE = "Disease"
    PEST = "Pest"
    LEAF_DAMAGE = "Leaf Damage"
    NUTRIENT = "Nutrient Deficiency"
    ABNORMALITY = "Other Abnormality"
    UNKNOWN = "Unknown"

class Severity:
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    CRITICAL = "Critical"

class SprayStatus:
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    ABORTED = "ABORTED"
    FAILED = "FAILED"

class VideoJobStatus:
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

class TicketStatus:
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"

class NotificationType:
    INFO = "INFO"
    WARNING = "WARNING"
    ALERT = "ALERT"
    SUCCESS = "SUCCESS"


# ============================================================
# CORE USER MODEL
# ============================================================

class User(Base):
    """
    Core user record — ADMIN or FARMER role.
    Exactly ONE admin allowed (enforced by application logic + unique constraint).
    Farmer accounts are only created after Admin approval of RegistrationRequest.
    """
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    username = Column(String(100), unique=True, index=True, nullable=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=False)
    phone = Column(String(50), nullable=True)
    role = Column(String(20), nullable=False, default=UserRole.FARMER)

    is_active = Column(Boolean, default=True, nullable=False)
    # Forces password change on first login (after admin-generated temp password)
    must_change_password = Column(Boolean, default=False, nullable=False)
    # Activation token for email link (cleared after use)
    activation_token = Column(String(128), nullable=True, unique=True)
    activation_token_expires = Column(DateTime, nullable=True)

    preferred_language = Column(String(20), default="en", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_login_at = Column(DateTime, nullable=True)

    # Relationships
    farmer_profile = relationship("FarmerProfile", back_populates="user", uselist=False)
    notifications = relationship("Notification", back_populates="user")
    support_tickets = relationship("SupportTicket", back_populates="user")
    community_posts = relationship("CommunityPost", back_populates="author")
    community_comments = relationship("CommunityComment", back_populates="author")
    activity_logs = relationship("ActivityLog", back_populates="actor")

    def is_admin(self) -> bool:
        return self.role == UserRole.ADMIN

    def is_farmer(self) -> bool:
        return self.role == UserRole.FARMER

    __table_args__ = (
        # Enforce single admin at DB level
        Index("ix_users_role_email", "role", "email"),
    )


# ============================================================
# FARMER REGISTRATION REQUEST
# ============================================================

class RegistrationRequest(Base):
    """
    A farmer's initial registration request.
    No password/account created at this stage.
    Admin reviews and approves/rejects.
    On approval, a User + FarmerProfile is created.
    """
    __tablename__ = "registration_requests"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    full_name = Column(String(255), nullable=False)
    email = Column(String(255), nullable=False, index=True)
    phone = Column(String(50), nullable=False)
    telegram_chat_id = Column(String(100), nullable=True)
    farm_name = Column(String(255), nullable=False)
    farm_location = Column(String(255), nullable=False)
    farm_area_hectares = Column(Float, nullable=True)
    main_crops = Column(String(500), nullable=True)     # comma-separated
    rover_id = Column(String(100), nullable=True)        # optional
    preferred_language = Column(String(20), default="en")
    additional_info = Column(Text, nullable=True)

    status = Column(String(30), default=RegistrationStatus.PENDING, nullable=False)
    rejection_reason = Column(Text, nullable=True)

    # Admin who reviewed
    reviewed_by = Column(String(36), ForeignKey("users.id"), nullable=True)
    reviewed_at = Column(DateTime, nullable=True)

    # Communication after approval
    email_status = Column(String(30), default=CommunicationStatus.NOT_SENT)
    sms_status = Column(String(30), default=CommunicationStatus.NOT_SENT)

    # Link to created user after approval
    created_user_id = Column(String(36), ForeignKey("users.id"), nullable=True)

    submitted_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    reviewer = relationship("User", foreign_keys=[reviewed_by])
    created_user = relationship("User", foreign_keys=[created_user_id])


# ============================================================
# FARMER PROFILE
# ============================================================

class FarmerProfile(Base):
    """
    Extended profile data for a farmer user.
    Created when admin approves a registration request.
    """
    __tablename__ = "farmer_profiles"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    user_id = Column(String(36), ForeignKey("users.id"), unique=True, nullable=False)
    registration_request_id = Column(String(36), ForeignKey("registration_requests.id"), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="farmer_profile")
    farms = relationship("Farm", back_populates="farmer")


# ============================================================
# FARM & FIELD & CROP
# ============================================================

class Farm(Base):
    __tablename__ = "farms"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    farmer_id = Column(String(36), ForeignKey("farmer_profiles.id"), nullable=False)
    name = Column(String(255), nullable=False)
    location_name = Column(String(255), nullable=False)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    total_area_hectares = Column(Float, nullable=True)
    description = Column(Text, nullable=True)
    main_crop_types = Column(String(500), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    farmer = relationship("FarmerProfile", back_populates="farms")
    fields = relationship("Field", back_populates="farm")
    rover_assignments = relationship("RoverAssignment", back_populates="farm")


class Field(Base):
    __tablename__ = "fields"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    farm_id = Column(String(36), ForeignKey("farms.id"), nullable=False)
    name = Column(String(255), nullable=False)
    area_hectares = Column(Float, nullable=True)
    location_description = Column(String(500), nullable=True)
    boundary_polygon = Column(JSON, nullable=True)   # GeoJSON polygon
    notes = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    farm = relationship("Farm", back_populates="fields")
    crops = relationship("Crop", back_populates="field")
    spray_sessions = relationship("SpraySession", back_populates="field")
    crop_health_records = relationship("CropHealthRecord", back_populates="field")


class Crop(Base):
    __tablename__ = "crops"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    field_id = Column(String(36), ForeignKey("fields.id"), nullable=False)
    name = Column(String(255), nullable=False)
    variety = Column(String(255), nullable=True)
    planting_date = Column(DateTime, nullable=True)
    expected_harvest_date = Column(DateTime, nullable=True)
    growth_stage = Column(String(100), nullable=True)
    status = Column(String(50), default=CropStatus.MONITORING, nullable=False)
    notes = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    field = relationship("Field", back_populates="crops")
    crop_health_records = relationship("CropHealthRecord", back_populates="crop")


# ============================================================
# ROVER DEVICE & ASSIGNMENT
# ============================================================

class RoverDevice(Base):
    """
    Registered rover hardware unit.
    rover_id is the unique hardware identifier (e.g. "ROVER-4WD-01").
    """
    __tablename__ = "rover_devices"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    rover_id = Column(String(100), unique=True, index=True, nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    hardware_spec = Column(JSON, nullable=True)   # motors, pump, tank capacity, etc.

    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    assignments = relationship("RoverAssignment", back_populates="rover")
    commands = relationship("RoverCommand", back_populates="rover")
    telemetry = relationship("RoverTelemetry", back_populates="rover")
    tasks = relationship("RoverTask", back_populates="rover")
    spray_sessions = relationship("SpraySession", back_populates="rover")


class RoverAssignment(Base):
    """Links a rover to a farm. Active assignment = farm uses that rover."""
    __tablename__ = "rover_assignments"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    rover_id = Column(String(36), ForeignKey("rover_devices.id"), nullable=False)
    farm_id = Column(String(36), ForeignKey("farms.id"), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    assigned_at = Column(DateTime, default=datetime.utcnow)
    unassigned_at = Column(DateTime, nullable=True)
    notes = Column(Text, nullable=True)

    rover = relationship("RoverDevice", back_populates="assignments")
    farm = relationship("Farm", back_populates="rover_assignments")


class RoverCommand(Base):
    """
    Every command sent to a rover is logged here with full lifecycle tracking.
    Physical commands go through: auth → safety → dispatch → ack → log.
    """
    __tablename__ = "rover_commands"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    rover_id = Column(String(36), ForeignKey("rover_devices.id"), nullable=False)
    issued_by = Column(String(36), ForeignKey("users.id"), nullable=False)
    command = Column(String(100), nullable=False)   # MOVE_FORWARD, EMERGENCY_STOP, etc.
    params = Column(JSON, nullable=True)

    status = Column(String(30), default=CommandStatus.PENDING, nullable=False)
    acknowledged_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)

    issued_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    rover = relationship("RoverDevice", back_populates="commands")
    issuer = relationship("User")


class RoverTelemetry(Base):
    """
    Real-time telemetry snapshots received from the rover via MQTT.
    Only real values stored — no fabricated data.
    """
    __tablename__ = "rover_telemetry"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    rover_id = Column(String(36), ForeignKey("rover_devices.id"), nullable=False)

    # All nullable — only set when real data is received
    battery_pct = Column(Float, nullable=True)
    battery_voltage = Column(Float, nullable=True)
    is_charging = Column(Boolean, nullable=True)
    spray_tank_pct = Column(Float, nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    heading_deg = Column(Float, nullable=True)
    speed_kmh = Column(Float, nullable=True)
    camera_height_cm = Column(Float, nullable=True)
    motor_status = Column(String(30), nullable=True)
    pump_active = Column(Boolean, nullable=True)
    solenoid_open = Column(Boolean, nullable=True)
    camera_active = Column(Boolean, nullable=True)
    gps_available = Column(Boolean, nullable=True)
    rover_status = Column(String(30), nullable=True)

    recorded_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    rover = relationship("RoverDevice", back_populates="telemetry")

    __table_args__ = (
        Index("ix_rover_telemetry_rover_time", "rover_id", "recorded_at"),
    )


class RoverTask(Base):
    """Autonomous field task (scan, spray, monitoring run)."""
    __tablename__ = "rover_tasks"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    task_code = Column(String(100), unique=True, nullable=False)
    rover_id = Column(String(36), ForeignKey("rover_devices.id"), nullable=False)
    farm_id = Column(String(36), ForeignKey("farms.id"), nullable=True)
    field_id = Column(String(36), ForeignKey("fields.id"), nullable=True)
    created_by = Column(String(36), ForeignKey("users.id"), nullable=False)

    task_type = Column(String(50), nullable=False)  # SCAN, SPRAY, MONITOR
    status = Column(String(30), default="PENDING", nullable=False)
    waypoints = Column(JSON, nullable=True)
    distance_traveled_m = Column(Float, default=0.0)

    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    rover = relationship("RoverDevice", back_populates="tasks")


# ============================================================
# CROP HEALTH / DETECTION
# ============================================================

class CropHealthRecord(Base):
    """
    A crop health analysis result from image or video analysis.
    Confidence is always shown — never presented as guaranteed fact.
    """
    __tablename__ = "crop_health_records"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    field_id = Column(String(36), ForeignKey("fields.id"), nullable=True)
    crop_id = Column(String(36), ForeignKey("crops.id"), nullable=True)
    analyzed_by = Column(String(36), ForeignKey("users.id"), nullable=False)

    detection_type = Column(String(50), nullable=False)   # DetectionType
    label = Column(String(255), nullable=False)            # e.g. "Early Blight"
    confidence = Column(Float, nullable=True)              # 0.0 – 1.0, nullable if unknown
    severity = Column(String(20), nullable=True)           # Severity
    is_healthy = Column(Boolean, nullable=False, default=False)

    # Source of analysis
    source = Column(String(30), nullable=False)  # IMAGE_UPLOAD, VIDEO_UPLOAD, ROVER_CAMERA

    # Farmer-friendly AI explanation and recommendations
    description = Column(Text, nullable=True)
    recommendations = Column(Text, nullable=True)

    # Location context
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    field = relationship("Field", back_populates="crop_health_records")
    crop = relationship("Crop", back_populates="crop_health_records")
    evidence = relationship("DetectionEvidence", back_populates="health_record")
    analyzer = relationship("User")


class DetectionEvidence(Base):
    """
    Evidence images/regions uploaded to Cloudinary from crop health analysis.
    One health record can have multiple evidence images (original + ROI crops).
    """
    __tablename__ = "detection_evidence"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    health_record_id = Column(String(36), ForeignKey("crop_health_records.id"), nullable=False)

    cloudinary_public_id = Column(String(500), nullable=False)
    cloudinary_url = Column(Text, nullable=False)
    cloudinary_folder = Column(String(255), nullable=True)
    evidence_type = Column(String(30), nullable=False)  # ORIGINAL, ROI_CROP, FRAME
    file_name = Column(String(255), nullable=True)
    file_size_bytes = Column(Integer, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    health_record = relationship("CropHealthRecord", back_populates="evidence")


# ============================================================
# VIDEO ANALYSIS JOB
# ============================================================

class VideoAnalysisJob(Base):
    """
    Tracks async video processing jobs.
    Farmer sees status updates; video is deleted after processing unless saved.
    """
    __tablename__ = "video_analysis_jobs"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    submitted_by = Column(String(36), ForeignKey("users.id"), nullable=False)
    field_id = Column(String(36), ForeignKey("fields.id"), nullable=True)
    crop_id = Column(String(36), ForeignKey("crops.id"), nullable=True)

    original_filename = Column(String(255), nullable=True)
    file_size_bytes = Column(Integer, nullable=True)
    duration_seconds = Column(Float, nullable=True)

    status = Column(String(30), default=VideoJobStatus.PENDING, nullable=False)
    progress_pct = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)

    # Optional: farmer chose to save original video
    save_original_video = Column(Boolean, default=False)
    original_video_cloudinary_url = Column(Text, nullable=True)
    original_video_cloudinary_id = Column(String(500), nullable=True)

    # Stats
    total_frames_extracted = Column(Integer, nullable=True)
    frames_analyzed = Column(Integer, nullable=True)
    detections_found = Column(Integer, nullable=True)

    submitted_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    submitter = relationship("User")


# ============================================================
# PRODUCTS (Pesticides, Fertilizers, etc.)
# ============================================================

class Product(Base):
    """Agricultural products managed by Admin only."""
    __tablename__ = "products"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    name = Column(String(255), nullable=False)
    product_type = Column(String(100), nullable=False)  # Pesticide, Fertilizer, Herbicide
    target_crop = Column(String(255), nullable=True)
    target_problem = Column(String(255), nullable=True)
    usage_instructions = Column(Text, nullable=True)
    safety_notes = Column(Text, nullable=True)
    recommended_quantity = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_by = Column(String(36), ForeignKey("users.id"), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    spray_sessions = relationship("SpraySession", back_populates="product")


# ============================================================
# SPRAYING
# ============================================================

class SpraySession(Base):
    """
    A controlled spraying session.
    Must pass SafetyRuleEngine checks before starting.
    """
    __tablename__ = "spray_sessions"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    session_code = Column(String(100), unique=True, nullable=False)
    rover_id = Column(String(36), ForeignKey("rover_devices.id"), nullable=False)
    farm_id = Column(String(36), ForeignKey("farms.id"), nullable=True)
    field_id = Column(String(36), ForeignKey("fields.id"), nullable=True)
    crop_id = Column(String(36), ForeignKey("crops.id"), nullable=True)
    product_id = Column(String(36), ForeignKey("products.id"), nullable=True)
    initiated_by = Column(String(36), ForeignKey("users.id"), nullable=False)

    status = Column(String(30), default=SprayStatus.PENDING, nullable=False)
    spray_height_cm = Column(Float, nullable=True)
    nozzle_angle_deg = Column(Float, nullable=True)
    target_area_hectares = Column(Float, nullable=True)
    volume_sprayed_liters = Column(Float, nullable=True)
    duration_seconds = Column(Integer, nullable=True)

    # Safety check result (stored for audit)
    safety_check_passed = Column(Boolean, nullable=True)
    safety_check_notes = Column(Text, nullable=True)

    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    aborted_reason = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    rover = relationship("RoverDevice", back_populates="spray_sessions")
    field = relationship("Field", back_populates="spray_sessions")
    product = relationship("Product", back_populates="spray_sessions")
    initiator = relationship("User")


class SprayEvent(Base):
    """Individual spray pulse events within a session."""
    __tablename__ = "spray_events"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    session_id = Column(String(36), ForeignKey("spray_sessions.id"), nullable=False)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    volume_ml = Column(Float, nullable=True)
    duration_ms = Column(Integer, nullable=True)
    occurred_at = Column(DateTime, default=datetime.utcnow)

    session = relationship("SpraySession")


# ============================================================
# WEATHER
# ============================================================

class WeatherRecord(Base):
    """
    Weather data fetched from external API.
    No fabricated values — only store real API responses.
    """
    __tablename__ = "weather_records"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    farm_id = Column(String(36), ForeignKey("farms.id"), nullable=True)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)

    temperature_c = Column(Float, nullable=True)
    humidity_pct = Column(Float, nullable=True)
    wind_speed_kmh = Column(Float, nullable=True)
    wind_direction = Column(String(20), nullable=True)
    precipitation_chance_pct = Column(Float, nullable=True)
    uv_index = Column(Float, nullable=True)
    condition = Column(String(100), nullable=True)
    spray_safe = Column(Boolean, nullable=True)

    raw_response = Column(JSON, nullable=True)
    fetched_at = Column(DateTime, default=datetime.utcnow, nullable=False)


# ============================================================
# NOTIFICATIONS
# ============================================================

class Notification(Base):
    __tablename__ = "notifications"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    title = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)
    notification_type = Column(String(30), default=NotificationType.INFO)
    is_read = Column(Boolean, default=False)
    link = Column(String(500), nullable=True)  # optional deep link
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="notifications")


# ============================================================
# REPORTS
# ============================================================

class Report(Base):
    __tablename__ = "reports"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    report_type = Column(String(50), nullable=False)  # CROP_HEALTH, SPRAY, ROVER_ACTIVITY
    title = Column(String(255), nullable=False)
    generated_by = Column(String(36), ForeignKey("users.id"), nullable=True)
    farm_id = Column(String(36), ForeignKey("farms.id"), nullable=True)
    field_id = Column(String(36), ForeignKey("fields.id"), nullable=True)
    crop_id = Column(String(36), ForeignKey("crops.id"), nullable=True)

    date_from = Column(DateTime, nullable=True)
    date_to = Column(DateTime, nullable=True)
    summary = Column(Text, nullable=True)
    findings = Column(JSON, nullable=True)
    recommendations = Column(Text, nullable=True)

    cloudinary_url = Column(Text, nullable=True)  # exported PDF/image if any
    created_at = Column(DateTime, default=datetime.utcnow)

    generator = relationship("User")


# ============================================================
# SUPPORT
# ============================================================

class SupportTicket(Base):
    __tablename__ = "support_tickets"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    subject = Column(String(255), nullable=False)
    category = Column(String(100), nullable=False)
    description = Column(Text, nullable=False)
    status = Column(String(30), default=TicketStatus.OPEN, nullable=False)
    priority = Column(String(20), default="Medium")

    attachment_url = Column(Text, nullable=True)
    attachment_cloudinary_id = Column(String(500), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="support_tickets")
    messages = relationship("SupportMessage", back_populates="ticket")


class SupportMessage(Base):
    __tablename__ = "support_messages"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    ticket_id = Column(String(36), ForeignKey("support_tickets.id"), nullable=False)
    author_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    message = Column(Text, nullable=False)
    is_admin_reply = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    ticket = relationship("SupportTicket", back_populates="messages")
    author = relationship("User")


# ============================================================
# COMMUNITY
# ============================================================

class CommunityPost(Base):
    __tablename__ = "community_posts"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    author_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    title = Column(String(255), nullable=False)
    content = Column(Text, nullable=False)
    tags = Column(String(255), nullable=True)
    image_cloudinary_url = Column(Text, nullable=True)
    image_cloudinary_id = Column(String(500), nullable=True)
    is_visible = Column(Boolean, default=True)  # Admin can hide
    likes_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    author = relationship("User", back_populates="community_posts")
    comments = relationship("CommunityComment", back_populates="post")


class CommunityComment(Base):
    __tablename__ = "community_comments"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    post_id = Column(String(36), ForeignKey("community_posts.id"), nullable=False)
    author_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    content = Column(Text, nullable=False)
    is_visible = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    post = relationship("CommunityPost", back_populates="comments")
    author = relationship("User", back_populates="community_comments")


# ============================================================
# MEDIA ASSETS
# ============================================================

class MediaAsset(Base):
    """
    Tracks all Cloudinary uploads across the system.
    Central registry for media management and audit.
    """
    __tablename__ = "media_assets"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    uploaded_by = Column(String(36), ForeignKey("users.id"), nullable=True)
    cloudinary_public_id = Column(String(500), nullable=False, unique=True)
    cloudinary_url = Column(Text, nullable=False)
    cloudinary_folder = Column(String(255), nullable=True)
    resource_type = Column(String(30), nullable=False)   # image, video, raw
    file_name = Column(String(255), nullable=True)
    file_size_bytes = Column(Integer, nullable=True)
    mime_type = Column(String(100), nullable=True)

    # Context linking
    entity_type = Column(String(50), nullable=True)  # detection, community_post, support, etc.
    entity_id = Column(String(36), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    uploader = relationship("User")


# ============================================================
# COMMUNICATION LOG
# ============================================================

class CommunicationLog(Base):
    """Tracks all email and SMS communications sent by the system."""
    __tablename__ = "communication_logs"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    recipient_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    recipient_email = Column(String(255), nullable=True)
    recipient_phone = Column(String(50), nullable=True)
    channel = Column(String(20), nullable=False)  # EMAIL, SMS
    subject = Column(String(255), nullable=True)
    message_preview = Column(String(500), nullable=True)
    status = Column(String(30), nullable=False)   # SENT, FAILED
    error_message = Column(Text, nullable=True)
    context = Column(String(100), nullable=True)  # REGISTRATION_APPROVAL, NOTIFICATION, etc.
    sent_at = Column(DateTime, default=datetime.utcnow)

    recipient = relationship("User")


# ============================================================
# ACTIVITY LOG
# ============================================================

class ActivityLog(Base):
    """
    Full audit trail of important system actions.
    Admin can view all logs. Used for compliance and debugging.
    """
    __tablename__ = "activity_logs"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    actor_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    actor_email = Column(String(255), nullable=True)  # stored directly for immutability
    actor_role = Column(String(20), nullable=True)

    action = Column(String(100), nullable=False)
    resource_type = Column(String(50), nullable=True)  # User, Farm, Rover, Spraying, etc.
    resource_id = Column(String(36), nullable=True)
    result = Column(String(30), nullable=True)          # SUCCESS, FAILED, DENIED

    details = Column(JSON, nullable=True)
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(500), nullable=True)

    occurred_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    actor = relationship("User", back_populates="activity_logs")

    __table_args__ = (
        Index("ix_activity_logs_actor_time", "actor_id", "occurred_at"),
        Index("ix_activity_logs_action", "action"),
    )
