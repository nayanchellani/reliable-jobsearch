"""FastAPI main application for the Job Aggregator."""

from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from pathlib import Path
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional

from fastapi import FastAPI, HTTPException, Query, Depends, UploadFile, File, BackgroundTasks
from fastapi.responses import PlainTextResponse, Response
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from app.db.base import Base, Job as SQLJob, ConnectorSyncRun, engine, SessionLocal
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
_sync_lock = asyncio.Lock()
_active_sync_task: asyncio.Task | None = None
_ACTIVE_SYNC_STATUSES = {"pending", "running"}


def register_connector(name: str, connector: Connector) -> None:
    """Register a connector in the global registry."""
    connectors[name] = connector


def _job_to_dict(job: Job) -> dict:
    data = job.model_dump()
    raw = data.get("raw")
    if isinstance(raw, str):
        try:
            data["raw"] = json.loads(raw)
        except Exception:
            data["raw"] = {}
    return data


def _upsert_job(db: Session, job: Job) -> bool:
    existing = db.query(SQLJob).filter(SQLJob.canonical_url == job.canonical_url).first()
    now = datetime.now(timezone.utc)
    payload = _job_to_dict(job)
    payload["raw"] = json.dumps(payload.get("raw") or {})
    payload["first_seen_at"] = payload.get("first_seen_at") or now
    payload["posted_at"] = payload.get("posted_at")
    if existing:
        for field, value in payload.items():
            if field == "id":
                continue
            setattr(existing, field, value)
        existing.updated_at = now
        db.commit()
        return False
    db_job = SQLJob(**{k: v for k, v in payload.items() if k != "id"})
    db.add(db_job)
    db.commit()
    return True


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
                        _upsert_job(db, job)
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


@app.get("/jobs", response_model=Dict[str, Any], tags=["search"])
async def search_jobs(
    q: Optional[str] = Query(default=None, description="Free text search"),
    location: Optional[str] = Query(default=None, description="Location filter (city/region)"),
    job_type: Optional[str] = Query(default=None, description="Job type filter"),
    experience_level: Optional[str] = Query(default=None, description="Experience level filter"),
    remote: Optional[bool] = Query(default=None, description="Remote filter"),
    work_mode: Optional[str] = Query(default=None, description="remote|onsite|hybrid"),
    source: Optional[str] = Query(default=None, description="Source filter"),
    posted_within: Optional[str] = Query(default=None, description="24h|week|month"),
    sort: str = Query(default="posted_at_desc", description="Sort order"),
    page: int = Query(default=1, ge=1, description="Page number"),
    per_page: int = Query(default=20, ge=1, le=100, description="Items per page"),
    user: dict = Depends(get_current_user),
) -> Any:
    """Search jobs with full filter support and pagination metadata."""
    allowed_work_modes = {"remote", "onsite", "hybrid"}
    allowed_posted = {"24h", "week", "month"}
    allowed_exp = {"fresher", "junior", "mid", "senior", "lead", "principal", "director", "entry"}
    allowed_job_types = {"full_time", "part_time", "contract", "internship"}
    if work_mode and work_mode not in allowed_work_modes:
        raise HTTPException(status_code=400, detail="Invalid work_mode")
    if posted_within and posted_within not in allowed_posted:
        raise HTTPException(status_code=400, detail="Invalid posted_within")
    if experience_level and experience_level not in allowed_exp:
        raise HTTPException(status_code=400, detail="Invalid experience_level")
    if job_type and job_type not in allowed_job_types:
        raise HTTPException(status_code=400, detail="Invalid job_type")

    db = SessionLocal()
    try:
        query = db.query(SQLJob)
        if q:
            like = f"%{q.strip()}%"
            query = query.filter(
                (SQLJob.title.ilike(like))
                | (SQLJob.company.ilike(like))
                | (SQLJob.description.ilike(like))
                | (SQLJob.location.ilike(like))
            )
        if location:
            query = query.filter(SQLJob.location.ilike(f"%{location.strip()}%"))
        if remote is not None:
            query = query.filter(SQLJob.remote == remote)
        if work_mode == "remote":
            query = query.filter(SQLJob.remote.is_(True))
        elif work_mode == "onsite":
            query = query.filter(SQLJob.remote.is_(False))
            query = query.filter(~SQLJob.location.ilike("%hybrid%"))
            query = query.filter(~SQLJob.title.ilike("%hybrid%"))
            query = query.filter(~SQLJob.description.ilike("%hybrid%"))
        elif work_mode == "hybrid":
            query = query.filter(
                (SQLJob.location.ilike("%hybrid%"))
                | (SQLJob.title.ilike("%hybrid%"))
                | (SQLJob.description.ilike("%hybrid%"))
            )
        if source:
            query = query.filter(SQLJob.source == source)
        if job_type:
            query = query.filter(SQLJob.job_type == job_type)
        if experience_level:
            query = query.filter(SQLJob.experience_level == experience_level)
        if posted_within:
            now = datetime.now(timezone.utc)
            delta = {"24h": timedelta(hours=24), "week": timedelta(days=7), "month": timedelta(days=30)}[posted_within]
            query = query.filter((SQLJob.posted_at >= now - delta) | (SQLJob.first_seen_at >= now - delta))

        if sort == "posted_at_desc":
            query = query.order_by(SQLJob.posted_at.desc().nullslast(), SQLJob.first_seen_at.desc().nullslast(), SQLJob.id.desc())
        elif sort == "posted_at_asc":
            query = query.order_by(SQLJob.posted_at.asc().nullslast(), SQLJob.first_seen_at.asc().nullslast(), SQLJob.id.asc())
        elif sort == "title_asc":
            query = query.order_by(SQLJob.title.asc(), SQLJob.id.desc())
        elif sort == "title_desc":
            query = query.order_by(SQLJob.title.desc(), SQLJob.id.desc())
        else:
            query = query.order_by(SQLJob.first_seen_at.desc().nullslast(), SQLJob.id.desc())

        total = query.count()
        db_jobs = query.offset((page - 1) * per_page).limit(per_page).all()
        jobs = []
        for sj in db_jobs:
            jobs.append(Job(
                id=sj.id, title=sj.title, company=sj.company, location=sj.location, remote=sj.remote,
                job_type=sj.job_type, experience_level=sj.experience_level, salary=sj.salary, description=sj.description,
                posted_at=sj.posted_at, first_seen_at=sj.first_seen_at, source=sj.source, apply_url=sj.apply_url,
                canonical_url=sj.canonical_url, status=sj.status,
                raw=json.loads(sj.raw) if isinstance(sj.raw, str) else (sj.raw or {}),
            ))
        return {"jobs": jobs, "total": total, "page": page, "per_page": per_page, "pages": max(1, (total + per_page - 1) // per_page)}
    finally:
        db.close()


@app.post("/jobs", response_model=Job, tags=["ingest"])
async def ingest_job(job: Job, user: dict = Depends(get_current_user)) -> Any:
    """Ingest a single job into the database. Requires authentication."""
    db = SessionLocal()
    try:
        _upsert_job(db, job)
        saved = db.query(SQLJob).filter(SQLJob.canonical_url == job.canonical_url).first()
        return Job(**{c.name: (json.loads(getattr(saved, c.name)) if c.name == "raw" and isinstance(getattr(saved, c.name), str) else getattr(saved, c.name)) for c in saved.__table__.columns})
    finally:
        db.close()


@app.get("/connectors/health", response_model=List[ConnectorHealth], tags=["connectors"])
async def connector_health(user: dict = Depends(get_current_user)) -> Any:
    """Get health status for all registered connectors."""
    health_list = []
    for name, connector in connectors.items():
        try:
            h = connector.health()
            h.name = name
            health_list.append(h)
        except Exception as e:
            health_list.append(ConnectorHealth(name=name, is_healthy=False, last_error=str(e)))
    return health_list


def _sync_run_to_dict(run: ConnectorSyncRun) -> Dict[str, Any]:
    return {
        "sync_id": run.sync_id,
        "status": run.status,
        "query": run.query or "",
        "location": run.location or "",
        "requested_by": run.requested_by,
        "total_new": run.total_new or 0,
        "results": run.results_json or {},
        "error": run.error,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "updated_at": run.updated_at.isoformat() if run.updated_at else None,
    }


def _get_active_sync_run(db: Session) -> ConnectorSyncRun | None:
    return db.query(ConnectorSyncRun).filter(ConnectorSyncRun.status.in_(list(_ACTIVE_SYNC_STATUSES))).order_by(ConnectorSyncRun.created_at.desc()).first()


async def _execute_sync_run(sync_id: str) -> None:
    global _active_sync_task
    connector_timeout_s = 45.0
    db = SessionLocal()
    run = db.query(ConnectorSyncRun).filter(ConnectorSyncRun.sync_id == sync_id).first()
    if not run:
        db.close()
        return
    run.status = "running"
    run.started_at = datetime.now(timezone.utc)
    run.error = None
    db.commit()
    query = run.query or ""
    location = run.location or ""
    db.close()

    results: Dict[str, Any] = {}
    total_new = 0
    any_success = False
    any_error = False
    cancelled = False
    try:
        async with _sync_lock:
            for name, connector in connectors.items():
                started = time.monotonic()
                try:
                    jobs = await asyncio.wait_for(
                        connector.fetch(query=query, location=location or None),
                        timeout=connector_timeout_s,
                    )
                    added = 0
                    dbi = SessionLocal()
                    try:
                        for job in jobs:
                            if _upsert_job(dbi, job):
                                added += 1
                    finally:
                        dbi.close()
                    total_new += added
                    any_success = True
                    results[name] = {
                        "fetched": len(jobs),
                        "new": added,
                        "duration_ms": int((time.monotonic() - started) * 1000),
                        "status": "ok",
                    }
                except asyncio.CancelledError:
                    cancelled = True
                    any_error = True
                    results[name] = {
                        "error": "cancelled",
                        "duration_ms": int((time.monotonic() - started) * 1000),
                        "status": "cancelled",
                    }
                    break
                except asyncio.TimeoutError:
                    any_error = True
                    results[name] = {
                        "error": f"timeout after {int(connector_timeout_s)}s",
                        "duration_ms": int((time.monotonic() - started) * 1000),
                        "status": "timeout",
                    }
                except Exception as e:
                    any_error = True
                    results[name] = {
                        "error": str(e),
                        "duration_ms": int((time.monotonic() - started) * 1000),
                        "status": "error",
                    }

                dbu = SessionLocal()
                try:
                    r = dbu.query(ConnectorSyncRun).filter(ConnectorSyncRun.sync_id == sync_id).first()
                    if r:
                        r.results_json = results
                        r.total_new = total_new
                        r.updated_at = datetime.now(timezone.utc)
                        dbu.commit()
                finally:
                    dbu.close()

        if not cancelled and total_new > 0:
            try:
                from app.services.enrichment import enrich_recent_jobs
                asyncio.create_task(enrich_recent_jobs())
            except Exception:
                pass
    except asyncio.CancelledError:
        cancelled = True
    finally:
        dbf = SessionLocal()
        try:
            r = dbf.query(ConnectorSyncRun).filter(ConnectorSyncRun.sync_id == sync_id).first()
            if r:
                r.results_json = results
                r.total_new = total_new
                r.finished_at = datetime.now(timezone.utc)
                r.updated_at = datetime.now(timezone.utc)
                if cancelled:
                    r.status = "cancelled"
                    r.error = "cancelled"
                elif any_success and any_error:
                    r.status = "partially_completed"
                elif any_success:
                    r.status = "completed"
                elif any_error:
                    r.status = "failed"
                    r.error = "all connectors failed"
                else:
                    r.status = "completed"
                dbf.commit()
        finally:
            dbf.close()
            if _active_sync_task is asyncio.current_task():
                _active_sync_task = None


@app.post("/connectors/sync", status_code=202, tags=["connectors"])
async def sync_connectors(
    query: Optional[str] = Query(default=""),
    location: Optional[str] = Query(default=""),
    background_tasks: BackgroundTasks = None,
    user: dict = Depends(get_current_user),
) -> Any:
    """Start async connector sync. Returns 202 with sync_id."""
    global _active_sync_task
    if _active_sync_task and _active_sync_task.done():
        _active_sync_task = None

    db = SessionLocal()
    try:
        active = _get_active_sync_run(db)
        if active or _sync_lock.locked() or _active_sync_task is not None:
            existing = active.sync_id if active else None
            raise HTTPException(status_code=409, detail={"message": "Sync already in progress", "sync_id": existing})
        sync_id = uuid.uuid4().hex
        run = ConnectorSyncRun(
            sync_id=sync_id,
            status="pending",
            query=(query or "").strip() or None,
            location=(location or "").strip() or None,
            requested_by=(user or {}).get("email") if isinstance(user, dict) else None,
            total_new=0,
            results_json={},
        )
        db.add(run)
        db.commit()
    finally:
        db.close()

    _active_sync_task = asyncio.create_task(_execute_sync_run(sync_id))
    return {"sync_id": sync_id, "status": "pending", "status_url": f"/connectors/sync/{sync_id}"}


@app.get("/connectors/sync/history", tags=["connectors"])
async def sync_history(limit: int = Query(default=20, ge=1, le=100), user: dict = Depends(get_current_user)) -> Any:
    db = SessionLocal()
    try:
        rows = db.query(ConnectorSyncRun).order_by(ConnectorSyncRun.created_at.desc()).limit(limit).all()
        return {"items": [_sync_run_to_dict(r) for r in rows]}
    finally:
        db.close()


@app.get("/connectors/sync/{sync_id}", tags=["connectors"])
async def sync_status(sync_id: str, user: dict = Depends(get_current_user)) -> Any:
    db = SessionLocal()
    try:
        run = db.query(ConnectorSyncRun).filter(ConnectorSyncRun.sync_id == sync_id).first()
        if not run:
            raise HTTPException(status_code=404, detail="Sync run not found")
        return _sync_run_to_dict(run)
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
async def upload_resume(file: UploadFile = File(...), user: dict = Depends(get_current_user)):
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
async def get_resume_profile(user: dict = Depends(get_current_user)):
    """Retrieve currently stored structured resume profile."""
    return active_resume_profile

@app.put("/resume/profile", response_model=ResumeProfile, tags=["resume"])
async def update_resume_profile(profile: ResumeProfile, user: dict = Depends(get_current_user)):
    """Save user modifications from the editable review screen."""
    global active_resume_profile
    active_resume_profile = profile
    _save_resume_profile(profile)
    return profile

@app.get("/jobs/{job_id}/match-score", response_model=MatchScoreResult, tags=["resume"])
async def get_job_match_score(job_id: int, user: dict = Depends(get_current_user)):
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
async def generate_cover_letter_endpoint(req: CoverLetterRequest, user: dict = Depends(get_current_user)):
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

# ── Phase 3: Reliability endpoints ──────────────────────────────────────────

@app.get("/stats", tags=["reliability"])
async def get_stats(user: dict = Depends(get_current_user)) -> Any:
    """Return aggregate DB stats. Requires auth."""
    db = SessionLocal()
    try:
        total = db.query(SQLJob).count()
        active = db.query(SQLJob).filter(SQLJob.status == "active").count()
        closed = db.query(SQLJob).filter(SQLJob.status == "closed").count()
        from sqlalchemy import func as sqlfunc
        per_source = db.query(SQLJob.source, sqlfunc.count(SQLJob.id)).group_by(SQLJob.source).all()
        latest = db.query(sqlfunc.max(SQLJob.first_seen_at)).scalar()
        return {
            "total_jobs": total, "active_jobs": active, "closed_jobs": closed,
            "per_source": {src: cnt for src, cnt in per_source},
            "latest_sync": str(latest) if latest else None, "connector_count": len(connectors),
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