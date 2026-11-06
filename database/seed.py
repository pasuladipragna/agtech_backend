import os

from sqlalchemy.orm import Session

from core.database import Base, SessionLocal, engine
from core.security import get_password_hash
from models import Crop, Farm, FarmerProfile, Field, Product, RoverDevice, User, UserRole


def _get_or_create_user(
    db: Session,
    email: str,
    full_name: str,
    role: str,
    password: str,
    username: str,
) -> User:
    user = db.query(User).filter(User.email == email).first()
    if user:
        return user

    user = User(
        email=email,
        username=username,
        hashed_password=get_password_hash(password),
        full_name=full_name,
        role=role,
        is_active=True,
        must_change_password=False,
    )
    db.add(user)
    db.flush()
    return user


def seed_database() -> None:
    admin_password = os.getenv("SEED_ADMIN_PASSWORD")
    farmer_password = os.getenv("SEED_FARMER_PASSWORD")
    if not admin_password or not farmer_password:
        raise RuntimeError(
            "Set SEED_ADMIN_PASSWORD and SEED_FARMER_PASSWORD before seeding."
        )

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        admin = _get_or_create_user(
            db,
            os.getenv("SEED_ADMIN_EMAIL", "admin@agritech.com"),
            "AgriTech Administrator",
            UserRole.ADMIN,
            admin_password,
            "admin",
        )
        farmer = _get_or_create_user(
            db,
            os.getenv("SEED_FARMER_EMAIL", "farmer@agritech.com"),
            "Demo Farmer",
            UserRole.FARMER,
            farmer_password,
            "demo-farmer",
        )

        profile = db.query(FarmerProfile).filter(FarmerProfile.user_id == farmer.id).first()
        if not profile:
            profile = FarmerProfile(user_id=farmer.id)
            db.add(profile)
            db.flush()

        farm = db.query(Farm).filter(Farm.farmer_id == profile.id).first()
        if not farm:
            farm = Farm(
                farmer_id=profile.id,
                name="Demo Farm",
                location_name="Fresno, California",
                latitude=36.778259,
                longitude=-119.417931,
                total_area_hectares=18.5,
                main_crop_types="Tomato, Corn",
            )
            db.add(farm)
            db.flush()

        field = db.query(Field).filter(Field.farm_id == farm.id).first()
        if not field:
            field = Field(
                farm_id=farm.id,
                name="North Field",
                area_hectares=4.2,
                notes="Demo field",
            )
            db.add(field)
            db.flush()

        if not db.query(Crop).filter(Crop.field_id == field.id).first():
            db.add(
                Crop(
                    field_id=field.id,
                    name="Tomato",
                    variety="Roma",
                    growth_stage="Vegetative",
                    status="Monitoring",
                )
            )

        rover = db.query(RoverDevice).filter(RoverDevice.rover_id == "ROVER-DEMO-01").first()
        if not rover:
            db.add(
                RoverDevice(
                    rover_id="ROVER-DEMO-01",
                    name="Demo Rover",
                    description="Offline demo rover; connect hardware to enable commands.",
                )
            )

        if not db.query(Product).filter(Product.name == "Demo Crop Treatment").first():
            db.add(
                Product(
                    name="Demo Crop Treatment",
                    product_type="Pesticide",
                    target_crop="Tomato",
                    usage_instructions="Follow the product label and local regulations.",
                    safety_notes="Wear appropriate personal protective equipment.",
                    created_by=admin.id,
                )
            )

        db.commit()
        print("Database seeded without deleting existing records.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed_database()