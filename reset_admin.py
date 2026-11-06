import sys
sys.path.insert(0, ".")
from core.database import SessionLocal
from core.security import get_password_hash
from models import User, UserRole

db = SessionLocal()
admin = db.query(User).filter(User.role == UserRole.ADMIN).first()
if admin:
    admin.email = "admin@agritech.com"
    admin.hashed_password = get_password_hash("Admin@123456")
    db.commit()
    print("Admin password reset to Admin@123456")
else:
    admin = User(email="admin@agritech.com", hashed_password=get_password_hash("Admin@123456"), full_name="Admin", role=UserRole.ADMIN, is_active=True, must_change_password=False)
    db.add(admin)
    db.commit()
    print("Admin created with Admin@123456")
