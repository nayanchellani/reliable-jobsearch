"""Authentication and settings API endpoints."""

from __future__ import annotations

import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Header, Response, Cookie
from pydantic import BaseModel, Field
from sqlalchemy import Column, Integer, String, DateTime, Text, func
from sqlalchemy.orm import Session

from app.db.base import SessionLocal, Base, User, Session as SessionModel, UserSettings
from passlib.context import CryptContext
import jwt

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT settings
JWT_SECRET = os.getenv("JWT_SECRET", "your-super-secret-change-in-production")
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_DAYS = 30


class AuthRequest(BaseModel):
    email: str = Field(...)
    password: str = Field(..., min_length=1)


class RegisterRequest(BaseModel):
    email: str = Field(...)
    password: str = Field(..., min_length=1)
    confirm_password: str = Field(..., min_length=1)


class AuthResponse(BaseModel):
    token: str
    expires_at: datetime


class SettingsResponse(BaseModel):
    # LLM
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = "auto"

    # ATS tokens
    greenhouse_token: str = ""
    lever_company: str = ""
    ashby_name: str = ""

    # Aggregator API keys
    adzuna_app_id: str = ""
    adzuna_api_key: str = ""
    jooble_api_key: str = ""
    jsearch_api_key: str = ""

    # Feature flags
    enable_linkedin_scraping: bool = False
    enable_naukri_scraping: bool = False
    enable_guest_scraping: bool = False

    # Email/IMAP
    imap_server: str = ""
    imap_port: int = 993
    imap_user: str = ""
    imap_password: str = ""


router = APIRouter(prefix="/auth", tags=["auth"])


def create_jwt_token(user_id: int, email: str) -> str:
    """Create JWT token for user."""
    now = datetime.now(timezone.utc)
    expires = now + timedelta(days=JWT_EXPIRATION_DAYS)
    payload = {
        "sub": str(user_id),
        "email": email,
        "iat": now,
        "exp": expires,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_jwt_token(token: str) -> dict:
    """Decode and validate JWT token."""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


async def get_current_user(
    authorization: Optional[str] = Header(None),
    auth_token: Optional[str] = Cookie(None)
) -> dict:
    """Get current user from JWT token."""
    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ")[1]
    elif auth_token:
        token = auth_token

    if not token:
        raise HTTPException(status_code=401, detail="Missing token")

    payload = decode_jwt_token(token)
    return payload


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("/register", response_model=AuthResponse)
async def register(request: RegisterRequest, response: Response, db: Session = Depends(get_db)):
    """Register a new user."""
    try:
        # Check if user already exists
        existing = db.query(User).filter(User.email == request.email).first()
        if existing:
            raise HTTPException(status_code=400, detail="User already registered")

        if request.password != request.confirm_password:
            raise HTTPException(status_code=400, detail="Passwords do not match")

        password_hash = pwd_context.hash(request.password)
        user = User(email=request.email, password_hash=password_hash)
        db.add(user)
        db.commit()
        db.refresh(user)

        # Create JWT token
        token = create_jwt_token(user.id, user.email)
        expires = datetime.now(timezone.utc) + timedelta(days=JWT_EXPIRATION_DAYS)

        response.set_cookie(key="auth_token", value=token, httponly=True, secure=True, samesite="lax", max_age=JWT_EXPIRATION_DAYS*24*3600)

        return AuthResponse(token=token, expires_at=expires)
    finally:
        db.close()


@router.post("/login", response_model=AuthResponse)
async def login(request: AuthRequest, response: Response, db: Session = Depends(get_db)):
    """Login with existing password."""
    try:
        user = db.query(User).filter(User.email == request.email).first()

        if not user:
            raise HTTPException(status_code=401, detail="Invalid credentials")

        if not pwd_context.verify(request.password, user.password_hash):
            raise HTTPException(status_code=401, detail="Invalid credentials")

        # Create JWT token
        token = create_jwt_token(user.id, user.email)
        expires = datetime.now(timezone.utc) + timedelta(days=JWT_EXPIRATION_DAYS)

        response.set_cookie(key="auth_token", value=token, httponly=True, secure=True, samesite="lax", max_age=30*24*3600)

        return AuthResponse(token=token, expires_at=expires)
    finally:
        db.close()


@router.post("/logout")
async def logout(response: Response):
    """Logout - just clear cookie (JWT is stateless)."""
    response.delete_cookie("auth_token")
    return {"message": "Logged out"}


@router.get("/me")
async def me(user: dict = Depends(get_current_user)):
    """Check auth status."""
    return {"authenticated": True, "user_id": user.get("sub"), "email": user.get("email")}


# Settings router
settings_router = APIRouter(prefix="/settings", tags=["settings"])


@settings_router.get("", response_model=SettingsResponse)
async def get_settings(user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    """Get all settings (without secrets)."""
    try:
        settings = db.query(UserSettings).all()
        settings_dict = {s.setting_key: s.setting_value for s in settings}

        # Return settings but mask sensitive values
        return SettingsResponse(
            llm_base_url=settings_dict.get("llm_base_url", ""),
            llm_api_key="***" if settings_dict.get("llm_api_key") else "",
            llm_model=settings_dict.get("llm_model", "auto"),
            greenhouse_token="***" if settings_dict.get("greenhouse_token") else "",
            lever_company="***" if settings_dict.get("lever_company") else "",
            ashby_name="***" if settings_dict.get("ashby_name") else "",
            adzuna_app_id="***" if settings_dict.get("adzuna_app_id") else "",
            adzuna_api_key="***" if settings_dict.get("adzuna_api_key") else "",
            jooble_api_key="***" if settings_dict.get("jooble_api_key") else "",
            jsearch_api_key="***" if settings_dict.get("jsearch_api_key") else "",
            enable_linkedin_scraping=settings_dict.get("enable_linkedin_scraping", "false") == "true",
            enable_naukri_scraping=settings_dict.get("enable_naukri_scraping", "false") == "true",
            enable_guest_scraping=settings_dict.get("enable_guest_scraping", "false") == "true",
            imap_server=settings_dict.get("imap_server", ""),
            imap_port=int(settings_dict.get("imap_port", "993")),
            imap_user="***" if settings_dict.get("imap_user") else "",
            imap_password="***" if settings_dict.get("imap_password") else "",
        )
    finally:
        db.close()


@settings_router.put("", response_model=SettingsResponse)
async def update_settings(
    settings: SettingsResponse,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update settings."""
    settings_dict = settings.model_dump()

    for key, value in settings_dict.items():
        if value == "***":  # Don't update masked values
            continue
        if isinstance(value, bool):
            value = str(value).lower()
        elif isinstance(value, int):
            value = str(value)
        existing = db.query(UserSettings).filter(UserSettings.setting_key == key).first()
        if existing:
            existing.setting_value = value
        else:
            db.add(UserSettings(setting_key=key, setting_value=value))

    db.commit()
    return settings