from app.connectors.search_engine import SearchEngineConnector

def test_yc_query_generation_dynamic():
    c=SearchEngineConnector()
    q1=c._generate_queries("ycombinator","AI Engineer","India")
    assert q1[0]=='site:ycombinator.com/jobs "AI Engineer" India'
    assert all("site:ycombinator.com/jobs" in q for q in q1)
    q2=c._generate_queries("ycombinator","","Remote")
    assert any("software engineer" in q.lower() or "ai engineer" in q.lower() for q in q2)
    assert len(q2)<=5

def test_yc_url_validation():
    c=SearchEngineConnector()
    assert c._is_target_job_url("https://www.ycombinator.com/jobs/role/123","ycombinator")
    assert not c._is_target_job_url("https://www.ycombinator.com/companies/foo","ycombinator")
    assert not c._is_target_job_url("https://example.com/jobs/123","ycombinator")

def test_yc_target_included():
    c=SearchEngineConnector(enable_linkedin=False, enable_naukri=False)
    assert c._is_target_job_url("https://ycombinator.com/jobs/123","ycombinator")
