# Cover Letter Prompt

## Purpose
Generate a tailored cover letter for a specific job application, grounded only in the user's resume facts.

## Input Variables
- `job_title`: The job title being applied for
- `company_name`: The target company
- `resume_json`: Structured resume data (parsed from user's uploaded resume)
- `job_match_score`: Match score 0-100 from the job matching system
- `job_strengths`: List of strengths matching this job
- `job_gaps`: List of gaps/experience missing for this job
- `tone`: One of "professional", "enthusiastic", "concise"

## Constraints
- Maximum 300 words
- Never invent employers, skills, or numbers
- Ground ONLY in resume facts from resume_json
- Must include a strong opening hook referencing the specific role
- Must close with a clear call-to-action
- Tone must match the selected option

## Example Output Structure
```
[Opening: Hook referencing the role and relevant experience from resume]

[Body: 2-3 paragraphs highlighting specific matches between resume skills and job requirements, using only facts from resume_json]

[Closing: Confident call-to-action, expressing enthusiasm for discussion]
```

## LLM Prompt Template
```
You are writing a cover letter for the position of {{job_title}} at {{company_name}}.

Respond ONLY with the cover letter text. Do not include analysis, apologies, or meta commentary.

Resume facts (ground truth only - never invent):
- Name: {{resume_json.name or "not provided"}}
- Years experience: {{resume_json.years_experience or "not provided"}}
- Key skills: {{", ".join(resume_json.key_skills or [])}}
- Notable achievements: {{", ".join(resume_json.achievements or [])}}
- Previous companies: {{", ".join(resume_json.previous_companies or [])}}

Job match: {{job_match_score}}/100
Strengths: {{", ".join(job_strengths or [])}}
Gaps: {{", ".join(job_gaps or [])}}

Tone: {{tone}}

Constraints:
- Max 300 words
- Ground EVERY claim in the resume facts above
- Never invent employers, skills, or Quantifiable achievements
- Keep under 300 words
- Professional tone: {{tone}}

Write the cover letter now.
```