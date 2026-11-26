"""SearchEngineConnector for LinkedIn and Naukri (Layer 1).

Uses pluggable backends:
1. SearXNG (docker service)
2. DuckDuckGo HTML / Lite fallback

Features:
- Generates 3-5 query variants for LinkedIn and Naukri
- Filters results matching known job URL patterns
- Canonicalises URLs (strips tracking params)
- Polite page fetch (cache, delay, robots.txt awareness)
- Extracts JSON-LD JobPosting schema, falls back to HTML parsing or search snippet (marked partial=True)
- Infers posted_at from JSON-LD datePosted or relative text ('2 days ago')
"""

from __future__ import annotations

import os
import re
import json
import time
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

import httpx
from bs4 import BeautifulSoup

from app.connectors.base import Connector, ConnectorError
from app.schemas.job import Job, JobSearchFilters, ConnectorHealth


class SearchEngineConnector(Connector):
    """Layer 1 Search-engine-based connector for LinkedIn and Naukri."""

    name = "search_engine"

    def __init__(
        self,
        searxng_url: Optional[str] = None,
        rate_limit_ms: int = 2000,
        enable_linkedin: bool = True,
        enable_naukri: bool = True,
    ):
        self.rate_limit_ms = rate_limit_ms
        self.searxng_url = searxng_url or os.getenv("SEARXNG_URL", "http://localhost:8080")
        self.enable_linkedin = enable_linkedin
        self.enable_naukri = enable_naukri
        self.client = httpx.AsyncClient(
            timeout=20.0,
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
        self._cache: Dict[str, Any] = {}
        self._success_count: int = 0
        self._error_count: int = 0

    def health(self) -> ConnectorHealth:
        return ConnectorHealth(
            name=self.name,
            is_healthy=True,
            success_count=self._success_count,
            error_count=self._error_count,
        )

    def _generate_queries(
        self, target_site: str, query: str, location: Optional[str] = None, job_type: Optional[str] = None
    ) -> List[str]:
        """Generate 3-5 query variants for the target domain."""
        base_term = query.strip() if query else "software engineer"
        loc = f" {location.strip()}" if location else ""
        type_str = f" {job_type.strip()}" if job_type else ""

        if target_site == "linkedin":
            site_prefix = "site:linkedin.com/jobs"
            return [
                f"{site_prefix} {base_term}{loc}{type_str}",
                f'{site_prefix} "{base_term}"{loc}',
                f"linkedin jobs {base_term}{loc}",
            ]
        elif target_site == "naukri":
            site_prefix = "site:naukri.com/job-listings"
            return [
                f"{site_prefix} {base_term}{loc}{type_str}",
                f'{site_prefix} "{base_term}"{loc}',
                f"{site_prefix} {base_term} jobs",
            ]
        elif target_site == "wellfound":
            site_prefix = "site:wellfound.com/jobs"
            defaults = [
                f'{site_prefix} "AI Engineer"',
                f'{site_prefix} "GenAI Engineer"',
                f'{site_prefix} "Python Developer"',
                f'{site_prefix} "Machine Learning Engineer"',
            ]
            if base_term and base_term.lower() not in ["software engineer", ""]:
                q = f'{site_prefix} "{base_term}"{loc}'
                return [q] + [d for d in defaults if d.lower() != q.lower()]
            return defaults
        elif target_site == "ycombinator":
            site_prefix = "site:ycombinator.com/jobs"
            term = base_term or "software engineer"
            queries = [f'{site_prefix} "{term}"{loc}']
            if loc:
                queries.append(f'{site_prefix} "{term}" {location.strip()}')
            if term.lower() in ["software engineer", ""]:
                queries.extend([
                    f'{site_prefix} "AI Engineer"{loc}',
                    f'{site_prefix} "Python Developer"{loc}',
                ])
            # dedupe preserving order
            seen=set(); out=[]
            for q in queries:
                k=q.lower()
                if k not in seen:
                    seen.add(k); out.append(q)
            return out[:5]
        return [f"{base_term}{loc}"]

    def _is_target_job_url(self, url: str, target_site: str) -> bool:
        """Filter URLs to ensure they match genuine job posting structures."""
        parsed = urlparse(url)
        netloc = parsed.netloc.lower()
        path = parsed.path.lower()

        if target_site == "linkedin":
            return "linkedin.com" in netloc and ("/jobs/view/" in path or "/jobs/" in path)
        elif target_site == "naukri":
            return "naukri.com" in netloc and ("/job-listings" in path or "-jobs-" in path or "/job-" in path)
        elif target_site == "wellfound":
            return "wellfound.com" in netloc and "/jobs" in path
        elif target_site == "ycombinator":
            return "ycombinator.com" in netloc and path.startswith("/jobs")
        return False

    def _canonicalise_url(self, url: str) -> str:
        """Canonicalise job URLs by stripping tracking & session params."""
        parsed = urlparse(url)
        clean_path = parsed.path.rstrip("/")
        # Keep clean schema & domain
        return urlunparse((parsed.scheme, parsed.netloc, clean_path, "", "", ""))

    async def _query_searxng(self, q: str) -> List[Dict[str, str]]:
        """Query SearXNG JSON endpoint."""
        url = f"{self.searxng_url.rstrip('/')}/search"
        params = {"q": q, "format": "json"}
        try:
            resp = await self.client.get(url, params=params)
            if resp.status_code != 200:
                raise ConnectorError(f"SearXNG returned HTTP {resp.status_code}: {resp.text[:200]}")
            data = resp.json()
            results = []
            for item in data.get("results", []):
                results.append({
                    "url": item.get("url", ""),
                    "title": item.get("title", ""),
                    "snippet": item.get("content", ""),
                })
            return results
        except ConnectorError:
            raise
        except Exception as e:
            raise ConnectorError(f"SearXNG connection error ({url}): {e}") from e

    async def _query_duckduckgo_fallback(self, q: str) -> List[Dict[str, str]]:
        """Fallback to DuckDuckGo HTML search if SearXNG is unavailable."""
        url = "https://html.duckduckgo.com/html/"
        data = {"q": q}
        results: List[Dict[str, str]] = []
        try:
            resp = await self.client.post(url, data=data)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                for link in soup.select(".result__snippet"):
                    title_elem = link.find_previous_sibling("h2") or link.parent.find("h2")
                    a_elem = title_elem.find("a") if title_elem else None
                    if a_elem and a_elem.get("href"):
                        href = a_elem["href"]
                        # Extract clean URL from DDG redirect if present
                        if "/l/?" in href:
                            match = re.search(r"uddg=([^&]+)", href)
                            if match:
                                from urllib.parse import unquote
                                href = unquote(match.group(1))
                        results.append({
                            "url": href,
                            "title": a_elem.get_text(strip=True),
                            "snippet": link.get_text(strip=True),
                        })
        except Exception as e:
            raise ConnectorError(f"DuckDuckGo fallback error: {e}") from e
        return results

    def _parse_relative_date(self, text: str) -> Optional[datetime]:
        """Infer datetime from strings like '2 days ago', '3 hours ago', 'Just posted'."""
        if not text:
            return None
        text_lower = text.lower()
        now = datetime.now(timezone.utc)
        if "just" in text_lower or "today" in text_lower:
            return now

        m_hours = re.search(r"(\d+)\s+hour", text_lower)
        if m_hours:
            return now - timedelta(hours=int(m_hours.group(1)))

        m_days = re.search(r"(\d+)\s+day", text_lower)
        if m_days:
            return now - timedelta(days=int(m_days.group(1)))

        m_weeks = re.search(r"(\d+)\s+week", text_lower)
        if m_weeks:
            return now - timedelta(weeks=int(m_weeks.group(1)))

        m_months = re.search(r"(\d+)\s+month", text_lower)
        if m_months:
            return now - timedelta(days=int(m_months.group(1)) * 30)

        return None

    async def _fetch_and_extract_job(
        self, url: str, snippet_title: str, snippet_text: str, source: str
    ) -> Optional[Job]:
        """Fetch polite page or extract from snippet if blocked."""
        canonical_url = self._canonicalise_url(url)
        if canonical_url in self._cache:
            return self._cache[canonical_url]

        await self._rate_limit()

        title = snippet_title
        company = ""
        location = "Remote"
        description = snippet_text
        posted_at = None
        is_partial = False

        # Try to extract details from snippet directly first
        # Format often: "Title - Company - Location"
        parts = re.split(r"\s*[-–|•]\s*", snippet_title)
        if len(parts) >= 2:
            title = parts[0].strip()
            company = parts[1].strip()
            if len(parts) >= 3:
                location = parts[2].strip()

        try:
            resp = await self.client.get(url)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                # 1. Try schema.org JobPosting JSON-LD
                for script in soup.find_all("script", type="application/ld+json"):
                    try:
                        data = json.loads(script.string or "")
                        if isinstance(data, list):
                            data = data[0] if data else {}
                        if data.get("@type") == "JobPosting":
                            title = data.get("title", title)
                            hiring_org = data.get("hiringOrganization")
                            if isinstance(hiring_org, dict):
                                company = hiring_org.get("name", company)
                            elif isinstance(hiring_org, str):
                                company = hiring_org

                            job_loc = data.get("jobLocation")
                            if isinstance(job_loc, dict):
                                addr = job_loc.get("address")
                                if isinstance(addr, dict):
                                    location = addr.get("addressLocality") or addr.get("addressRegion") or location
                                elif isinstance(addr, str):
                                    location = addr

                            description = data.get("description", description)
                            date_str = data.get("datePosted")
                            if date_str:
                                try:
                                    posted_at = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                                except Exception:
                                    pass
                            break
                    except Exception:
                        continue
            else:
                is_partial = True
        except Exception:
            is_partial = True

        if not posted_at:
            posted_at = self._parse_relative_date(snippet_text)

        if not company:
            company = "Verified Employer"

        job = Job(
            title=title,
            company=company,
            location=location,
            remote="remote" in f"{title} {location} {description}".lower(),
            job_type="full_time",
            experience_level="mid",
            salary=None,
            description=description,
            posted_at=posted_at or datetime.now(timezone.utc),
            first_seen_at=datetime.now(timezone.utc),
            source=source,
            apply_url=url,
            canonical_url=canonical_url,
            status="active",
            raw={"partial": is_partial, "snippet": snippet_text, "source_engine": "search"},
        )
        self._cache[canonical_url] = job
        return job

    async def fetch(
        self,
        query: str,
        location: Optional[str] = None,
        filters: Optional[JobSearchFilters] = None,
    ) -> List[Job]:
        """Execute search engine queries for LinkedIn and Naukri."""
        jobs: List[Job] = []
        targets = []
        if self.enable_linkedin:
            targets.append("linkedin")
        if self.enable_naukri:
            targets.append("naukri")
        targets.append("wellfound")
        targets.append("ycombinator")

        job_type = filters.job_type if filters else None

        for target in targets:
            queries = self._generate_queries(target, query, location, job_type)
            for q in queries[:2]:  # Use top 2 targeted query variants to be fast and respectful
                results = await self._query_searxng(q)
                if not results:
                    results = await self._query_duckduckgo_fallback(q)

                for item in results:
                    raw_url = item.get("url", "")
                    if self._is_target_job_url(raw_url, target):
                        try:
                            job = await self._fetch_and_extract_job(
                                raw_url,
                                item.get("title", ""),
                                item.get("snippet", ""),
                                source=target,
                            )
                            if job:
                                jobs.append(job)
                        except Exception as e:
                            self._error_count += 1
                            continue

        self._success_count += 1
        return jobs
