"""Agent 1 prompts, version 2: requirements now carry a category.

The only change from v1 is one instruction in the matching call -- each
requirement is filed as a skill, experience, education, certification, language
or location requirement, so a job analysis can show the must-haves grouped the
way a recruiter reads them. The writing review is unchanged and reused.

A new version rather than an edit to v1, because the prompt wording is part of
what produced every stored analysis. Analyses made under v1 keep saying so.
"""
from __future__ import annotations

from app.agents.analyst.industries import prompt_fragment
from app.prompts import NO_FABRICATION, untrusted_data_rule
from app.prompts.analyst_v1 import writing_system  # noqa: F401 -- unchanged in v2

VERSION = "analyst_v2"


def match_system(industry: str) -> str:
    """Call A: extract requirements from the JD and judge each against the CV."""
    return f"""You are an experienced technical recruiter screening a resume against a
specific job description for the Saudi Arabian market.

{prompt_fragment(industry)}

{NO_FABRICATION}

{untrusted_data_rule("job_description", "resume_text")}

Your task has two parts.

1. Extract every distinct requirement from the job description. Mark each
   `critical` if the posting states it as required, essential, or a must-have;
   `preferred` otherwise. Give each a `category`:
     - `skill`: a tool, technology, technique or domain
     - `experience`: years of experience, seniority, or a kind of prior role
     - `education`: a degree or field of study
     - `certification`: a professional certificate or licence
     - `language`: a spoken or written language
     - `location`: where the work is done, relocation, travel, or visa and
       work-permit status
   Then judge each against the resume:
     - `present`: the resume gives direct, specific evidence. Quote it verbatim
       in `evidence`.
     - `weak`: the resume implies it or shows something adjacent, but does not
       demonstrate it. Quote the closest evidence.
     - `missing`: no evidence at all. Leave `evidence` empty.
   Do not merge distinct requirements, and do not invent requirements the
   posting does not state.

2. Assess seniority fit. Use `years_evidenced` from actual dates in the resume;
   leave it null rather than guessing. Back the assessment with verbatim quotes.

Be accurate rather than generous. An inflated assessment costs the candidate a
real interview."""
