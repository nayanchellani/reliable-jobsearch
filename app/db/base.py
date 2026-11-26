"""SQLAlchemy base models for the job aggregator."""

import os
import json
from datetime import datetime, date, timezone
from pathlib import Path
from sqlalchemy import (
    Column,
    Integer,
    String,
    Boolean,
    DateTime,
    Text,
    Float,
    Date,
    Index,
    func,
    create_engine,
    JSON,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

# Load .env from project root
# Load .env from repo root and current working dir
load_dotenv(Path(__file__).resolve().parents[2] / ".env")
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data/jobs.db")
if DATABASE_URL.startswith("sqlite:///./"):
    Path(DATABASE_URL[len("sqlite:///./") :]).parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False}
    if DATABASE_URL.startswith("sqlite")
    else {},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


class User(Base):
    """User authentication table."""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )


class Session(Base):
    """Session storage for JWT tokens."""

    __tablename__ = "sessions"

    id = Column(Integer, primary_key=True, index=True)
    token = Column(String(255), unique=True, index=True, nullable=False)
    user_id = Column(Integer, nullable=False, index=True)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)


class Job(Base):
    """SQLAlchemy model for jobs table, mirroring the pydantic Job schema."""

    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), nullable=False, index=True)
    company = Column(String(200), nullable=False, index=True)
    location = Column(String(200), nullable=False, index=True)
    remote = Column(Boolean, default=False, nullable=False)
    job_type = Column(String(50), nullable=False, default="full_time")
    experience_level = Column(String(50), nullable=False, default="mid")
    salary = Column(String(100), nullable=True)
    description = Column(Text, nullable=True)
    posted_at = Column(DateTime(timezone=True), nullable=True)
    first_seen_at = Column(DateTime(timezone=True), nullable=True)
    source = Column(String(100), nullable=False, index=True)
    apply_url = Column(String(500), nullable=False)
    canonical_url = Column(String(500), nullable=False, unique=True, index=True)
    status = Column(String(20), nullable=False, default="active")
    raw = Column(JSON, nullable=True)  # JSON column for raw source data
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_jobs_source_status", "source", "status"),
        Index("ix_jobs_canonical_url", "canonical_url"),
        Index("ix_jobs_posted_at", "posted_at"),
    )


class UserSettings(Base):
    """User settings stored in DB."""

    __tablename__ = "user_settings"

    id = Column(Integer, primary_key=True, index=True)
    setting_key = Column(String(100), unique=True, nullable=False, index=True)
    setting_value = Column(Text, nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class ConnectorSyncRun(Base):
    """Persisted connector sync run for async status/polling."""

    __tablename__ = "connector_sync_runs"

    id = Column(Integer, primary_key=True, index=True)
    sync_id = Column(String(64), unique=True, nullable=False, index=True)
    status = Column(String(32), nullable=False, default="pending", index=True)  # pending|running|completed|partially_completed|failed|cancelled
    query = Column(String(500), nullable=True)
    location = Column(String(200), nullable=True)
    requested_by = Column(String(255), nullable=True)
    total_new = Column(Integer, default=0, nullable=False)
    results_json = Column(JSON, nullable=True)
    error = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)