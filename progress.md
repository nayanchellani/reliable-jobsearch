# Progress Log — Reliable JobSearch

**Last updated:** 2025-08-16 (auto-generated)

---

## Project State Summary

**Stack:** FastAPI + SQLAlchemy + SQLite + React/Vite/Tailwind + Docker Compose

**Core features implemented:**
- ✅ Job aggregation from 11 free connectors (Remotive, Arbeitnow, RemoteOK, Adzuna, Jooble, JSearch, Greenhouse, Lever, Ashby, SearchEngine, CareerCrawler, AlertEmail, GuestScraper)
- ✅ JWT-based auth with DB-backed sessions (User, Session, UserSettings tables)
- ✅ Background sync scheduler (APScheduler, 30-min interval for free connectors)
- ✅ Manual sync endpoint (`POST /connectors/sync`)
- ✅ Per-connector health dashboard (`GET /connectors/health`)
- ✅ DB stats endpoint (`GET /stats`)
- ✅ Deduplication (canonical URL + fuzzy match)
- ✅ Resume upload/parse (PDF/DOCX/TXT → structured JSON via LLM)
- ✅ Match scoring (0-100, strengths/gaps)
- ✅ Cover letter generation (LLM-grounded, <300 words, multiple tones)
- ✅ Link validator (`POST /admin/validate-links`)
- ✅ LinkedIn/Naukri 3-layer connectors (SearchEngine, AlertEmail, GuestScraper)

---

## Git Status

**Current commit:** `e773a12` — feat: initial commit
**Uncommitted changes:**
- `app/api/main.py` — modified (14 lines changed)
- `app/connectors/lever.py` — modified (4 lines)
- `frontend/package-lock.json` — deleted (ghost file from Windows path issue)

---

## File Tree (key paths)

```
reliable-jobsearch/
├── app/
│   ├── api/
│   │   ├── main.py          # FastAPI app, lifespan, all routes
│   │   └── auth.py          # JWT auth, settings API
│   ├── connectors/
│   │   ├── base.py          # Abstract Connector (async fetch, rate limit)
│   │   ├── greenhouse.py
│   │   ├── lever.py
│   │   ├── ashby.py
│   │   ├── remotive.py
│   │   ├── arbeitnow.py
│   │   ├── remoteok.py
│   │   ├── adzuna.py
│   │   ├── jooble.py
│   │   ├── jsearch.py
│   │   ├── career_crawler.py
│   │   ├── alert_email.py
│   │   ├── search_engine.py  # SearXNG/DDG for LinkedIn/Naukri
│   │   ├── alert_email.py    # Gmail/IMAP alert parser
│   │   └── guest_scraper.py  # Layer 3 (OFF by default)
│   ├── db/
│   │   └── base.py           # SQLAlchemy: User, Session, Job, UserSettings
│   ├── schemas/
│   │   └── job.py            # Job, JobSearchFilters, ConnectorHealth
│   ├── dedupe.py             # Canonical URL + fuzzy match
│   ├── resume_service.py     # Parse, match score, cover letter
│   ├── reliability.py        # Link validator, zero-result alerts
│   └── prompts/
│       └── cover_letter.md
├── frontend/
│   └── src/App.tsx           # React + Vite + Tailwind UI
├── tests/
│   ├── stubs/                # Offline shims (pydantic, httpx, bs4)
│   ├── test_dedupe.py
│   ├── test_linkedin_naukri.py
│   └── test_resume_cover_letter.py
├── .env                      # Local secrets (gitignored)
├── .env.example
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── config.yaml
└── README.md
```

---

## Key Architectural Decisions

1. **No paid services** — All connectors use free tiers or public APIs.
2. **Local-first** — SQLite + local file storage for resume/cover letter.
3. **JWT auth** — Stateless tokens, HttpOnly cookie, DB-backed User/Session tables.
3. **Connector pattern** — Abstract `Connector` base with async `fetch()`, rate limiting, health check.
4. **Dedupe** — Canonical URL exact match → fuzzy (company+title+location) → merge sources, prefer ATS apply_url.
5. **Background sync** — APScheduler runs free connectors every 30 min; manual sync via `POST /connectors/sync`.
6. **LLM** — FreeLLMAPI router (OpenAI-compatible); all calls have template fallback.
7. **Frontend** — React + Vite + Tailwind; design tokens from spec (`--primary #E96832`, `--background #FFF9F3`).

---

## Tests

```bash
pytest          # 15 tests, offline via stubs in tests/stubs/
```

Coverage:
- `test_dedupe.py` — canonical URL + fuzzy merge
- `test_linkedin_naukri.py` — 3-layer connector logic
- `test_resume_cover_letter.py` — resume parse, match score, cover letter

---

## Current Status (2025-08-16)

| Component | Status |
|-----------|--------|
| Backend API | ✅ Running (port 8000) |
| Frontend | ✅ Running (port 5173) |
| DB (SQLite) | ✅ Auto-migrated |
| Auth (JWT) | ✅ Working |
| Free connectors | ✅ Registered (11) |
| ATS connectors | ⚠️ Need tokens in Settings |
| Background sync | ✅ Scheduler active |
| Frontend UI | ✅ Design tokens applied |
| Tests | ✅ 15 passing |

---

## Next Steps (if continuing)

1. Add connector health dashboard tab in Frontend (`/connectors/health` → table view)
2. Clean ghost folders (`D:codereliable-jobsearch...` Windows artifacts)
3. Verify ATS connectors with real tokens
4. Add date range filters to `/jobs`
5. Add pagination metadata to `/jobs` response
6. Run full test suite in CI