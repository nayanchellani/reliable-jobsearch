"""JSearch (RapidAPI) connector.

Docs: https://rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch
"""

from __future__ import annotations

import time
from typing import List, Dict, Any, Optional

import httpx
from app.connectors.base import Connector
from app.schemas.job import Job


class JSearchConnector(Connector):
    """Connector for JSearch RapidAPI."""

    name = "jsearch"

    def __init__(self, api_key: str, rate_limit_ms: int = 1000):
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
        self._rate_limit()

        url = "https://jsearch.p.rapidapi.com/search"
        headers = {
            "X-RapidAPI-Key": self.api_key,
            "X-RapidAPI-Host": "jsearch.p.rapidapi.com",
        }
        params = {
            "query": query,
            "page": "1",
            "num_pages": "1",
        }
        if location:
            params["query"] = f"{query} {location}"

        try:
            resp = await self.client.get(url, headers=headers, params=params)
            resp.raise_for_status()
            data = resp.json()

            jobs = []
            for j in data.get("data", []):
                job = self._parse_jsearch_job(j)
                if job:
                    jobs.append(job)

            self._success_count = getattr(self, "_success_count", 0) + 1
            return jobs

        except httpx.HTTPError as e:
            self._error_count = getattr(self, "_error_count", 0) + 1
            return []
        finally:
            self._rate_limit_last = time.time()

    def _parse_jsearch_job(self, data: dict) -> Optional[Job]:
        try:
            apply_url = data.get("job_apply_link", "")
            canonical = self._canonicalise_url(apply_url)

            location = data.get("job_city", "") or data.get("job_country", "")

            job = Job(
                title=data.get("job_title", ""),
                company=data.get("employer_name", ""),
                location=location,
                remote=data.get("job_is_remote", False),
                job_type=data.get("job_employment_type", "full_time").lower().replace(" ", "_"),
                experience_level="mid",
                salary=data.get("job_salary"),
                description=data.get("job_description", ""),
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