"""Ashby connector.

Docs: https://api.ashbyhq.com/posting-api/job-board/{name}
"""

from __future__ import annotations

import asyncio
import time
from typing import List, Dict, Any, Optional

import httpx
from app.connectors.base import Connector, ConnectorError
from app.schemas.job import Job

ASHBY_API_BASE = "https://api.ashbyhq.com"


class AshbyConnector(Connector):
    """Connector for Ashby job board API."""

    name = "ashby"

    def __init__(self, board_name: str = "linear,vanta,ramp", rate_limit_ms: int = 1000):
        self.board_names = [b.strip() for b in board_name.split(",") if b.strip()]
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
        """Fetch jobs from Ashby API across configured boards."""
        all_jobs: List[Job] = []
        self._last_error: Optional[str] = None

        for board in self.board_names:
            await self._rate_limit()
            url = f"https://api.ashbyhq.com/posting-api/job-board/{board}"

            try:
                resp = await self.client.get(url)
                resp.raise_for_status()
                data = resp.json()

                for j in data.get("jobs", []) if isinstance(data, dict) else []:
                    job = self._parse_ashby_job(j)
                    if job:
                        all_jobs.append(job)

                self._success_count = getattr(self, "_success_count", 0) + 1
            except httpx.HTTPError as e:
                self._error_count = getattr(self, "_error_count", 0) + 1
                self._last_error = f"Ashby ({board}): {e}"
            finally:
                self._rate_limit_last = time.time()

        if not all_jobs and self._last_error:
            raise ConnectorError(self._last_error)

        return all_jobs

    def _parse_ashby_job(self, data: dict) -> Optional[Job]:
        """Parse an Ashby job dict into a Job model."""
        try:
            apply_url = data.get("applyUrl", "")
            canonical = self._canonicalise_url(apply_url)

            title = data.get("title", "")
            company = data.get("company", "")
            location_raw = data.get("location", "")
            location = location_raw.split(",")[0] if location_raw else ""

            # Ashby experience level
            experience_level = data.get("experienceLevel", "mid")

            job_type = data.get("employmentType", "full_time")

            posted_at = None
            if data.get("postedDate"):
                try:
                    from datetime import datetime, timezone
                    posted_at = datetime.fromisoformat(data["postedDate"])
                except (ValueError, TypeError):
                    pass

            job = Job(
                title=title,
                company=company,
                location=location,
                remote=data.get("isRemote", False),
                job_type=job_type,
                experience_level=experience_level,
                salary=data.get("salary"),
                description=data.get("description", ""),
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