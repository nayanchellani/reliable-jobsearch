"""Async job enrichment using configured LLM endpoint."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.db.base import SessionLocal, Job as SQLJob


PROMPT = """Extract job metadata. Return ONLY JSON with keys experience_level and posted_at.
experience_level must be one of: fresher, junior, mid, senior, lead.
posted_at must be ISO 8601 date or null.
Title: {title}
Description: {description}
"""


async def _call_llm(title: str, description: str) -> dict[str, Any] | None:
    base_url = os.getenv("LLM_BASE_URL") or os.getenv("OPENAI_BASE_URL")
    api_key = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY")
    model = os.getenv("LLM_MODEL", "auto")
    if not base_url or not api_key:
        try:
            from app.db.base import UserSettings
            db = SessionLocal()
            try:
                s = {r.setting_key: r.setting_value for r in db.query(UserSettings).all()}
                base_url = base_url or s.get("llm_base_url")
                api_key = api_key or s.get("llm_api_key")
                model = model if model != "auto" else (s.get("llm_model") or "auto")
            finally:
                db.close()
        except Exception:
            pass
    if not base_url or not api_key:
        return None
    base = base_url.rstrip("/")
    url = base + "/chat/completions" if base.endswith("/v1") else base + "/v1/chat/completions"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": PROMPT.format(title=title, description=(description or "")[:500])}],
        "temperature": 0,
    }
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, headers={"Authorization": f"Bearer {api_key}"}, json=payload)
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            if isinstance(content, list):
                content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
            content = content.strip()
            if content.startswith("```"):
                content = content.strip("`")
                content = content.replace("json", "", 1).strip()
            parsed = json.loads(content)
            return parsed if isinstance(parsed, dict) else None
    except Exception:
        return None


def _normalize_level(level: Any) -> str | None:
    if not isinstance(level, str):
        return None
    v = level.lower().strip()
    mapping = {"entry": "fresher", "fresher": "fresher", "junior": "junior", "mid": "mid", "senior": "senior", "lead": "lead"}
    return mapping.get(v)


def _parse_posted_at(value: Any):
    if not value or not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


async def enrich_recent_jobs(limit: int = 50) -> int:
    db: Session = SessionLocal()
    updated = 0
    try:
        jobs = db.query(SQLJob).filter((SQLJob.posted_at.is_(None)) | (SQLJob.experience_level.in_(["mid", "entry"]))).order_by(SQLJob.first_seen_at.desc().nullslast()).limit(limit).all()
        for job in jobs:
            result = await _call_llm(job.title or "", job.description or "")
            if not result:
                continue
            level = _normalize_level(result.get("experience_level"))
            posted_at = _parse_posted_at(result.get("posted_at"))
            changed = False
            if level and (not job.experience_level or job.experience_level in ["mid", "entry"]):
                job.experience_level = level
                changed = True
            if posted_at and not job.posted_at:
                job.posted_at = posted_at
                changed = True
            if changed:
                updated += 1
        if updated:
            db.commit()
    finally:
        db.close()
    return updated
