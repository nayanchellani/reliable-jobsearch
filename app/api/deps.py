"""Dependency injection for FastAPI app."""

from __future__ import annotations

from typing import Optional
from app.schemas.job import JobSearchFilters


def get_filters(
    query: Optional[str] = None,
    location: Optional[str] = None,
    job_type: Optional[str] = None,
    experience_level: Optional[str] = None,
    remote: Optional[bool] = None,
    source: Optional[str] = None,
    sort: str = "posted_at_desc",
    page: int = 1,
    per_page: int = 20,
) -> JobSearchFilters:
    """Create JobSearchFilters from API query parameters."""
    return JobSearchFilters(
        query=query,
        location=location,
        job_type=job_type,
        experience_level=experience_level,
        remote=remote,
        source=source,
        sort=sort,
        page=page,
        per_page=per_page,
    )