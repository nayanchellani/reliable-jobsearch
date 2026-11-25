"""Pydantic models for job data and search filters."""

from __future__ import annotations

from datetime import datetime, date
from typing import List, Optional, Literal
from pydantic import BaseModel, Field, validator


class Job(BaseModel):
    """Core job model matching the DB schema."""

    id: Optional[int] = Field(default=None, description="DB primary key")
    title: str = Field(..., max_length=200, description="Job title")
    company: str = Field(..., max_length=200, description="Company name")
    location: str = Field(..., max_length=200, description="Job location")
    remote: bool = Field(default=False, description="Whether the role is remote")
    job_type: Literal["full_time", "part_time", "contract", "internship"] = Field(
        default="full_time", description="Employment type"
    )
    experience_level: Literal[
        "entry", "junior", "mid", "senior", "lead", "principal", "director"
    ] = Field(default="mid", description="Experience level required")
    salary: Optional[str] = Field(default=None, max_length=100, description="Salary range")
    description: Optional[str] = Field(default=None, description="Full job description")
    posted_at: Optional[datetime] = Field(
        default=None, description="When the job was posted"
    )
    first_seen_at: Optional[datetime] = Field(
        default=None, description="When first seen by the system"
    )
    source: str = Field(..., max_length=100, description="Source identifier (ats, aggregator, linkedin, naukri)")
    apply_url: str = Field(..., max_length=500, description="Apply URL")
    canonical_url: str = Field(
        ..., max_length=500, description="Dedup canonical URL"
    )
    status: Literal["active", "closed", "archived"] = Field(
        default="active", description="Job status"
    )
    raw: Optional[dict] = Field(
        default=None, description="Raw source data for debugging"
    )

    model_config = {"protected_namespaces": ()}

    @validator("salary", pre=True, always=True)
    def normalize_salary(cls, v):
        if v is None:
            return None
        return str(v).strip()

    @validator("status", always=True)
    def default_status(cls, v):
        if v is None:
            return "active"
        return v

    def model_dump_sql(self) -> dict:
        """Convert to dict for SQLAlchemy model insertion."""
        return {
            "id": self.id,
            "title": self.title,
            "company": self.company,
            "location": self.location,
            "remote": self.remote,
            "job_type": self.job_type,
            "experience_level": self.experience_level,
            "salary": self.salary,
            "description": self.description,
            "posted_at": self.posted_at,
            "first_seen_at": self.first_seen_at,
            "source": self.source,
            "apply_url": self.apply_url,
            "canonical_url": self.canonical_url,
            "status": self.status,
            "raw": self.raw,
        }


class JobSearchFilters(BaseModel):
    """Filter parameters for job search API."""

    # Text filters
    query: Optional[str] = Field(
        default=None, description="Free text search against title/company"
    )
    location: Optional[str] = Field(
        default=None, description="City/region filter"
    )
    remote: Optional[bool] = Field(
        default=None, description="Filter by remote eligibility"
    )
    source: Optional[str] = Field(
        default=None, description="Filter by source identifier"
    )

    # Type filters
    job_type: Optional[Literal["full_time", "part_time", "contract", "internship"]] = Field(
        default=None, description="Employment type filter"
    )
    experience_level: Optional[
        Literal["entry", "junior", "mid", "senior", "lead", "principal", "director"]
    ] = Field(default=None, description="Experience level filter")

    # Sorting
    sort: Literal["posted_at_desc", "posted_at_asc", "title_asc", "title_desc"] = Field(
        default="posted_at_desc", description="Sort order"
    )

    # Date range
    date_from: Optional[date] = Field(
        default=None, description="Earliest posted_at (inclusive)"
    )
    date_to: Optional[date] = Field(
        default=None, description="Latest posted_at (inclusive)"
    )

    # Pagination
    page: int = Field(default=1, ge=1, description="Page number")
    per_page: int = Field(default=20, ge=1, le=100, description="Items per page")


class ConnectorHealth(BaseModel):
    """Health status for a connector."""

    name: str = Field(..., description="Connector name")
    last_success: Optional[datetime] = Field(
        default=None, description="Last successful fetch timestamp"
    )
    last_error: Optional[str] = Field(default=None, description="Last error message")
    error_count: int = Field(default=0, description="Total error count")
    success_count: int = Field(default=0, description="Total success count")
    avg_latency_ms: float = Field(
        default=0.0, description="Average fetch latency in ms"
    )
    is_healthy: bool = Field(default=True, description="Whether connector is healthy")