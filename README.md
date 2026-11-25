# Job Aggregator

A local-first, open-source (MIT) job aggregation portal.  
One command to run. No paid services required.

---

## Quick start

```bash
# 1. Clone
git clone <repo-url> && cd reliable-jobsearch

# 2. Backend
cp .env.example .env          # fill in LLM_BASE_URL etc.
pip install -r requirements.txt
uvicorn app.api.main:app --reload --port 8000

# 3. Frontend (separate terminal)
cd frontend
npm install
npm run dev                   # → http://localhost:5173
```

The backend fetches jobs from free connectors automatically on startup and every 30 minutes.  
To trigger a manual fetch, click **Sync now** in the Search tab.

---

## Architecture

```
app/
  api/
    main.py        – FastAPI routes, lifespan scheduler
    auth.py        – JWT auth, settings API
  connectors/
    base.py        – Abstract Connector base class
    remotive.py    – Remotive (free, no key)
    arbeitnow.py   – Arbeitnow (free, no key)
    remoteok.py    – RemoteOK (free, no key)
    greenhouse.py  – Greenhouse ATS (token required)
    lever.py       – Lever ATS (token required)
    ashby.py       – Ashby ATS (name required)
    adzuna.py      – Adzuna API (free key)
    jooble.py      – Jooble API (free key)
    jsearch.py     – JSearch / RapidAPI (free key)
    search_engine.py – LinkedIn + Naukri via SearXNG/DDG (Layer 1)
    alert_email.py   – Gmail / IMAP job alert parser (Layer 2)
    guest_scraper.py – Direct scraping, OFF by default (Layer 3)
    career_crawler.py – Generic career page crawler
  db/
    base.py        – SQLAlchemy models (SQLite)
  schemas/
    job.py         – Pydantic Job, JobSearchFilters, ConnectorHealth
  dedupe.py        – Canonical URL + fuzzy deduplication
  resume_service.py– Resume parsing, match scoring, cover letter generation
  reliability.py   – Link validator, zero-result alerting
  prompts/
    cover_letter.md – Cover letter LLM prompt template
frontend/
  src/App.tsx      – React + Vite + Tailwind UI
tests/
  stubs/           – Minimal offline shims (pydantic, httpx, bs4)
  test_dedupe.py
  test_linkedin_naukri.py
  test_resume_cover_letter.py
```

---

## Free connectors (no API key)

| Source | Type | Key required |
|--------|------|-------------|
| Remotive | Remote jobs API | No |
| Arbeitnow | European jobs API | No |
| RemoteOK | Remote jobs API | No |
| SearchEngine (LinkedIn/Naukri) | Search engine scraping | No (SearXNG optional) |

## Optional connectors (free keys)

| Source | Sign up |
|--------|---------|
| Adzuna | https://developer.adzuna.com |
| Jooble | https://jooble.org/api/about |
| JSearch | https://rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch |

## ATS connectors (company token)

| ATS | How to get token |
|-----|-----------------|
| Greenhouse | Your company's Greenhouse board slug |
| Lever | Your company's Lever company slug |
| Ashby | Your company's Ashby board name |

---

## LLM configuration

Set in `.env` or via Settings in the UI:

```env
LLM_BASE_URL=https://api.openai.com/v1   # or any OpenAI-compatible endpoint
LLM_API_KEY=sk-...
LLM_MODEL=gpt-4o-mini
```

Cover letters are grounded only in resume facts. The LLM call is optional — a template fallback is used if the call fails.

---

## LinkedIn & Naukri

Three layers, configured in `config.yaml` / `.env`:

| Layer | Default | Description |
|-------|---------|-------------|
| SearchEngineConnector | On | Queries via SearXNG or DuckDuckGo, extracts JSON-LD |
| AlertEmailConnector | On (if IMAP set) | Parses job alert emails from LinkedIn/Naukri/Indeed |
| GuestPageConnector | **Off** | Direct scraping; set `ENABLE_GUEST_SCRAPING=true` to enable |

---

## Running tests

```bash
pytest          # uses pytest.ini (PYTHONPATH=. already set)
```

All 15 tests run offline using minimal stubs in `tests/stubs/`.

---

## Adding a connector

See [.claude/skills/add-connector/SKILL.md](.claude/skills/add-connector/SKILL.md).

---

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/jobs` | Search & filter jobs |
| POST | `/connectors/sync` | Trigger manual sync |
| GET | `/connectors/health` | Per-connector health |
| GET | `/stats` | DB stats (total, per source) |
| POST | `/resume/upload` | Parse resume PDF/DOCX |
| GET | `/resume/profile` | Get stored resume |
| PUT | `/resume/profile` | Update resume |
| GET | `/jobs/{id}/match-score` | Match score for a job |
| POST | `/generate-cover-letter` | Generate tailored cover letter |
| POST | `/admin/validate-links` | Mark closed jobs (auth required) |

---

## License

MIT © 2026
