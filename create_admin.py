"""
Smart AgriTech Rover — Admin Account Setup Script
Run this ONCE during initial deployment to create the single admin account.

Usage:
    python create_admin.py

The system enforces EXACTLY ONE admin account.
This script will refuse to run if an admin already exists.
Never expose this script through the public web interface.
"""

import sys
import getpass
import re
from sqlalchemy.orm import Session

# Add parent directory to path
sys.path.insert(0, ".")

from core.database import SessionLocal, engine, Base
from core.security import get_password_hash
from models import User, UserRole


def validate_email(email: str) -> bool:
    pattern = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
    return bool(re.match(pattern, email))


def validate_password(password: str) -> tuple[bool, str]:
    if len(password) < 10:
        return False, "Password must be at least 10 characters long."
    if not any(c.isupper() for c in password):
        return False, "Password must contain at least one uppercase letter."
    if not any(c.isdigit() for c in password):
        return False, "Password must contain at least one digit."
    return True, ""


def create_admin():
    # Ensure tables exist
    Base.metadata.create_all(bind=engine)

    db: Session = SessionLocal()
    try:
        # ── Check for existing admin ──────────────────────────────
        existing_admin = db.query(User).filter(User.role == UserRole.ADMIN).first()
        if existing_admin:
            print("\n❌ ERROR: An admin account already exists.")
            print(f"   Email: {existing_admin.email}")
            print("\nThe system enforces exactly ONE admin account.")
            print("To reset the admin, manually update the database.")
            sys.exit(1)

        print("\n" + "=" * 60)
        print("  Smart AgriTech Rover — Admin Account Setup")
        print("=" * 60)
        print("\nThis script creates the single administrator account.")
        print("This should only be run once during initial deployment.\n")

        # ── Collect credentials ───────────────────────────────────
        while True:
            full_name = input("Admin Full Name: ").strip()
            if full_name:
                break
            print("Full name is required.")

        while True:
            email = input("Admin Email: ").strip().lower()
            if validate_email(email):
                # Check if email already in use
                if db.query(User).filter(User.email == email).first():
                    print("That email is already registered. Choose a different one.")
                    continue
                break
            print("Please enter a valid email address.")

        while True:
            password = getpass.getpass("Admin Password (min 10 chars, 1 uppercase, 1 digit): ")
            valid, msg = validate_password(password)
            if not valid:
                print(f"  → {msg}")
                continue
            confirm = getpass.getpass("Confirm Password: ")
            if password != confirm:
                print("  → Passwords do not match. Try again.")
                continue
            break

        phone = input("Admin Phone (optional): ").strip() or None

        # ── Create admin user ─────────────────────────────────────
        admin_user = User(
            email=email,
            hashed_password=get_password_hash(password),
            full_name=full_name,
            phone=phone,
            role=UserRole.ADMIN,
            is_active=True,
            must_change_password=False,
        )
        db.add(admin_user)
        db.commit()
        db.refresh(admin_user)

        print("\n" + "=" * 60)
        print("  ✅ Admin account created successfully!")
        print("=" * 60)
        print(f"\n  ID:    {admin_user.id}")
        print(f"  Name:  {admin_user.full_name}")
        print(f"  Email: {admin_user.email}")
        print(f"  Role:  {admin_user.role}")
        print(f"\n  Admin login URL: /admin/login")
        print("\n⚠️  Keep these credentials secure. Do not share them.")
        print("=" * 60 + "\n")

    finally:
        db.close()


if __name__ == "__main__":
    create_admin()
