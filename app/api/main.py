"""FastAPI main application for the Job Aggregator."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from contextlib import asynccontextmanager
from typing import List, Dict, Any, Optional

from fastapi import FastAPI, HTTPException, Query, Depends, UploadFile, File
from fastapi.responses import PlainTextResponse, Response
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from app.db.base import Base, Job as SQLJob, engine, SessionLocal
from app.schemas.job import Job, JobSearchFilters, ConnectorHealth
from app.dedupe import dedupe_jobs
from app.resume_service import ResumeService, ResumeProfile, MatchScoreResult
from app.connectors.base import Connector
from app.connectors.greenhouse import GreenhouseConnector
from app.connectors.lever import LeverConnector
from app.connectors.ashby import AshbyConnector
from app.connectors.career_crawler import CareerCrawlerConnector
from app.connectors.alert_email import AlertEmailConnector
from app.connectors.adzuna import AdzunaConnector
from app.connectors.jooble import JoobleConnector
from app.connectors.jsearch import JSearchConnector
from app.connectors.remotive import RemotiveConnector
from app.connectors.arbeitnow import ArbeitnowConnector
from app.connectors.remoteok import RemoteOKConnector
from app.connectors.search_engine import SearchEngineConnector
from app.connectors.guest_scraper import GuestPageConnector
from app.api.auth import router as auth_router, settings_router, get_current_user


# In-memory connector registry
connectors: Dict[str, Connector] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create DB tables on startup, initialize connectors, and schedule background sync."""
    Base.metadata.create_all(bind=engine)

    # Initialize connectors from settings
    from app.db.base import SessionLocal
    from app.api.auth import UserSettings

    db = SessionLocal()
    try:
        settings = {s.setting_key: s.setting_value for s in db.query(UserSettings).all()}

        # Load default ATS tokens from companies.yaml if available
        companies_cfg: Dict[str, List[str]] = {}
        companies_yaml = Path("companies.yaml")
        if companies_yaml.exists():
            try:
                import yaml
                companies_cfg = yaml.safe_load(companies_yaml.read_text(encoding="utf-8")) or {}
            except Exception as e:
                print(f"[WARN] Failed to load companies.yaml: {e}")

        # Greenhouse (support multiple board tokens, default to companies.yaml)
        gh_default = ",".join(companies_cfg.get("greenhouse", ["stripe", "airbnb", "figma"]))
        gh_tokens = settings.get("greenhouse_token") or os.environ.get("GREENHOUSE_TOKEN") or gh_default
        register_connector("greenhouse", GreenhouseConnector(gh_tokens))

        # Lever (support multiple companies, default to companies.yaml)
        lever_default = ",".join(companies_cfg.get("lever", ["spotify", "coupa"]))
        lever_companies = settings.get("lever_company") or os.environ.get("LEVER_COMPANY") or lever_default
        register_connector("lever", LeverConnector(lever_companies))

        # Ashby (support multiple boards, default to companies.yaml)
        ashby_default = ",".join(companies_cfg.get("ashby", ["linear", "vanta", "ramp"]))
        ashby_name = settings.get("ashby_name") or os.environ.get("ASHBY_NAME") or ashby_default
        if ashby_name:
            register_connector("ashby", AshbyConnector(ashby_name))

        # Career Crawler (no auth needed)
        register_connector("career_crawler", CareerCrawlerConnector())

        # Alert Email
        if settings.get("imap_server"):
            register_connector("alert_email", AlertEmailConnector())

        # Free connectors (no auth needed)
        register_connector("adzuna", AdzunaConnector(
            settings.get("adzuna_app_id", ""), settings.get("adzuna_api_key", "")
        ))
        register_connector("jooble", JoobleConnector(settings.get("jooble_api_key", "")))
        register_connector("jsearch", JSearchConnector(settings.get("jsearch_api_key", "")))
        register_connector("remotive", RemotiveConnector())
        register_connector("arbeitnow", ArbeitnowConnector())
        register_connector("remoteok", RemoteOKConnector())

        # LinkedIn & Naukri Connectors
        # Layer 1: SearchEngineConnector (Enabled by default)
        register_connector("search_engine", SearchEngineConnector(
            searxng_url=settings.get("searxng_url") or os.environ.get("SEARXNG_URL") or "http://searxng:8080",
            enable_linkedin=settings.get("enable_linkedin_scraping", "true") == "true",
            enable_naukri=settings.get("enable_naukri_scraping", "true") == "true",
        ))

        # Layer 3: GuestPageConnector (Disabled by default)
        enable_guest = settings.get("enable_guest_scraping", "false") == "true"
        register_connector("guest_scraper", GuestPageConnector(enabled=enable_guest))

    finally:
        db.close()

    # Background scheduler: sync free connectors every 30 minutes
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    scheduler = AsyncIOScheduler()

    async def _background_sync():
        """Sync free connectors (remotive, arbeitnow, remoteok) silently."""
        db = SessionLocal()
        try:
            free_sources = ["remotive", "arbeitnow", "remoteok"]
            for name in free_sources:
                connector = connectors.get(name)
                if not connector:
                    continue
                try:
                    jobs = await connector.fetch(query="", location=None)
                    for job in jobs:
                        existing = db.query(SQLJob).filter(
                            SQLJob.canonical_url == job.canonical_url
                        ).first()
                        if not existing:
                            db_job = SQLJob(
                                title=job.title, company=job.company,
                                location=job.location, remote=job.remote,
                                job_type=job.job_type, experience_level=job.experience_level,
                                salary=job.salary, description=job.description,
                                posted_at=job.posted_at, first_seen_at=job.first_seen_at,
                                source=job.source, apply_url=job.apply_url,
                                canonical_url=job.canonical_url, status=job.status,
                                raw=job.raw,
                            )
                            db.add(db_job)
                    db.commit()
                except Exception as e:
                    print(f"[scheduler] Error syncing {name}: {e}")
        finally:
            db.close()

    # Run immediately on startup, then every 30 minutes
    scheduler.add_job(_background_sync, "interval", minutes=30, id="free_sync")
    scheduler.start()
    # Trigger initial sync after a short delay
    import asyncio as _asyncio
    _asyncio.ensure_future(_background_sync())

    yield

    scheduler.shutdown(wait=False)


app = FastAPI(
    title="Job Aggregator",
    version="0.1.0",
    lifespan=lifespan,
)

# Include auth and settings routers
app.include_router(auth_router)
app.include_router(settings_router)

# CORS - restrict to frontend origin
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["health"])
async def health() -> Dict[str, str]:
    """Simple health check."""
    return {"status": "ok"}


@app.get("/jobs", response_model=List[Job], tags=["search"])
async def search_jobs(
    q: Optional[str] = Query(default=None, description="Free text search"),
    location: Optional[str] = Query(
        default=None, description="Location filter (city/region)"
    ),
    job_type: Optional[str] = Query(
        default=None, description="Job type filter"
    ),
    experience_level: Optional[str] = Query(
        default=None, description="Experience level filter"
    ),
    remote: Optional[bool] = Query(
        default=None, description="Remote filter"
    ),
    source: Optional[str] = Query(
        default=None, description="Source filter"
    ),
    sort: str = Query(
        default="posted_at_desc", description="Sort order"
    ),
    page: int = Query(default=1, ge=1, description="Page number"),
    per_page: int = Query(
        default=20, ge=1, le=100, description="Items per page"
    ),
) -> Any:
    """Search jobs with full filter support."""

    from app.db.base import SessionLocal

    db = SessionLocal()

    try:
        # Build query
        query = db.query(SQLJob)

        # Text filters
        if q:
            query = query.filter(
                (SQLJob.title.ilike(f"%{q}%"))
                | (SQLJob.company.ilike(f"%{q}%"))
            )

        if location:
            query = query.filter(SQLJob.location.ilike(f"%{location}%"))

        if remote is not None:
            query = query.filter(SQLJob.remote == remote)

        if source:
            query = query.filter(SQLJob.source == source)

        # Type filters
        if job_type:
            query = query.filter(SQLJob.job_type == job_type)

        if experience_level:
            query = query.filter(
                SQLJob.experience_level == experience_level
            )

        # Sorting
        if sort == "posted_at_desc":
            query = query.order_by(SQLJob.posted_at.desc())
        elif sort == "posted_at_asc":
            query = query.order_by(SQLJob.posted_at.asc())
        elif sort == "title_asc":
            query = query.order_by(SQLJob.title.asc())
        elif sort == "title_desc":
            query = query.order_by(SQLJob.title.desc())

        # Date range
        # Note: date filters would need date_from/date_to params added to API

        # Pagination
        total = query.count()
        query = query.offset((page - 1) * per_page).limit(per_page)

        # Execute
        db_jobs = query.all()

        # Convert SQLAlchemy models to pydantic
        jobs = []
        for sj in db_jobs:
            job = Job(
                id=sj.id,
                title=sj.title,
                company=sj.company,
                location=sj.location,
                remote=sj.remote,
                job_type=sj.job_type,
                experience_level=sj.experience_level,
                salary=sj.salary,
                description=sj.description,
                posted_at=sj.posted_at,
                first_seen_at=sj.first_seen_at,
                source=sj.source,
                apply_url=sj.apply_url,
                canonical_url=sj.canonical_url,
                status=sj.status,
                raw=json.loads(sj.raw) if isinstance(sj.raw, str) else (sj.raw or {}),
            )
            jobs.append(job)

        # Deduplicate
        deduped = dedupe_jobs(jobs)

        return deduped

    finally:
        db.close()


@app.post("/jobs", response_model=Job, tags=["ingest"])
async def ingest_job(job: Job, user: dict = Depends(get_current_user)) -> Any:
    """Ingest a single job into the database.

    Used by connectors to add discovered jobs.
    Requires authentication.
    """
    from app.db.base import SessionLocal

    db = SessionLocal()

    try:
        # Check if job already exists by canonical_url
        existing = db.query(SQLJob).filter(
            SQLJob.canonical_url == job.canonical_url
        ).first()

        if existing:
            # Update if new one is newer or has more info
            if not existing.first_seen_at or job.first_seen_at > existing.first_seen_at:
                for field, value in job.model_dump(
                    exclude={"id", "first_seen_at"}
                ).items():
                    setattr(existing, field, value)
                existing.first_seen_at = job.first_seen_at or existing.first_seen_at
                db.commit()
                db.refresh(existing)
                return existing
            return existing

        # New job - add to DB
        db_job = SQLJob(
            title=job.title,
            company=job.company,
            location=job.location,
            remote=job.remote,
            job_type=job.job_type,
            experience_level=job.experience_level,
            salary=job.salary,
            description=job.description,
            posted_at=job.posted_at,
            first_seen_at=job.first_seen_at or time.time(),
            source=job.source,
            apply_url=job.apply_url,
            canonical_url=job.canonical_url,
            status=job.status,
            raw=job.raw,
        )
        db.add(db_job)
        db.commit()
        db.refresh(db_job)
        return db_job

    finally:
        db.close()


@app.get("/connectors/health", response_model=List[ConnectorHealth], tags=["connectors"])
async def connector_health() -> Any:
    """Get health status for all registered connectors."""
    health_list = []
    for name, connector in connectors.items():
        try:
            h = connector.health()
            h.name = name  # Ensure name is set
            health_list.append(h)
        except Exception as e:
            health_list.append(
                ConnectorHealth(
                    name=name,
                    is_healthy=False,
                    last_error=str(e),
                )
            )
    return health_list


@app.post("/connectors/sync", tags=["connectors"])
async def sync_connectors(
    query: Optional[str] = Query(default=""),
    location: Optional[str] = Query(default=""),
) -> Any:
    """Sync jobs from all registered connectors. No auth required (local tool)."""
    from app.db.base import SessionLocal
    from app.schemas.job import Job as PydanticJob

    db = SessionLocal()
    total_jobs = 0

    try:
        for name, connector in connectors.items():
            try:
                jobs = await connector.fetch(query=query, location=location)
                for job in jobs:
                    # Check if job already exists by canonical_url
                    existing = db.query(SQLJob).filter(
                        SQLJob.canonical_url == job.canonical_url
                    ).first()

                    if existing:
                        # Update if new one is newer or has more info
                        if not existing.first_seen_at or job.first_seen_at > existing.first_seen_at:
                            for field, value in job.model_dump(
                                exclude={"id", "first_seen_at"}
                            ).items():
                                setattr(existing, field, value)
                            existing.first_seen_at = job.first_seen_at or existing.first_seen_at
                            db.commit()
                    else:
                        # New job - add to DB
                        db_job = SQLJob(
                            title=job.title,
                            company=job.company,
                            location=job.location,
                            remote=job.remote,
                            job_type=job.job_type,
                            experience_level=job.experience_level,
                            salary=job.salary,
                            description=job.description,
                            posted_at=job.posted_at,
                            first_seen_at=job.first_seen_at or time.time(),
                            source=job.source,
                            apply_url=job.apply_url,
                            canonical_url=job.canonical_url,
                            status=job.status,
                            raw=job.raw,
                        )
                        db.add(db_job)
                        db.commit()
                        total_jobs += 1
            except Exception as e:
                print(f"Error syncing {name}: {e}")

        return {"message": f"Synced {total_jobs} new jobs from {len(connectors)} connectors"}
    finally:
        db.close()


# Phase 4: Resume and Cover Letter Models & Endpoints
class CoverLetterRequest(BaseModel):
    job_id: int
    tone: str = "professional"
    resume_override: Optional[ResumeProfile] = None

class CoverLetterResponse(BaseModel):
    cover_letter: str
    match_score: int
    strengths: List[str]
    gaps: List[str]

# Persistent local resume profile
RESUME_PROFILE_PATH = Path("data/resume_profile.json")

def _load_resume_profile() -> Optional[ResumeProfile]:
    if RESUME_PROFILE_PATH.exists():
        try:
            return ResumeProfile.model_validate_json(RESUME_PROFILE_PATH.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None

def _save_resume_profile(profile: ResumeProfile) -> None:
    RESUME_PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESUME_PROFILE_PATH.write_text(profile.model_dump_json(indent=2), encoding="utf-8")

active_resume_profile: Optional[ResumeProfile] = _load_resume_profile()

@app.post("/resume/upload", response_model=ResumeProfile, tags=["resume"])
async def upload_resume(file: UploadFile = File(...)):
    """Upload resume (PDF, DOCX, TXT), parse to structured JSON, and store locally."""
    global active_resume_profile
    contents = await file.read()
    service = ResumeService()
    extracted_text = service.extract_text_from_file(contents, file.filename or "resume.txt")
    profile = service.parse_resume_to_json(extracted_text)
    active_resume_profile = profile
    _save_resume_profile(profile)
    return profile

@app.get("/resume/profile", response_model=Optional[ResumeProfile], tags=["resume"])
async def get_resume_profile():
    """Retrieve currently stored structured resume profile."""
    return active_resume_profile

@app.put("/resume/profile", response_model=ResumeProfile, tags=["resume"])
async def update_resume_profile(profile: ResumeProfile):
    """Save user modifications from the editable review screen."""
    global active_resume_profile
    active_resume_profile = profile
    _save_resume_profile(profile)
    return profile

@app.get("/jobs/{job_id}/match-score", response_model=MatchScoreResult, tags=["resume"])
async def get_job_match_score(job_id: int):
    """Compute match score (0-100), strengths, and gaps for a specific job."""
    db = SessionLocal()
    try:
        sql_job = db.query(SQLJob).filter(SQLJob.id == job_id).first()
        if not sql_job:
            raise HTTPException(status_code=404, detail="Job not found")

        job = Job(**{c.name: getattr(sql_job, c.name) for c in sql_job.__table__.columns})
        resume = active_resume_profile or ResumeProfile()
        service = ResumeService()
        return service.calculate_match_score(job, resume)
    finally:
        db.close()

@app.post("/generate-cover-letter", response_model=CoverLetterResponse, tags=["resume"])
async def generate_cover_letter_endpoint(req: CoverLetterRequest):
    """Generate cover letter grounded in resume facts under 300 words."""
    db = SessionLocal()
    try:
        sql_job = db.query(SQLJob).filter(SQLJob.id == req.job_id).first()
        if not sql_job:
            raise HTTPException(status_code=404, detail="Job not found")

        job = Job(**{c.name: getattr(sql_job, c.name) for c in sql_job.__table__.columns})
        resume = req.resume_override or active_resume_profile or ResumeProfile()
        service = ResumeService()
        match_res = service.calculate_match_score(job, resume)
        letter = service.generate_cover_letter(job, resume, tone=req.tone)

        return CoverLetterResponse(
            cover_letter=letter,
            match_score=match_res.match_score,
            strengths=match_res.strengths,
            gaps=match_res.gaps,
        )
    finally:
        db.close()

def register_connector(name: str, connector: Connector) -> None:
    """Register a connector in the global registry."""
    connectors[name] = connector


# ── Phase 3: Reliability endpoints ──────────────────────────────────────────

@app.get("/stats", tags=["reliability"])
async def get_stats() -> Any:
    """Return aggregate DB stats: total jobs, jobs per source, latest sync."""
    db = SessionLocal()
    try:
        total = db.query(SQLJob).count()
        active = db.query(SQLJob).filter(SQLJob.status == "active").count()
        closed = db.query(SQLJob).filter(SQLJob.status == "closed").count()

        from sqlalchemy import func as sqlfunc
        per_source = db.query(SQLJob.source, sqlfunc.count(SQLJob.id)).group_by(SQLJob.source).all()

        # Latest first_seen_at
        latest = db.query(sqlfunc.max(SQLJob.first_seen_at)).scalar()

        return {
            "total_jobs": total,
            "active_jobs": active,
            "closed_jobs": closed,
            "per_source": {src: cnt for src, cnt in per_source},
            "latest_sync": str(latest) if latest else None,
            "connector_count": len(connectors),
        }
    finally:
        db.close()


@app.post("/admin/validate-links", tags=["reliability"])
async def validate_links(user: dict = Depends(get_current_user)) -> Any:
    """Trigger nightly link validator (marks closed jobs). Requires auth."""
    from app.reliability import reliability_manager
    stats = await reliability_manager.validate_job_links()
    return stats


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)