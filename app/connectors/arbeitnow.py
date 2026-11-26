"""Arbeitnow API connector.

Docs: https://www.arbeitnow.com/api
"""

from __future__ import annotations

import time
from typing import List, Dict, Any, Optional

import httpx
from app.connectors.base import Connector
from app.schemas.job import Job


class ArbeitnowConnector(Connector):
    """Connector for Arbeitnow API."""

    name = "arbeitnow"

    def __init__(self, rate_limit_ms: int = 1000):
        self.rate_limit_ms = rate_limit_ms
        self.client = httpx.AsyncClient(timeout=30.0)

    def health(self):
        from app.schemas.job import ConnectorHealth
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
        filters: Optional[Any] = None,
    ) -> List[Job]:
        await self._rate_limit()

        url = "https://www.arbeitnow.com/api/job-board-api"
        params = {}
        if query:
            params["search"] = query

        try:
            resp = await self.client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()

            jobs = []
            for j in data.get("data", []):
                job = self._parse_arbeitnow_job(j)
                if job:
                    jobs.append(job)

            self._success_count = getattr(self, "_success_count", 0) + 1
            return jobs

        except httpx.HTTPError as e:
            self._error_count = getattr(self, "_error_count", 0) + 1
            return []

    def _parse_arbeitnow_job(self, data: dict) -> Optional[Job]:
        try:
            apply_url = data.get("url", "")
            canonical = self._canonicalise_url(apply_url)

            location = data.get("location", "")

            job = Job(
                title=data.get("title", ""),
                company=data.get("company_name", ""),
                location=location,
                remote=data.get("remote", False),
                job_type=data.get("job_type", "full_time").lower().replace("-", "_"),
                experience_level="mid",
                salary=data.get("salary"),
                description=data.get("description", ""),
                posted_at=None,
                first_seen_at=None,
                source=self.name,
                apply_url=apply_url,
                canonical_url=canonical,
                status="active",
                raw=data,
            )
            return job
        except Exception:
            return None

    def _rate_limit(self) -> None:
        now = time.time()
        elapsed = now - self._rate_limit_last
        if elapsed < self.rate_limit_ms / 1000.0:
            time.sleep(self.rate_limit_ms / 1000.0 - elapsed)
        self._rate_limit_last = time.time()