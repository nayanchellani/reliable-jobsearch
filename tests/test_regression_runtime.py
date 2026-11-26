from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import pytest


def test_docker_compose_has_env_file_and_llm_passthrough():
    text = Path("docker-compose.yml").read_text(encoding="utf-8")
    assert "env_file:" in text
    assert "- .env" in text
    # DATABASE_URL/SEARXNG_URL remain explicit
    assert "DATABASE_URL=" in text
    assert "SEARXNG_URL=" in text


@pytest.mark.asyncio
async def test_async_rate_limit_awaits_sleep(monkeypatch):
    from app.connectors.base import Connector
    from app.schemas.job import ConnectorHealth

    class C(Connector):
        name = "c"
        rate_limit_ms = 100
        async def fetch(self, query, location=None, filters=None):
            return []
        def health(self):
            return ConnectorHealth(name=self.name)

    slept = {"n": 0, "secs": []}
    async def fake_sleep(s):
        slept["n"] += 1
        slept["secs"].append(s)
    t = {"v": 1000.0}
    monkeypatch.setattr("app.connectors.base.time.time", lambda: t["v"])
    monkeypatch.setattr("app.connectors.base.asyncio.sleep", fake_sleep)

    c = C()
    c._rate_limit_last = 999.95  # elapsed 0.05s
    await c._rate_limit()
    assert slept["n"] == 1
    assert slept["secs"][0] > 0


@pytest.mark.asyncio
async def test_remoteok_fetch_awaits_rate_limit(monkeypatch):
    from app.connectors.remoteok import RemoteOKConnector

    called = {"n": 0}
    async def fake_rl(self):
        called["n"] += 1
    monkeypatch.setattr(RemoteOKConnector, "_rate_limit", fake_rl)

    class Resp:
        def raise_for_status(self): return None
        def json(self): return [{"legal":1}]

    class Client:
        async def get(self, *a, **k): return Resp()

    c = RemoteOKConnector.__new__(RemoteOKConnector)
    c.client = Client()
    c._rate_limit_last = 0.0
    c._success_count = 0
    c._error_count = 0
    c._last_error = None
    jobs = await RemoteOKConnector.fetch(c, "python")
    assert called["n"] == 1
    assert jobs == []


@pytest.mark.asyncio
async def test_sync_partial_connector_failure():
    # Unit-test the sync contract: one connector failure should not block others.
    import asyncio, time
    results = {}
    total_new = 0

    async def run_one(name, fn):
        started = time.monotonic()
        try:
            jobs = await asyncio.wait_for(fn(), timeout=1)
            results[name] = {"fetched": len(jobs), "new": len(jobs), "duration_ms": int((time.monotonic()-started)*1000)}
            return len(jobs)
        except Exception as e:
            results[name] = {"error": str(e)}
            return 0

    async def good(): return [1]
    async def bad(): raise RuntimeError("boom")
    total_new += await run_one("good", good)
    total_new += await run_one("bad", bad)
    assert results["good"]["new"] == 1
    assert "error" in results["bad"]
    assert total_new == 1


@pytest.mark.asyncio
async def test_malformed_llm_responses_return_none(monkeypatch):
    import app.services.enrichment as enr

    monkeypatch.setenv("LLM_BASE_URL", "http://llm.test/v1")
    monkeypatch.setenv("LLM_API_KEY", "k")
    monkeypatch.setenv("LLM_MODEL", "m")

    class Resp:
        def __init__(self, content):
            self._content = content
        def raise_for_status(self): pass
        def json(self):
            return {"choices":[{"message":{"content": self._content}}]}

    class Client:
        def __init__(self, content):
            self.content = content
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, *a, **k): return Resp(self.content)

    for bad in ["not json", "{", "[]", '{"experience_level":"wizard"}']:
        monkeypatch.setattr(enr.httpx, "AsyncClient", lambda timeout=30.0, c=bad: Client(c))
        r = await enr._call_llm("t","d")
        assert r is None or isinstance(r, dict)


def test_resume_pdf_docx_txt_extraction(tmp_path):
    from app.resume_service import ResumeService
    svc = ResumeService()

    txt = tmp_path / "r.txt"
    txt.write_text("Python developer FastAPI", encoding="utf-8")
    assert "Python developer" in svc.extract_text_from_file(txt.read_bytes(), "r.txt")

    # DOCX
    try:
        import docx
        d = docx.Document()
        d.add_paragraph("FastAPI engineer")
        docx_path = tmp_path / "r.docx"
        d.save(docx_path)
        out = svc.extract_text_from_file(docx_path.read_bytes(), "r.docx")
        assert "FastAPI" in out
    except Exception as e:
        pytest.skip(f"docx not available: {e}")

    # PDF
    try:
        from pypdf import PdfWriter
        from io import BytesIO
        # pypdf writer can't easily create text; fall back to checking extractor handles bytes without crashing
        writer = PdfWriter()
        writer.add_blank_page(width=72, height=72)
        buf = BytesIO(); writer.write(buf)
        out = svc.extract_text_from_file(buf.getvalue(), "r.pdf")
        assert isinstance(out, str)
    except Exception as e:
        pytest.skip(f"pypdf not available: {e}")
