"""Deduplication engine for job results.

Strategies:
1. Exact canonical URL match (preferred)
2. Fuzzy match on company + title + location
3. Keep a sources list per job; prefer employer ATS URL as apply_url
"""

from __future__ import annotations

import json
import difflib
from datetime import datetime
from typing import List, Set, Tuple, Optional

from app.schemas.job import Job


def canonical_key(url: str) -> str:
    """Generate a dedup key from a canonical URL."""
    from urllib.parse import urlparse
    parsed = urlparse(url)
    # Normalise: lowercase netloc, strip path trailing slash
    netloc = parsed.netloc.lower()
    path = parsed.path.rstrip("/") or "/"
    return f"{netloc}{path}"


def fuzzy_match_jobs(
    job1: Job, job2: Job, threshold: float = 0.85
) -> Tuple[bool, str]:
    """Determine if two jobs are a fuzzy match.

    Returns (is_match, reason_string).
    """
    # Normalise strings for comparison
    def norm(s: str) -> str:
        return s.lower().strip() if s else ""

    norm_comp1 = norm(job1.company)
    norm_comp2 = norm(job2.company)
    norm_title1 = norm(job1.title)
    norm_title2 = norm(job2.title)

    # For two jobs to be considered duplicates, company must be identical or near-identical
    company_match = difflib.SequenceMatcher(None, norm_comp1, norm_comp2).ratio()
    title_match = difflib.SequenceMatcher(None, norm_title1, norm_title2).ratio()
    location_match = difflib.SequenceMatcher(None, norm(job1.location), norm(job2.location)).ratio()

    # Company and Title must be strongly related (>0.9) to prevent collapsing distinct companies/titles like "Company A" & "Company B"
    if company_match < 0.9 or title_match < 0.85:
        return False, "distinct_job"

    # Weighted: title 50%, company 30%, location 20%
    composite = (title_match * 0.5) + (company_match * 0.3) + (location_match * 0.2)

    is_match = composite >= threshold

    reasons = []
    if title_match >= 0.9:
        reasons.append("title_similar")
    if company_match >= 0.8:
        reasons.append("company_similar")
    if location_match >= 0.8:
        reasons.append("location_similar")

    reason = "+".join(reasons) if reasons else "unknown"
    return is_match, reason


def dedupe_jobs(jobs: List[Job]) -> List[Job]:
    """Deduplicate a list of jobs using canonical URL then fuzzy matching.

    Returns deduplicated list preserving first-seen order for each unique job.
    Each job keeps a sources list of all canonical URLs that map to it.
    The preferred apply_url is the employer ATS URL when available.
    """
    if not jobs:
        return []

    deduped: List[Job] = []
    seen_keys: Set[str] = set()  # canonical URL keys
    # Track fuzzy duplicates that get subsumed
    fuzzy_groups: dict = {}  # key: (company_norm, title_norm, location_norm) -> index in deduped

    for job in jobs:
        # Strategy 1: Exact canonical URL match
        canon_key = canonical_key(job.canonical_url)

        # Check if this canonical URL was already seen
        if canon_key in seen_keys:
            # This is an exact canonical URL duplicate - merge sources
            # Find the existing job and add this source
            for existing in deduped:
                if canonical_key(existing.canonical_url) == canon_key:
                    # Merge sources: keep existing apply_url if it's an ATS URL,
                    # otherwise keep this one if it looks more like an ATS URL
                    if not existing.apply_url or _is_ats_url(existing.apply_url):
                        # Keep existing apply_url
                        pass
                    else:
                        existing.apply_url = job.apply_url
                    # Add source to tracking
                    existing.raw = existing.raw or {}
                    current_sources = existing.raw.get("sources", [])
                    if not current_sources and existing.source:
                        current_sources = [existing.source]
                    new_sources = job.raw.get("sources", [job.source]) if job.raw else [job.source]
                    for s in new_sources:
                        if s not in current_sources:
                            current_sources.append(s)
                    existing.raw["sources"] = current_sources
                    break
            continue

        # Strategy 2: Fuzzy match on company+title+location
        matched_fuzzy = False
        for group_key, idx in list(fuzzy_groups.items()):
            existing = deduped[idx]
            is_match, reason = fuzzy_match_jobs(job, existing)
            if is_match:
                # Merge: keep the one with more complete info or first-seen
                # Prefer keeping the one with ATS apply_url
                existing_sources = existing.raw.get("sources", []) if existing.raw else []
                job_sources = job.raw.get("sources", []) if job.raw else []

                # Update sources
                all_sources = list(set(existing_sources + job_sources))
                existing.raw = existing.raw or {}
                existing.raw["sources"] = all_sources

                # Prefer ATS URL as apply_url
                if not _is_ats_url(existing.apply_url) and _is_ats_url(job.apply_url):
                    existing.apply_url = job.apply_url

                # Track this job's canonical URL under the same group
                fuzzy_groups[group_key] = idx  # keep existing index
                matched_fuzzy = True
                break

        if matched_fuzzy:
            continue

        # No match found - add as new job
        # Initialise sources list
        sources = job.raw.get("sources", []) if job.raw else [job.source]
        # Create a shallow copy without raw, then set raw explicitly
        job_attrs = {k: getattr(job, k) for k in job.__dict__ if k != "raw"}
        job_copy = Job(**job_attrs)
        job_copy.raw = {"sources": sources}
        seen_keys.add(canon_key)
        deduped.append(job_copy)
        fuzzy_groups[(job.company.lower().strip(), job.title.lower().strip(), job.location.lower().strip())] = len(deduped) - 1

    # Sort by first_seen_at desc (newest first), then by id
    deduped.sort(key=lambda j: (j.first_seen_at or datetime.min, j.id or 0), reverse=True)

    return deduped


def _is_ats_url(url: str) -> bool:
    """Heuristic: check if URL looks like an ATS-derived apply URL."""
    if not url:
        return False
    url_lower = url.lower()
    ats_indicators = [
        "greenhouse.io/jobs", "lever.co/apply", "lever.co/postings", "jobs.lever.co", "ashbyhq.com",
        "workable.com", "smartrecruiters.com", "jobs.adp.com",
        "jobs.paycom", "jobs.bamboohr", "jobs.gusto",
    ]
    return any(indicator in url_lower for indicator in ats_indicators)