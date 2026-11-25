"""Greenhouse boards API connector.

Docs: https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true
"""

from __future__ import annotations

import asyncio
import time
from typing import List, Dict, Any, Optional

import httpx
from app.connectors.base import Connector
from app.schemas.job import Job

GREENHOUSE_API_BASE = "https://boards-api.greenhouse.io/v1"


class GreenhouseConnector(Connector):
    """Connector for Greenhouse job boards API."""

    name = "greenhouse"

    def __init__(self, token: str, rate_limit_ms: int = 1000):
        self.token = token
        self.rate_limit_ms = rate_limit_ms
        self.client = httpx.AsyncClient(timeout=30.0)

    def health(self) -> ConnectorHealth:
        return ConnectorHealth(
            name=self.name,
            is_healthy=True,
            success_count=getattr(self, "_success_count", 0),
            error_count=getattr(self, "_error_count", 0),
        )

    async def fetch(
        self,
        query: str,
        location: Optional[str] = None,
        filters: Optional[JobSearchFilters] = None,
    ) -> List[Job]:
        """Fetch jobs from Greenhouse boards API."""
        await self._rate_limit()

        url = f"{GREENHOUSE_API_BASE}/boards/{self.token}/jobs"
        params = {"content": "true"}

        if location:
            params["location"] = location

        try:
            resp = await self.client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()

            jobs = []
            for j in data.get("jobs", []):
                job = self._parse_greenhouse_job(j)
                if job:
                    jobs.append(job)

            self._success_count = getattr(self, "_success_count", 0) + 1
            return jobs

        except httpx.HTTPError as e:
            self._error_count = getattr(self, "_error_count", 0) + 1
            return []
        finally:
            self._rate_limit_last = time.time()

    def _parse_greenhouse_job(self, data: dict) -> Optional[Job]:
        """Parse a Greenhouse job dict into a Job model."""
        try:
            # Extract canonical URL and apply URL
            apply_url = data.get("absolute_application_url", "")
            canonical = self._canonicalise_url(apply_url)

            # Parse posted_at from ISO string
            posted_at = None
            if data.get("posted_at"):
                try:
                    from datetime import datetime, timezone
                    posted_at = datetime.fromisoformat(
                        data["posted_at"].replace("Z", "+00:00")
                    )
                except (ValueError, TypeError):
                    pass

            # Parse experience level from title or levels dict
            experience_level = data.get("experience_levels", ["mid"])[0] if data.get("experience_levels") else "mid"

            job = Job(
                title=data.get("title", ""),
                company=data.get("name", ""),
                location=data.get("location", {}).get("city", ""),
                remote=bool(data.get("remote", False)),
                job_type=data.get("employment_type", "full_time"),
                experience_level=experience_level,
                salary=data.get("salary"),  # May be None
                description=data.get("content", ""),
                posted_at=posted_at,
                first_seen_at=datetime.utcnow(),
                source=self.name,
                apply_url=apply_url,
                canonical_url=canonical,
                status="active",
                raw=data,
            )
            return job
        except Exception:
            return None