"""Tests for LinkedIn and Naukri multi-layer connectors."""

import pytest
from app.connectors.search_engine import SearchEngineConnector
from app.connectors.guest_scraper import GuestPageConnector
from app.connectors.alert_email import AlertEmailConnector


def test_search_engine_query_generation():
    """Layer 1 generates 3-5 query variants for LinkedIn and Naukri."""
    connector = SearchEngineConnector()

    li_queries = connector._generate_queries("linkedin", "frontend engineer", "Bangalore")
    assert len(li_queries) >= 3
    assert any("site:linkedin.com/jobs/view" in q for q in li_queries)
    assert any("frontend engineer" in q for q in li_queries)

    naukri_queries = connector._generate_queries("naukri", "data scientist", "Delhi")
    assert len(naukri_queries) >= 3
    assert any("site:naukri.com/job-listings" in q for q in naukri_queries)


def test_search_engine_url_filtering_and_canonicalisation():
    """Layer 1 accurately filters job paths and strips tracking parameters."""
    connector = SearchEngineConnector()

    valid_li = "https://www.linkedin.com/jobs/view/senior-developer-at-google-123456?refId=xyz&trackingId=abc"
    invalid_li = "https://www.linkedin.com/feed/update/urn:li:activity:123"

    assert connector._is_target_job_url(valid_li, "linkedin") is True
    assert connector._is_target_job_url(invalid_li, "linkedin") is False

    canonical = connector._canonicalise_url(valid_li)
    assert canonical == "https://www.linkedin.com/jobs/view/senior-developer-at-google-123456"
    assert "refId" not in canonical
    assert "trackingId" not in canonical


def test_search_engine_relative_date_inference():
    """Relative text posted date parsing ('2 days ago', '3 hours ago')."""
    connector = SearchEngineConnector()

    d1 = connector._parse_relative_date("Posted 2 days ago")
    assert d1 is not None

    d2 = connector._parse_relative_date("Just posted")
    assert d2 is not None


def test_guest_scraper_circuit_breaker():
    """Layer 3 circuit-breaker self-disables after 3 consecutive blocks."""
    scraper = GuestPageConnector(enabled=True)
    assert scraper.enabled is True
    assert scraper._disabled is False

    # Simulate 3 blocks
    scraper._record_block("HTTP 403")
    assert scraper._disabled is False
    scraper._record_block("HTTP 429")
    assert scraper._disabled is False
    scraper._record_block("Captcha challenge")
    assert scraper._disabled is True

    # Health check should reflect disabled state
    health = scraper.health()
    assert health.is_healthy is False
    assert "circuit breaker" in health.last_error.lower()


@pytest.mark.asyncio
async def test_alert_email_template_parsing():
    """Layer 2 parses LinkedIn and Naukri email fixtures and extracts normalized jobs."""
    connector = AlertEmailConnector()

    # Fixture HTML for LinkedIn email
    linkedin_fixture = """
    <div>
        <tr>
            <a href="https://www.linkedin.com/comm/jobs/view/3990001?tracking=email">Staff Cloud Engineer</a>
            <div>Acme Technologies</div>
            <div>Bengaluru, Karnataka, India</div>
        </tr>
    </div>
    """

    jobs = await connector.process_email_content("jobalerts-noreply@linkedin.com", linkedin_fixture)
    assert len(jobs) == 1
    assert jobs[0].title == "Staff Cloud Engineer"
    assert jobs[0].company == "Acme Technologies"
    assert jobs[0].source == "linkedin"
    assert "tracking" not in jobs[0].canonical_url
