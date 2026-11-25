"""Tests for Phase 4: Resume parsing, match score calculation, and cover letter generation."""

import pytest
from app.schemas.job import Job
from app.resume_service import ResumeService, ResumeProfile


def test_resume_rule_based_parsing():
    """Verify resume text parses into structured ResumeProfile."""
    service = ResumeService()
    sample_text = """
    Jane Doe
    jane.doe@example.com | (555) 123-4567
    5+ years of experience as a Software Engineer.
    Core skills: Python, React, FastAPI, Docker, AWS, PostgreSQL.
    Previous experience at Stripe building payments infra.
    B.S. in Computer Science from University of California.
    """
    profile = service.parse_resume_to_json(sample_text)
    assert profile.name == "Jane Doe"
    assert profile.email == "jane.doe@example.com"
    assert profile.years_experience >= 5.0
    assert any("Python" in s for s in profile.key_skills)
    assert any("Fastapi" in s or "React" in s for s in profile.key_skills)


def test_experience_level_inference():
    """Rule-based experience level inference on job listings."""
    service = ResumeService()

    assert service.infer_experience_level("Staff Platform Architect", "") == "lead"
    assert service.infer_experience_level("Senior Python Backend Engineer", "") == "senior"
    assert service.infer_experience_level("Software Engineer Intern (Summer 2026)", "") == "internship"
    assert service.infer_experience_level("Junior Associate Developer", "") == "entry"
    assert service.infer_experience_level("Full Stack Engineer", "") == "mid"


def test_match_score_calculation():
    """Calculates match score (0-100) with strengths and gaps."""
    service = ResumeService()
    job = Job(
        title="Senior Python Backend Developer",
        company="Stripe",
        location="Remote",
        remote=True,
        job_type="full_time",
        experience_level="senior",
        salary="$160k",
        description="Looking for an experienced Python and FastAPI developer with Docker and AWS experience.",
        source="greenhouse",
        apply_url="https://stripe.com/jobs/1",
        canonical_url="https://stripe.com/jobs/1",
        status="active",
    )

    resume = ResumeProfile(
        name="Alex Smith",
        email="alex@example.com",
        years_experience=6.0,
        key_skills=["Python", "FastAPI", "Docker", "AWS"],
        previous_companies=["FinTech Corp"],
    )

    result = service.calculate_match_score(job, resume)
    assert 70 <= result.match_score <= 98
    assert len(result.strengths) >= 1
    assert any("proficiency" in s.lower() or "python" in s.lower() for s in result.strengths)


def test_cover_letter_constraints():
    """Cover letter must remain under 300 words and grounded in resume facts."""
    service = ResumeService()
    job = Job(
        title="Frontend Engineer",
        company="Airbnb",
        location="San Francisco, CA",
        remote=True,
        job_type="full_time",
        experience_level="mid",
        salary="$140k",
        description="Build responsive UI in React and TypeScript.",
        source="lever",
        apply_url="https://airbnb.com/jobs/2",
        canonical_url="https://airbnb.com/jobs/2",
        status="active",
    )

    resume = ResumeProfile(
        name="Taylor Reed",
        years_experience=3.0,
        key_skills=["React", "TypeScript", "Tailwind"],
        previous_companies=["Studio Interactive"],
        achievements=["Improved web latency by 35%"],
    )

    letter = service.generate_cover_letter(job, resume, tone="enthusiastic")
    words = letter.split()
    assert len(words) <= 300
    assert "Taylor Reed" in letter
    assert "Airbnb" in letter
    assert "React" in letter
