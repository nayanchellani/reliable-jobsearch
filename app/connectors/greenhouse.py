"""Greenhouse boards API connector.

Docs: https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

import httpx
from app.connectors.base import Connector, ConnectorError, normalize_job_type
from app.schemas.job import Job

GREENHOUSE_API_BASE = "https://boards-api.greenhouse.io/v1"


class GreenhouseConnector(Connector):
    """Connector for Greenhouse job boards API."""

    name = "greenhouse"

    def __init__(self, tokens: str = "stripe,airbnb,figma", rate_limit_ms: int = 1000):
        # Support comma-separated list of board tokens
        self.tokens = [t.strip() for t in tokens.split(",") if t.strip()]
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
        """Fetch jobs from Greenhouse boards API for all configured tokens."""
        all_jobs: List[Job] = []

        for token in self.tokens:
            await self._rate_limit()

            url = f"{GREENHOUSE_API_BASE}/boards/{token}/jobs"
            params = {"content": "true"}

            if location:
                params["location"] = location

            try:
                resp = await self.client.get(url, params=params)
                resp.raise_for_status()
                data = resp.json()

                for j in data.get("jobs", []):
                    job = self._parse_greenhouse_job(j)
                    if job:
                        all_jobs.append(job)

                self._success_count = getattr(self, "_success_count", 0) + 1

            except httpx.HTTPError as e:
                self._error_count = getattr(self, "_error_count", 0) + 1
                self._last_error = f"Greenhouse ({token}): {e}"
            finally:
                self._rate_limit_last = time.time()

        if not all_jobs and getattr(self, "_last_error", None):
            raise ConnectorError(self._last_error)

        return all_jobs

    def _parse_greenhouse_job(self, data: dict, token: str = "") -> Optional[Job]:
        """Parse a Greenhouse job dict into a Job model."""
        try:
            apply_url = data.get("absolute_url") or data.get("absolute_application_url", "")
            canonical = self._canonicalise_url(apply_url)

            posted_at = None
            raw_date = data.get("first_published") or data.get("updated_at") or data.get("posted_at")
            if raw_date:
                try:
                    posted_at = datetime.fromisoformat(raw_date.replace("Z", "+00:00"))
                except (ValueError, TypeError):
                    pass

            loc_obj = data.get("location") or {}
            location = loc_obj.get("name", "") if isinstance(loc_obj, dict) else str(loc_obj)
            company = data.get("company_name") or data.get("name") or token.capitalize()
            remote = "remote" in location.lower() or bool(data.get("remote", False))

            job = Job(
                title=data.get("title", ""),
                company=company,
                location=location,
                remote=remote,
                job_type=normalize_job_type(data.get("employment_type") or ""),
                experience_level="mid",
                salary=data.get("salary"),
                description=data.get("content", ""),
                posted_at=posted_at,
                first_seen_at=datetime.now(timezone.utc),
                source=self.name,
                apply_url=apply_url,
                canonical_url=canonical,
                status="active",
                raw=data,
            )
            return job
        except Exception:
            return None