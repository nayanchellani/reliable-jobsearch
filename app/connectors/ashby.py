"""Ashby connector.

Docs: https://api.ashbyhq.com/posting-api/job-board/{name}
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

import httpx
from app.connectors.base import Connector, ConnectorError, normalize_job_type
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
                    job = self._parse_ashby_job(j, board)
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

    def _parse_ashby_job(self, data: dict, board: str = "") -> Optional[Job]:
        """Parse an Ashby job dict into a Job model."""
        try:
            apply_url = data.get("applyUrl") or data.get("jobUrl", "")
            canonical = self._canonicalise_url(apply_url)

            title = data.get("title", "")
            if not title:
                return None

            # Ashby API has no company name — use board slug as fallback
            company = data.get("company") or board.replace("-", " ").title() or "Unknown"
            location = data.get("location") or ""
            if isinstance(location, dict):
                location = location.get("name") or location.get("city") or ""
            remote = bool(data.get("isRemote", False)) or (data.get("workplaceType") or "").lower() == "remote"
            job_type = normalize_job_type(data.get("employmentType") or "")

            posted_at = None
            raw_date = data.get("publishedAt") or data.get("postedDate")
            if raw_date:
                try:
                    posted_at = datetime.fromisoformat(raw_date.replace("Z", "+00:00"))
                except (ValueError, TypeError):
                    pass

            job = Job(
                title=title,
                company=company,
                location=location,
                remote=remote,
                job_type=job_type,
                experience_level="mid",
                salary=None,
                description=data.get("descriptionPlain") or data.get("descriptionHtml") or "",
                posted_at=posted_at,
                first_seen_at=datetime.now(timezone.utc),
                source=self.name,
                apply_url=apply_url,
                canonical_url=canonical,
                status="active",
                raw=data,
            )
            return job
        except Exception as e:
            return None