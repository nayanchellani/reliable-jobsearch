"""Abstract base class for all job connectors."""

from __future__ import annotations

import time
import json
import hashlib
from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, Dict, Any, Optional

from app.schemas.job import Job, JobSearchFilters, ConnectorHealth


class Connector(ABC):
    """Abstract base class for all job board connectors."""

    name: str = "base"
    rate_limit_ms: int = 1000
    _rate_limit_last: float = 0.0

    def __init__(self):
        self._rate_limit_last = 0.0

    @abstractmethod
    async def fetch(
        self,
        query: str,
        location: Optional[str] = None,
        filters: Optional[JobSearchFilters] = None,
    ) -> List[Job]:
        """Fetch jobs from the source.

        Args:
            query: Search query string (job title keywords)
            location: Location filter
            filters: Optional JobSearchFilters for additional filtering

        Returns:
            List of Job objects, empty list if no results or on error
        """
        raise NotImplementedError

    @abstractmethod
    def health(self) -> ConnectorHealth:
        """Return health status for this connector."""
        raise NotImplementedError

    async def _rate_limit(self) -> None:
        """Ensure we don't exceed the configured rate limit."""
        now = time.time()
        elapsed = now - self._rate_limit_last
        if elapsed < self.rate_limit_ms / 1000.0:
            sleep_time = self.rate_limit_ms / 1000.0 - elapsed
            time.sleep(sleep_time)
        self._rate_limit_last = time.time()

    def _canonicalise_url(self, url: str) -> str:
        """Strip tracking parameters from a URL to get the canonical form."""
        from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

        parsed = urlparse(url)
        # Remove common tracking params
        tracking_params = {
            "utm_source", "utm_medium", "utm_campaign", "utm_term",
            "utm_content", "gclid", "fbclid", "mc_campaign", "mc_id",
            "tracking", "refid", "trackingid", "trk", "midtoken",
        }
        qs = parse_qs(parsed.query)
        filtered_qs = {k: v for k, v in qs.items() if k.lower() not in tracking_params}
        # Rebuild URL without tracking params
        new_query = urlencode(filtered_qs, doseq=True) if filtered_qs else ""
        new_url = urlunparse(parsed._replace(query=new_query))
        return new_url

    def _make_job_from_raw(self, raw: dict, source: str) -> Job:
        """Normalise raw source data into a Job object."""
        from app.schemas.job import Job

        canonical_url = raw.get("apply_url") or raw.get(" canonical_url", "")
        canonical_url = self._canonicalise_url(canonical_url)

        return Job(
            title=raw.get("title", ""),
            company=raw.get("company", ""),
            location=raw.get("location", ""),
            remote=raw.get("remote", False),
            job_type=raw.get("job_type", "full_time"),
            experience_level=raw.get("experience_level", "mid"),
            salary=raw.get("salary"),
            description=raw.get("description"),
            posted_at=raw.get("posted_at"),
            first_seen_at=raw.get("first_seen_at") or datetime.utcnow(),
            source=source,
            apply_url=raw.get("apply_url", canonical_url),
            canonical_url=canonical_url,
            status=raw.get("status", "active"),
            raw=raw,
        )