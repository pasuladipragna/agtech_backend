"""
Smart AgriTech Rover — Core Security Module
Real JWT authentication with bcrypt password hashing.
Role-based access control enforced at the API level.
No demo mode. No hardcoded credentials.
"""

import secrets
import string
from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from core.config import settings
from core.database import get_db

# ── Password hashing ──────────────────────────────────────────
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ── JWT Bearer ────────────────────────────────────────────────
bearer_scheme = HTTPBearer(auto_error=False)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def generate_temp_password(length: int = 12) -> str:
    """Generate a secure temporary password for farmer activation."""
    alphabet = string.ascii_letters + string.digits + "!@#$%"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def generate_activation_token() -> str:
    """Generate a secure URL-safe activation token."""
    return secrets.token_urlsafe(48)


# ── JWT Token creation ────────────────────────────────────────

def create_access_token(
    subject: str,
    role: str,
    user_id: str,
    must_change_password: bool = False,
    expires_delta: Optional[timedelta] = None
) -> str:
    expire = datetime.utcnow() + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    payload = {
        "sub": subject,              # email
        "uid": user_id,
        "role": role,
        "mcp": must_change_password, # must change password flag
        "exp": expire,
        "iat": datetime.utcnow(),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")


def decode_access_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        return payload
    except JWTError:
        return None


# ── Current User Resolution ───────────────────────────────────

def get_current_user_from_token(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: Session = Depends(get_db)
):
    """
    Resolves the current authenticated user from Bearer JWT.
    Raises 401 if token is missing or invalid.
    """
    from models import User

    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please log in.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_access_token(credentials.credentials)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Your session has expired. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id: str = payload.get("uid")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token.")

    user = db.query(User).filter(User.id == user_id, User.is_active == True).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account not found or has been deactivated."
        )

    return user


def require_admin(current_user=Depends(get_current_user_from_token)):
    """Dependency — requires admin role. Returns user if admin, raises 403 otherwise."""
    if not current_user.is_admin():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required."
        )
    return current_user


def require_farmer(current_user=Depends(get_current_user_from_token)):
    """Dependency — requires farmer role. Returns user if farmer."""
    if not current_user.is_farmer():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Farmer access required."
        )
    return current_user


# ── Farmer Ownership Checks ───────────────────────────────────

def verify_farm_ownership(farm, current_user) -> None:
    """
    Verifies the current farmer owns the given farm.
    Raises 403 if not. This is critical — farmers must never
    access another farmer's data by manipulating IDs.
    """
    if current_user.is_admin():
        return  # Admin has access to all

    if not current_user.farmer_profile:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied.")

    if farm.farmer_id != current_user.farmer_profile.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this resource."
        )


def verify_field_ownership(field, current_user, db: Session) -> None:
    """Verify farmer owns the field (via farm ownership)."""
    if current_user.is_admin():
        return
    from models import Farm
    farm = db.query(Farm).filter(Farm.id == field.farm_id).first()
    if not farm:
        raise HTTPException(status_code=404, detail="Farm not found.")
    verify_farm_ownership(farm, current_user)
