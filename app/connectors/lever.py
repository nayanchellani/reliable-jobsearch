"""Lever API connector.

Docs: https://api.lever.co/v0/postings/{company}?mode=json
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

import httpx
from app.connectors.base import Connector, ConnectorError, normalize_job_type
from app.schemas.job import Job

LEVER_API_BASE = "https://api.lever.co/v0"


class LeverConnector(Connector):
    """Connector for Lever hiring API."""

    name = "lever"

    def __init__(self, companies: str = "spotify,coupa,aircall", rate_limit_ms: int = 1000):
        # Support comma-separated list of companies
        self.companies = [c.strip() for c in companies.split(",") if c.strip()]
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
        """Fetch jobs from Lever API for all configured companies."""
        all_jobs: List[Job] = []

        for company in self.companies:
            await self._rate_limit()

            url = f"{LEVER_API_BASE}/postings/{company}"
            params = {"mode": "json"}

            try:
                resp = await self.client.get(url, params=params)
                resp.raise_for_status()
                data = resp.json()

                for j in data if isinstance(data, list) else [data]:
                    job = self._parse_lever_job(j, company)
                    if job:
                        all_jobs.append(job)

                self._success_count = getattr(self, "_success_count", 0) + 1

            except httpx.HTTPError as e:
                self._error_count = getattr(self, "_error_count", 0) + 1
                self._last_error = f"Lever ({company}): {e}"
            finally:
                self._rate_limit_last = time.time()

        if not all_jobs and getattr(self, "_last_error", None):
            raise ConnectorError(self._last_error)

        return all_jobs

    def _parse_lever_job(self, data: dict, company_slug: str = "") -> Optional[Job]:
        """Parse a Lever job dict into a Job model."""
        try:
            apply_url = data.get("applyUrl") or data.get("hostedUrl", "")
            canonical = self._canonicalise_url(apply_url)

            title = data.get("text") or data.get("title", "")
            company = data.get("company") or company_slug.capitalize()
            cats = data.get("categories") or {}
            location = cats.get("location") or data.get("location", "")
            remote = data.get("workplaceType") == "remote" or "remote" in location.lower()
            job_type = normalize_job_type(cats.get("commitment") or cats.get("type") or "")

            posted_at = None
            if data.get("createdAt"):
                try:
                    posted_at = datetime.fromtimestamp(data["createdAt"] / 1000.0, tz=timezone.utc)
                except (ValueError, TypeError):
                    pass

            job = Job(
                title=title,
                company=company,
                location=location,
                remote=remote,
                job_type=job_type,
                experience_level="mid",
                salary=data.get("salary"),
                description=data.get("descriptionPlain") or data.get("description", ""),
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