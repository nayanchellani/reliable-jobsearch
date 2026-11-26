"""Adzuna API connector.

Docs: https://developer.adzuna.com/docs/api
"""

from __future__ import annotations

import time
from typing import List, Dict, Any, Optional

import httpx
from app.connectors.base import Connector
from app.schemas.job import Job


class AdzunaConnector(Connector):
    """Connector for Adzuna API."""

    name = "adzuna"

    def __init__(self, app_id: str, api_key: str, rate_limit_ms: int = 1000):
        self.app_id = app_id
        self.api_key = api_key
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

        url = "https://api.adzuna.com/v1/api/jobs/in/search/1"
        params = {
            "app_id": self.app_id,
            "app_key": self.api_key,
            "what": query,
            "results_per_page": 20,
        }
        if location:
            params["where"] = location

        try:
            resp = await self.client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()

            jobs = []
            for j in data.get("results", []):
                job = self._parse_adzuna_job(j)
                if job:
                    jobs.append(job)

            self._success_count = getattr(self, "_success_count", 0) + 1
            return jobs

        except httpx.HTTPError as e:
            self._error_count = getattr(self, "_error_count", 0) + 1
            return []

    def _parse_adzuna_job(self, data: dict) -> Optional[Job]:
        try:
            apply_url = data.get("redirect_url", "")
            canonical = self._canonicalise_url(apply_url)

            location_raw = data.get("location", {}).get("display_name", "")
            location = location_raw.split(",")[0] if location_raw else ""

            salary = data.get("salary_min") or data.get("salary_max")
            salary_str = None
            if salary:
                salary_str = f"{data.get('salary_min', 0)}-{data.get('salary_max', 0)} {data.get('salary_is_predicted', '')}"

            job = Job(
                title=data.get("title", ""),
                company=data.get("company", {}).get("display_name", ""),
                location=location,
                remote=False,
                job_type=data.get("contract_type", "full_time"),
                experience_level="mid",
                salary=salary_str,
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