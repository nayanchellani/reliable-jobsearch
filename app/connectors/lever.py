"""Lever API connector.

Docs: https://api.lever.co/v0/postings/{company}?mode=json
"""

from __future__ import annotations

import asyncio
import time
from typing import List, Dict, Any, Optional

import httpx
from app.connectors.base import Connector
from app.schemas.job import Job

LEVER_API_BASE = "https://api.lever.co/v0"


class LeverConnector(Connector):
    """Connector for Lever hiring API."""

    name = "lever"

    def __init__(self, company: str, rate_limit_ms: int = 1000):
        self.company = company
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
        """Fetch jobs from Lever API."""
        await self._rate_limit()

        # Lever uses: https://api.lever.co/v0/postings/{company}?mode=json
        # For specific posting: /v0/postings/{company}?mode=json&id={posting_id}
        # We'll search by company first
        url = f"{LEVER_API_BASE}/v0/postings/{self.company}"
        params = {"mode": "json"}

        if location:
            params["location"] = location

        try:
            resp = await self.client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()

            jobs = []
            for j in data if isinstance(data, list) else [data]:
                job = self._parse_lever_job(j)
                if job:
                    jobs.append(job)

            self._success_count = getattr(self, "_success_count", 0) + 1
            return jobs

        except httpx.HTTPError as e:
            self._error_count = getattr(self, "_error_count", 0) + 1
            return []
        finally:
            self._rate_limit_last = time.time()

    def _parse_lever_job(self, data: dict) -> Optional[Job]:
        """Parse a Lever job dict into a Job model."""
        try:
            apply_url = data.get("applyUrl", "")
            canonical = self._canonicalise_url(apply_url)

            # Lever uses different field names
            title = data.get("title", "")
            company = data.get("company", "")
            # Location may be formatted
            location_raw = data.get("location", "")
            # Parse city from formatted location
            location = location_raw.split(",")[0] if location_raw else ""

            # Experience level
            experience_level = data.get("tags", [{}])[0].get("display", "mid") if data.get("tags") else "mid"

            # Job type from lever
            job_type = data.get("categories", {}).get("type", "full_time")

            posted_at = None
            if data.get("publishedAt"):
                try:
                    from datetime import datetime, timezone
                    posted_at = datetime.fromisoformat(
                        data["publishedAt"].replace("Z", "+00:00")
                    )
                except (ValueError, TypeError):
                    pass

            job = Job(
                title=title,
                company=company,
                location=location,
                remote=False,  # Lever doesn't always expose remote flag clearly
                job_type=job_type,
                experience_level=experience_level,
                salary=data.get("salary"),  # May be None
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