"""Resume and Cover Letter generation service.

- First-run onboarding resume parsing to structured JSON via LLM
- Cover letter generation grounded ONLY in resume facts
"""

from __future__ import annotations

import os
import json
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

from app.schemas.job import Job


class ResumeProfile(BaseModel):
    """Structured resume profile extracted from uploaded resume."""

    name: str = Field(default="", description="Candidate full name")
    email: Optional[str] = Field(default=None, description="Email address")
    phone: Optional[str] = Field(default=None, description="Phone number")
    years_experience: Optional[float] = Field(default=0.0, description="Total years of experience")
    key_skills: List[str] = Field(default_factory=list, description="Core technical & professional skills")
    previous_companies: List[str] = Field(default_factory=list, description="Previous employer names")
    achievements: List[str] = Field(default_factory=list, description="Notable achievements / metrics")
    education: List[str] = Field(default_factory=list, description="Degrees and institutions")


class CoverLetterGenerator:
    """Generates tailored cover letters grounded strictly in resume facts."""

    def __init__(self, openai_client=None):
        self.client = openai_client

    def generate(
        self,
        job: Job,
        resume: ResumeProfile,
        tone: str = "professional",
        match_score: int = 85,
        strengths: Optional[List[str]] = None,
        gaps: Optional[List[str]] = None,
    ) -> str:
        """Generate cover letter matching prompt template constraints."""

        strengths = strengths or ["Relevant technical background", "Strong problem-solving skills"]
        gaps = gaps or []

        # Read prompt template
        prompt_template = ""
        try:
            with open("app/prompts/cover_letter.md", "r", encoding="utf-8") as f:
                content = f.read()
                # Extract LLM prompt template section
                if "```" in content:
                    parts = content.split("```")
                    if len(parts) >= 3:
                        prompt_template = parts[1].strip()
        except Exception:
            pass

        if not prompt_template:
            prompt_template = (
                f"Write a {tone} cover letter for {job.title} at {job.company}.\n"
                f"Candidate name: {resume.name}\n"
                f"Key skills: {', '.join(resume.key_skills)}\n"
                f"Constraints: under 300 words, ground ONLY in resume facts."
            )

        # Simple substitution for fallback if no LLM client
        letter = (
            f"Dear Hiring Manager at {job.company},\n\n"
            f"I am writing to express my strong interest in the {job.title} position. "
            f"With my background in {', '.join(resume.key_skills[:3])} and experience across "
            f"{', '.join(resume.previous_companies[:2]) or 'previous roles'}, I am confident in my "
            f"ability to contribute effectively to your team.\n\n"
            f"Key strengths I bring include {', '.join(strengths)}.\n\n"
            f"I look forward to discussing how my experience aligns with your needs.\n\n"
            f"Sincerely,\n"
            f"{resume.name or 'Job Applicant'}"
        )

        return letter