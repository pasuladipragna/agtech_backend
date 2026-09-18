import sys
import os
import datetime

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.database import engine, Base, SessionLocal
from core.security import get_password_hash
from models import (
    User, Farm, Field, Crop, Rover, Mission, Detection, SprayLog,
    Notification, SupportTicket, CommunityPost, Product, AuditLog
)

def seed_database():
    print("Creating database tables for agtech_backend...")
    Base.metadata.create_all(bind=engine)
    
    db = SessionLocal()

    print("Clearing old data...")
    db.query(AuditLog).delete()
    db.query(Product).delete()
    db.query(CommunityPost).delete()
    db.query(SupportTicket).delete()
    db.query(Notification).delete()
    db.query(SprayLog).delete()
    db.query(Detection).delete()
    db.query(Mission).delete()
    db.query(Rover).delete()
    db.query(Crop).delete()
    db.query(Field).delete()
    db.query(Farm).delete()
    db.query(User).delete()
    db.commit()

    print("Seeding Users...")
    farmer = User(
        email="farmer@agritech.com",
        hashed_password=get_password_hash("password123"),
        full_name="John Deere (Farmer)",
        role="farmer",
        phone="+1 (555) 234-5678"
    )
    admin = User(
        email="admin@agritech.com",
        hashed_password=get_password_hash("admin123"),
        full_name="AgriTech System Admin",
        role="admin",
        phone="+1 (555) 999-0000"
    )
    db.add_all([farmer, admin])
    db.commit()

    print("Seeding Farm & Fields...")
    farm = Farm(
        owner_id=farmer.id,
        name="SunValley Valley Precision Farm",
        location_name="Fresno, California",
        latitude=36.778259,
        longitude=-119.417931,
        total_area_hectares=18.5
    )
    db.add(farm)
    db.commit()

    field1 = Field(
        farm_id=farm.id,
        name="North Canopy - Tomato Block A",
        boundary_polygon=[
            [36.7785, -119.4185],
            [36.7795, -119.4185],
            [36.7795, -119.4170],
            [36.7785, -119.4170]
        ],
        area_hectares=4.2,
        soil_type="Clay Loam",
        irrigation_type="Drip Irrigation"
    )
    field2 = Field(
        farm_id=farm.id,
        name="South Lane - Corn Whorl Block B",
        boundary_polygon=[
            [36.7770, -119.4185],
            [36.7780, -119.4185],
            [36.7780, -119.4170],
            [36.7770, -119.4170]
        ],
        area_hectares=6.5,
        soil_type="Sandy Loam",
        irrigation_type="Center Pivot"
    )
    db.add_all([field1, field2])
    db.commit()

    print("Seeding Crops...")
    crop1 = Crop(
        field_id=field1.id,
        name="Roma Tomato",
        variety="VFT Hybrid",
        planting_date=datetime.datetime.now() - datetime.timedelta(days=45),
        growth_stage="Fruiting",
        health_score=91.5
    )
    crop2 = Crop(
        field_id=field2.id,
        name="Sweet Corn",
        variety="Golden Bantam",
        planting_date=datetime.datetime.now() - datetime.timedelta(days=30),
        growth_stage="Vegetative",
        health_score=96.0
    )
    db.add_all([crop1, crop2])
    db.commit()

    print("Seeding Rover...")
    rover = Rover(
        rover_id="ROVER-4WD-01",
        farm_id=farm.id,
        name="AgriRover 4WD Precision Sprayer",
        status="ONLINE",
        battery_pct=94.5,
        spray_tank_pct=88.0,
        latitude=36.778259,
        longitude=-119.417931,
        heading_deg=45.0,
        camera_height_cm=110.0,
        hardware_spec={
            "drive": "4WD DC Geared Motors",
            "pump": "12V DC High-Pressure Spray Pump",
            "valve": "High-Speed Solenoid Valve",
            "nozzles": "Dual Rotatable Spray Nozzles",
            "camera_mount": "Motorized Linear Actuator Mount",
            "sensors": "GPS Location Module (No Ultrasonic/IR required)"
        }
    )
    db.add(rover)
    db.commit()

    print("Seeding AI Detections...")
    det1 = Detection(
        field_id=field1.id,
        crop_name="Roma Tomato",
        is_healthy=False,
        label="Tomato Early Blight (Alternaria solani)",
        confidence=0.94,
        severity="Medium",
        category="Fungus",
        image_url="https://images.unsplash.com/photo-1592417817098-8f3d6eb231fc?auto=format&fit=crop&w=600&q=80",
        recommended_treatment="Apply Copper Hydroxide fungicide (2.5g/L). Repeat after 7-10 days if humid conditions persist.",
        recommended_spray_volume_l_per_ha=350.0,
        latitude=36.7786,
        longitude=-119.4182
    )
    det2 = Detection(
        field_id=field2.id,
        crop_name="Sweet Corn",
        is_healthy=False,
        label="Corn Armyworm Infestation (Spodoptera frugiperda)",
        confidence=0.91,
        severity="High",
        category="Pest",
        image_url="https://images.unsplash.com/photo-1574323347407-f5e1ad6d020b?auto=format&fit=crop&w=600&q=80",
        recommended_treatment="Apply Chlorantraniliprole precision spray focused on maize whorls.",
        recommended_spray_volume_l_per_ha=400.0,
        latitude=36.7775,
        longitude=-119.4178
    )
    det3 = Detection(
        field_id=field1.id,
        crop_name="Roma Tomato",
        is_healthy=True,
        label="Healthy Leaf Tissue",
        confidence=0.98,
        severity="None",
        category="Healthy",
        image_url="https://images.unsplash.com/photo-1530836369250-ef72a3f5cda8?auto=format&fit=crop&w=600&q=80",
        recommended_treatment="No chemical application required.",
        recommended_spray_volume_l_per_ha=0.0,
        latitude=36.7788,
        longitude=-119.4180
    )
    db.add_all([det1, det2, det3])
    db.commit()

    print("Seeding Spray Logs...")
    spray1 = SprayLog(
        rover_id=rover.id,
        chemical_name="Copper Hydroxide Fungicide",
        volume_sprayed_liters=4.5,
        target_area_hectares=0.4,
        duration_seconds=120,
        latitude=36.7786,
        longitude=-119.4182
    )
    spray2 = SprayLog(
        rover_id=rover.id,
        chemical_name="Chlorantraniliprole Precision Insecticide",
        volume_sprayed_liters=6.0,
        target_area_hectares=0.6,
        duration_seconds=180,
        latitude=36.7775,
        longitude=-119.4178
    )
    db.add_all([spray1, spray2])
    db.commit()

    print("Seeding Support Tickets & Community Posts...")
    ticket = SupportTicket(
        user_id=farmer.id,
        subject="Calibration query for DC spray pump flow rate",
        category="Spraying System",
        status="OPEN",
        priority="Medium",
        description="Hi team, I would like to confirm the optimal solenoid valve pulse width for low-volume foliar spray on tomatoes."
    )
    post = CommunityPost(
        author_id=farmer.id,
        title="Best practices for early blight spot detection with 4WD rover",
        content="We ran our 4WD rover through lane 3 of Tomato Block A yesterday morning. The OpenRouter Vision AI picked up early blight on lower leaves before any visible symptoms were widespread!",
        tags="EarlyBlight,PrecisionSpraying,RoverTips",
        likes_count=14
    )
    db.add_all([ticket, post])
    db.commit()

    print("Seeding Agricultural Products Catalog...")
    p1 = Product(
        name="Organic Copper Hydroxide Fungicide 5L",
        category="Pesticide",
        price=45.0,
        description="High-purity liquid copper formulation for organic control of Early Blight and Bacterial Leaf Spot.",
        stock_quantity=30,
        image_url="https://images.unsplash.com/photo-1584308666744-24d5c474f2ae?auto=format&fit=crop&w=400&q=80"
    )
    p2 = Product(
        name="24V High-Torque Geared DC Motor (Rover Replacement)",
        category="Rover Part",
        price=89.0,
        description="Heavy-duty replacement motor with all-metal planetary gearbox for 4WD AgriRovers.",
        stock_quantity=12,
        image_url="https://images.unsplash.com/photo-1581092160607-ee22621dd758?auto=format&fit=crop&w=400&q=80"
    )
    p3 = Product(
        name="High-Pressure Solenoid Valve Unit 12V/24V",
        category="Rover Part",
        price=34.50,
        description="Fast-response brass solenoid valve rated for precise liquid chemical pulse spraying.",
        stock_quantity=25,
        image_url="https://images.unsplash.com/photo-1581092335397-9583fe92d232?auto=format&fit=crop&w=400&q=80"
    )
    db.add_all([p1, p2, p3])
    db.commit()

    print("Database seeding completed for agtech_backend!")
    db.close()

if __name__ == "__main__":
    seed_database()
