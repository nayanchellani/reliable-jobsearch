# Adding a New Connector to Job Aggregator

This skill documents the steps to add a job board or job source connector to the aggregator. Each connector must follow the established patterns so the system can integrate it seamlessly.

## Before You Begin

- This project is MIT-licensed, local-first, no paid services required.
- All connectors live in `app/connectors/`, each as a separate Python module.
- Every connector must inherit from `Connector` base class and implement `fetch()` and `health()`.
- Connectors must respect rate limits, cache responses, and never crash the search if they fail.

## Step 1: Pick Your Source

| Category | Examples |
|---|---|
| **ATS API** | Greenhouse, Lever, Ashby, Workable, SmartRecruiters |
| **Aggregator API** | Adzuna, Jooble, JSearch (RapidAPI), Remotive, Arbeitnow, RemoteOK, The Muse, HN Who is Hiring |
| **Web crawler** | Career pages with JSON-LD schema.org JobPosting |
| **Email alerts** | Gmail MCP / IMAP parser for LinkedIn, Naukri, Indeed alerts |
| **Search engine** | SearXNG / DuckDuckGo site: queries |
| **Direct scraping** | LinkedIn / Naukri (OFF by default, behind config flag with TOS warning) |

## Step 2: Create the Connector File

Create `app/connectors/<name>.py` following this pattern:

```python
"""<Source name> connector.

Docs: <URL>
"""

from __future__ import annotations

import asyncio
import time
from typing import List, Dict, Any, Optional

import httpx
from app.connectors.base import Connector
from app.schemas.job import Job


class <Name>Connector(Connector):
    """<Short description>."""

    name = "<name>"  # Unique identifier

    def __init__(self, <config_params>, rate_limit_ms: int = 1000):
        self.<config_params> = <config_params>
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
        """Fetch jobs from <source>.

        Args:
            query: Search query string (job title keywords)
            location: Location filter
            filters: Optional JobSearchFilters for additional filtering

        Returns:
            List of Job objects, empty list if no results or on error
        """
        self._rate_limit()

        url = "<API endpoint>"

        # Build request params from query, location, filters
        params = {}

        try:
            resp = await self.client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()

            jobs = []
            for item in data.get("jobs", []) if isinstance(data, dict) else data:
                job = self._parse_<name>_job(item)
                if job:
                    jobs.append(job)

            self._success_count = getattr(self, "_success_count", 0) + 1
            return jobs

        except httpx.HTTPError as e:
            self._error_count = getattr(self, "_error_count", 0) + 1
            logger.error(f"<Name> connector error: {e}")
            return []
        finally:
            self._rate_limit_last = time.time()

    def _parse_<name>_job(self, data: dict) -> Optional[Job]:
        """Parse a <source> job dict into a Job model.

        Extract and normalise fields:
        - title, company, location, remote, job_type, experience_level
        - salary (optional), description, posted_at (ISO datetime or None)
        - apply_url (absolute), canonical_url (strip tracking params)
        - status ("active" default)
        - raw (store original source data for debugging)
        """
        try:
            apply_url = data.get("<field>", "")
            canonical = self._canonicalise_url(apply_url)

            job = Job(
                title=data.get("<title_field>", ""),
                company=data.get("<company_field>", ""),
                location=data.get("<location_field>", ""),
                remote=data.get("<remote_field>", False),
                job_type=data.get("<job_type_field>", "full_time"),
                experience_level=data.get("<exp_level_field>", "mid"),
                salary=data.get("<salary_field>"),
                description=data.get("<description_field>", ""),
                posted_at=self._parse_date(data.get("<date_field>")),
                first_seen_at=datetime.utcnow(),
                source=self.name,
                apply_url=apply_url,
                canonical_url=canonical,
                status="active",
                raw=data,
            )
            return job
        except Exception:
            return None

    def _parse_date(self, date_str: Optional[str]) -> Optional[datetime]:
        """Parse ISO date string or return None."""
        if not date_str:
            return None
        try:
            from datetime import datetime, timezone
            return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return None

    def _rate_limit(self) -> None:
        now = time.time()
        elapsed = now - self._rate_limit_last
        if elapsed < self.rate_limit_ms / 1000.0:
            time.sleep(self.rate_limit_ms / 1000.0 - elapsed)
        self._rate_limit_last = time.time()
```

## Step 3: Write Tests

Create `tests/test_<name>.py` with pytest fixtures. Use saved JSON fixtures from the API (example below).

```python
"""Tests for <source> connector."""

from __future__ import annotations

import json
import pytest
from app.connectors.<name> import <Name>Connector
from app.schemas.job import Job


@pytest.fixture
def connector():
    """Create a connector instance for testing."""
    return <Name>Connector(token="test-token")


@pytest.fixture
def sample_job_data():
    """Sample job data from <source> API."""
    return {
        "title": "Software Engineer",
        "name": "Acme Corp",
        "location": {"city": "New York, NY"},
        "remote": False,
        "employment_type": "full_time",
        "experience_levels": ["mid"],
        "salary": "$120k-$150k",
        "content": "Build cool stuff",
        "absolute_application_url": "https://boards.greenhouse.io/jobs/1234",
    }


def test_connector_health(connector):
    """Health check returns valid ConnectorHealth."""
    h = connector.health()
    assert h.name == "<name>"
    assert isinstance(h.is_healthy, bool)


def test_parse_job(sample_job_data, connector):
    """Parsed job is a valid Job model."""
    job = connector._parse_<name>_job(sample_job_data)
    assert isinstance(job, Job)
    assert job.title == "Software Engineer"
    assert job.company == "Acme Corp"
    assert job.source == "<name>"
    assert job.canonical_url == "https://boards.greenhouse.io/jobs/1234"


def test_fetch_returns_jobs(connector, mocker):
    """fetch() returns List[Job] on success."""
    mocker.patch.object(connector.client, "get")
    # ... set up mock response ...
```

## Step 4: Register the Connector

If using auto-registration, add the connector config to `config.yaml`:

```yaml
connectors:
  enabled:
    - greenhouse
    - lever
    - ashby
    - <your-connector>
```

Or register manually in `app/api/main.py`:

```python
from app.connectors.<name> import <Name>Connector

connector = <Name>Connector(token="my-token")
register_connector("<name>", connector)
```

## Step 5: Run Tests

```bash
pytest tests/test_<name>.v -v
```

Verify:
- Health endpoint works
- Parse function produces valid Job objects
- Error handling (non-200, malformed JSON) returns []
- Rate limiting works
- Canonical URL dedup works

## Step 6: Update README

Add your source to `README.md` under "Sources covered" section, including:
- Name and API docs URL
- Rate limits and auth requirements
- Expected results coverage
- Any caveats (terms of service, bot detection, etc.)

## Connector Requirements Checklist

- [ ] Inherits from `Connector` base
- [ ] Implements `fetch(query, location, filters) -> List[Job]`
- [ ] Implements `health() -> ConnectorHealth`
- [ ] Respects rate limit (`rate_limit_ms` default 1000ms)
- [ ] Caches responses (HTTP cache or in-memory, 10min typical)
- [ ] Never raises unhandled exception that crashes search
- [ ] Returns normalised Job objects with correct source field
- [ ] Strips tracking params from apply_url to canonical_url
- [ ] Handles missing fields gracefully (defaults: remote=False, job_type=full_time, exp_level=mid)
- [ ] Test fixtures exist in `tests/fixtures/`

## Need Help?

- Review existing connectors in `app/connectors/` for patterns.
- Check `app/connectors/base.py` for the base class contract.
- See `.env.example` for API config.
- Run `pytest` to verify your tests integrate with the suite.