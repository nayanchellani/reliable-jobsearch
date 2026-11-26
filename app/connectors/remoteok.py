"""RemoteOK API connector.

Docs: https://remoteok.com/api
"""

from __future__ import annotations

import time
from typing import List, Dict, Any, Optional

import httpx
from app.connectors.base import Connector
from app.schemas.job import Job


class RemoteOKConnector(Connector):
    """Connector for RemoteOK API."""

    name = "remoteok"

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

        url = "https://remoteok.com/api"
        params = {}

        try:
            resp = await self.client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()

            jobs = []
            for j in data[1:]:  # First item is metadata
                job = self._parse_remoteok_job(j)
                if job:
                    jobs.append(job)

            self._success_count = getattr(self, "_success_count", 0) + 1
            return jobs
        except Exception as e:
            self._error_count = getattr(self, "_error_count", 0) + 1
            self._last_error = str(e)
            print(f"RemoteOK fetch error: {e}")
            return []

    def _parse_remoteok_job(self, data: dict) -> Optional[Job]:
        try:
            apply_url = data.get("apply_url", "")
            canonical = self._canonicalise_url(apply_url)

            location = data.get("location", "Remote")

            job = Job(
                title=data.get("position", ""),
                company=data.get("company", ""),
                location=location,
                remote=True,
                job_type=data.get("contract", "full_time").lower().replace("-", "_"),
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

    # uses Connector._rate_limit()