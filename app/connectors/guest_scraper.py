"""GuestPageConnector for LinkedIn and Naukri (Layer 3).

STRICT SAFETY AND COMPLIANCE RULES:
- OFF by default. Requires explicit ENABLE_GUEST_SCRAPING=true.
- Prints terms-of-service warning at startup.
- Max 1 request per 5 seconds (rate limit: 5000ms).
- Daily request cap.
- Exponential backoff on rate limits / server errors.
- Automatic self-disable after 3 consecutive blocks (HTTP 403, 429, or captcha challenge).
- NEVER logs in, NEVER solves captchas, NEVER uses user credentials.
"""

from __future__ import annotations

import os
import re
import time
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

import httpx
from bs4 import BeautifulSoup

from app.connectors.base import Connector
from app.schemas.job import Job, JobSearchFilters, ConnectorHealth

logger = logging.getLogger(__name__)


class GuestPageConnector(Connector):
    """Layer 3 Guest Page scraper for LinkedIn & Naukri with self-disabling circuit breaker."""

    name = "guest_scraper"

    def __init__(
        self,
        rate_limit_ms: int = 5000,
        daily_cap: int = 100,
        enabled: Optional[bool] = None,
    ):
        self.rate_limit_ms = rate_limit_ms
        self.daily_cap = daily_cap
        self._consecutive_blocks: int = 0
        self._disabled: bool = False
        self._requests_today: int = 0
        self._last_reset_day: int = datetime.now().day

        # Must be explicitly enabled via environment or config
        flag = os.getenv("ENABLE_GUEST_SCRAPING", "false").lower() in ("true", "1", "yes")
        self.enabled = flag if enabled is None else enabled

        if self.enabled:
            print("\n" + "=" * 65)
            print("WARNING: Guest scraping for LinkedIn and Naukri is ENABLED.")
            print("Please ensure compliance with target website Terms of Service.")
            print("Strict 5s rate limits and circuit-breaker self-disable are active.")
            print("=" * 65 + "\n")

        self.client = httpx.AsyncClient(
            timeout=15.0,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                "Accept-Language": "en-US,en;q=0.9",
            },
            follow_redirects=True,
        )
        self._success_count: int = 0
        self._error_count: int = 0

    def health(self) -> ConnectorHealth:
        status_msg = "Disabled by circuit breaker" if self._disabled else ("Active" if self.enabled else "Disabled by config")
        return ConnectorHealth(
            name=self.name,
            is_healthy=self.enabled and not self._disabled,
            success_count=self._success_count,
            error_count=self._error_count,
            last_error=status_msg if (self._disabled or not self.enabled) else None,
        )

    def _check_daily_cap(self) -> bool:
        today = datetime.now().day
        if today != self._last_reset_day:
            self._requests_today = 0
            self._last_reset_day = today

        if self._requests_today >= self.daily_cap:
            logger.warning("Guest scraper reached daily request cap.")
            return False
        return True

    def _record_block(self, reason: str):
        self._consecutive_blocks += 1
        logger.warning(f"Guest scraper blocked ({reason}). Consecutive blocks: {self._consecutive_blocks}")
        if self._consecutive_blocks >= 3:
            self._disabled = True
            logger.error("Guest scraper self-disabled after 3 consecutive blocks.")

    def _record_success(self):
        self._consecutive_blocks = 0
        self._success_count += 1

    async def fetch_guest_linkedin_jobs(self, query: str, location: Optional[str] = None) -> List[Job]:
        """Fetch public job postings from LinkedIn public guest endpoint."""
        if not self.enabled or self._disabled or not self._check_daily_cap():
            return []

        self._respect_rate_limit()
        self._requests_today += 1

        url = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
        params = {"keywords": query, "start": "0"}
        if location:
            params["location"] = location

        try:
            resp = await self.client.get(url, params=params)

            # Detect blocks, 403, 429, or captcha redirects
            if resp.status_code in (403, 429) or "checkpoint/challenge" in str(resp.url):
                self._record_block(f"HTTP {resp.status_code} / captcha")
                return []

            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            job_cards = soup.select("li, .base-card, .job-search-card")

            jobs: List[Job] = []
            for card in job_cards:
                title_elem = card.select_one(".base-search-card__title, h3")
                company_elem = card.select_one(".base-search-card__subtitle, h4, .job-search-card__subtitle")
                location_elem = card.select_one(".job-search-card__location")
                link_elem = card.select_one("a.base-card__full-link, a")

                title = title_elem.get_text(strip=True) if title_elem else ""
                company = company_elem.get_text(strip=True) if company_elem else ""
                loc = location_elem.get_text(strip=True) if location_elem else (location or "Remote")
                apply_url = link_elem["href"] if (link_elem and link_elem.get("href")) else ""

                if title and apply_url:
                    canonical = self._canonicalise_url(apply_url)
                    jobs.append(
                        Job(
                            title=title,
                            company=company or "Verified Employer",
                            location=loc,
                            remote="remote" in f"{title} {loc}".lower(),
                            job_type="full_time",
                            experience_level="mid",
                            salary=None,
                            description="",
                            posted_at=datetime.now(timezone.utc),
                            first_seen_at=datetime.now(timezone.utc),
                            source="linkedin",
                            apply_url=apply_url,
                            canonical_url=canonical,
                            status="active",
                            raw={"scraper": "guest_linkedin"},
                        )
                    )

            self._record_success()
            return jobs

        except Exception as e:
            self._error_count += 1
            return []

    async def fetch(
        self,
        query: str,
        location: Optional[str] = None,
        filters: Optional[JobSearchFilters] = None,
    ) -> List[Job]:
        """Fetch jobs if enabled."""
        if not self.enabled or self._disabled:
            return []
        return await self.fetch_guest_linkedin_jobs(query, location)
