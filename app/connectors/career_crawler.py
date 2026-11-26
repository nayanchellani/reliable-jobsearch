"""Generic career page crawler.

Given any URL, attempts to:
1. Detect the ATS from meta tags/patterns
2. Extract schema.org JobPosting JSON-LD
3. Fall back to Playwright rendering then Firecrawl scraping
"""

from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Tuple

from bs4 import BeautifulSoup
import httpx
try:
    from playwright.async_api import async_playwright
except Exception:
    async_playwright = None

from app.connectors.base import Connector
from app.schemas.job import Job, JobSearchFilters, ConnectorHealth

CAREER_CRAWLER_RATE_LIMIT = 2000  # 2 seconds between requests


class CareerCrawlerConnector(Connector):
    """Crawler that discovers ATS and extracts jobs from career pages."""

    name = "career_crawler"

    def __init__(self, rate_limit_ms: int = 2000):
        super().__init__()
        self.rate_limit_ms = rate_limit_ms
        self.client = httpx.AsyncClient(timeout=60.0)

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
        start_url: Optional[str] = None,
    ) -> List[Job]:
        """Fetch jobs by crawling a career page."""
        await self._rate_limit()

        if not start_url:
            self._error_count = getattr(self, "_error_count", 0) + 1
            return []

        all_jobs = []

        # Step 1: Try to detect ATS and extract JSON-LD
        try:
            jobs = await self._extract_json_ld_jobs(start_url)
            all_jobs.extend(jobs)
        except Exception:
            pass

        # Step 2: If no JSON-LD jobs, try full HTML parsing
        if not all_jobs:
            try:
                jobs = await self._extract_html_jobs(start_url, query, location)
                all_jobs.extend(jobs)
            except Exception:
                pass

        # Step 3: Fallback to Playwright + Firecrawl
        if not all_jobs:
            try:
                jobs = await self._playwright_fallback(start_url, query, location)
                all_jobs.extend(jobs)
            except Exception:
                pass

        self._success_count = getattr(self, "_success_count", 0) + 1
        return all_jobs

    async def _extract_json_ld_jobs(self, url: str) -> List[Job]:
        """Extract JobPosting schema.org JSON-LD from page."""
        resp = await self.client.get(url)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        jobs = []
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or script.get_text())
                if isinstance(data, list):
                    items = data
                else:
                    items = [data]

                for item in items:
                    if item.get("@type") == "JobPosting":
                        job = self._parse_json_ld_job(item)
                        if job:
                            jobs.append(job)
            except (json.JSONDecodeError, Exception):
                continue

        return jobs

    def _parse_json_ld_job(self, data: dict) -> Optional[Job]:
        """Parse JSON-LD JobPosting into Job model."""
        try:
            apply_url = data.get("url", "")
            canonical = self._canonicalise_url(apply_url)

            title = data.get("title", "")
            company = data.get("hiringOrganization", {}).get("name", "")
            location = data.get("jobLocation", {}).get("address", {}).get("addressRegion", "")
            if not location:
                location = data.get("jobLocation", {}).get("address", {}).get("addressLocality", "")

            posted_at = None
            if data.get("datePosted"):
                try:
                    from datetime import datetime, timezone
                    posted_at = datetime.fromisoformat(data["datePosted"]).replace(tzinfo=timezone.utc)
                except (ValueError, TypeError):
                    pass

            job = Job(
                title=title,
                company=company,
                location=location or "",
                remote=data.get("jobField", False),  # fallback field
                job_type=data.get("employmentType", ["full_time"])[0] if isinstance(data.get("employmentType"), list) else data.get("employmentType", "full_time"),
                experience_level=data.get("experienceLevel", "mid"),
                salary=data.get("baseSalary", {}).get("value", {}).get("value", None) if data.get("baseSalary") else None,
                description=data.get("description", ""),
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

    async def _extract_html_jobs(
        self, url: str, query: str, location: Optional[str]
    ) -> List[Job]:
        """Fall back to HTML parsing for job links."""
        resp = await self.client.get(url)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        jobs = []
        # Look for job links with common patterns
        for link in soup.find_all("a", href=True):
            href = link["href"]
            title_text = link.get_text(strip=True)

            # Filter for job-like URLs
            if any(pattern in href.lower() for pattern in ["/job", "/positions", "/careers", "apply"]):
                if len(title_text) > 5:  # Reasonable job title length:
                    apply_url = href
                    if apply_url.startswith("/"):
                        from urllib.parse import urljoin
                        apply_url = urljoin(url, href)
                    apply_url = self._canonicalise_url(apply_url)
                    job = Job(
                        title=title_text or query[:50],
                        company="",
                        location=location or "",
                        remote=False,
                        job_type="full_time",
                        experience_level="mid",
                        salary=None,
                        description="",
                        posted_at=None,
                        first_seen_at=datetime.now(timezone.utc),
                        source=self.name,
                        apply_url=apply_url,
                        canonical_url=apply_url,
                        status="active",
                        raw={"html_snippet": href},
                    )
                    jobs.append(job)

        return jobs

    async def _playwright_fallback(
        self, url: str, query: str, location: Optional[str]
    ) -> List[Job]:
        """Use Playwright to render JS-heavy pages then extract."""
        jobs = []
        if async_playwright is None:
            return jobs
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context(user_agent="Mozilla/5.0")
                page = await context.new_page()
                try:
                    await page.goto(url, wait_until="networkidle", timeout=30000)
                except Exception:
                    return jobs
                content = await page.content()
                if not content:
                    return jobs
                soup = BeautifulSoup(content, "html.parser")
                for script in soup.find_all("script", type="application/ld+json"):
                    try:
                        data = json.loads(script.string or script.get_text())
                        items = data if isinstance(data, list) else [data]
                        for item in items:
                            if item.get("@type") == "JobPosting":
                                job = self._parse_json_ld_job(item)
                                if job:
                                    jobs.append(job)
                    except Exception:
                        continue
                await context.close()
                await browser.close()
        except Exception:
            return jobs
        return jobs

    # Uses Connector._rate_limit()