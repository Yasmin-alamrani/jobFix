"""Stage 1: rank every job against the CV without spending a token.

A scan returns ~100 jobs and most are obviously irrelevant. Sending all of them
to a model would cost 100x what the answer is worth, so this narrows the field
first using TF-IDF cosine similarity over the job corpus. Only the survivors
reach the LLM in stage 2.

TF-IDF rather than raw keyword counts because the discriminating terms are the
rare ones: "Kubernetes" appearing in both the CV and a posting means far more
than "experience" appearing in both, and only weighting by document frequency
captures that. Implemented directly -- pulling in scikit-learn for sixty lines
of arithmetic would be a heavy dependency for no gain.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass

from app.sources.base import JobPosting

# Words too common in job ads to carry signal. Deliberately short: TF-IDF
# already suppresses corpus-wide terms, so this only needs to catch generic
# English that would otherwise survive tokenisation.
STOPWORDS = frozenset("""
a an and are as at be been but by for from has have if in into is it its of on
or that the to was were will with you your we our us they their this these
those he she his her them then than there here about across after all also any
because before being between both during each few more most other over same
some such through under up very what when where which who why would can could
should may might must do does did doing done get got make made take taken
work working works experience experienced role position job candidate team
company please apply application applicant opportunity responsibilities
requirements qualifications skills ability able strong good excellent
""".split())

# Resume furniture: section headings, degree words, date filler.
#
# These must be excluded explicitly. IDF is computed over job *descriptions*,
# where "education" and "summary" are genuinely rare -- so the maths scores them
# as highly distinctive and matches any posting that happens to mention them.
# That put a Finance Operations manager third against a backend CV. They are
# rare in the corpus but carry no signal about what the candidate can do.
RESUME_BOILERPLATE = frozenset("""
summary profile objective education experience employment history skills
technical certifications certification licenses projects publications awards
volunteer references achievements training courses languages interests
university college school degree bachelor bachelors master masters phd diploma
gpa graduated present current ongoing curriculum vitae resume cv contact email
phone mobile address linkedin github portfolio website name date birth
january february march april may june july august september october november
december mon tue wed thu fri sat sun year years month months day days
""".split())

# Job-ad furniture: the benefits block, the EEO paragraph, the "about us" and
# the application process. Every advert carries it and it says nothing about
# the work, so it is excluded when measuring how much of a posting a CV
# covers. It is deliberately NOT removed in `tokenize`: ranking compares
# postings against each other, where this vocabulary cancels out anyway, and
# stripping it there would change every existing similarity.
AD_BOILERPLATE = frozenset("""
benefit benefits salary compensation bonus incentive pension insurance medical
dental health wellness gym allowance discount stipend equity options shares
leave holiday holidays vacation annual parental maternity paternity sick
flexible hybrid remote onsite office relocation visa sponsorship
opportunity opportunities employer equal diversity inclusive inclusion
background backgrounds regardless race gender religion disability veteran
orientation identity age applicants applications applying recruiter recruitment
hiring process interview offer start date immediately urgently
join joining looking seeking passionate motivated dynamic fast-paced
environment culture mission vision values people person individual
welcome welcoming thrive grow growth career careers journey world class
leading leader global regional local industry market customers clients
competitive generous outstanding exciting great best top
""".split())

_TOKEN = re.compile(r"[a-z][a-z0-9+#.\-]{1,}")

# How many times a job's title is repeated into its token stream. 3 is enough
# to dominate generic body prose without drowning out the description entirely.
TITLE_BOOST = 3
# Maximum lift applied when a role's title matches the user's stated target.
TITLE_HINT_LIFT = 0.6
# Smallest weight any term keeps, so small corpora still discriminate.
IDF_FLOOR = 0.05

# Terms that mean the same thing to a recruiter but not to a tokenizer.
SYNONYMS = {
    "js": "javascript", "ts": "typescript", "py": "python",
    "postgres": "postgresql", "psql": "postgresql",
    "k8s": "kubernetes", "gcp": "googlecloud",
    "ml": "machinelearning", "ai": "artificialintelligence",
    "nodejs": "node", "node.js": "node", "reactjs": "react",
    "ci/cd": "cicd", "restful": "rest", "apis": "api",
}


def tokenize(text: str) -> list[str]:
    out = []
    for raw in _TOKEN.findall(text.lower()):
        token = raw.strip(".-")
        if len(token) < 2 or token in STOPWORDS or token in RESUME_BOILERPLATE:
            continue
        out.append(SYNONYMS.get(token, token))
    return out


@dataclass(frozen=True)
class Candidate:
    job: JobPosting
    similarity: float
    overlap: tuple[str, ...]   # rare terms shared by CV and posting
    # Share of this posting's distinctive terms the CV contains, 0..1.
    # Unlike `similarity` -- a cosine whose magnitude only means anything
    # against the other results in the same scan -- this one is a fraction of
    # a fixed denominator, so it can be shown to a person as a number.
    coverage: float = 0.0

    @property
    def why(self) -> str:
        return ", ".join(self.overlap[:6]) if self.overlap else "no distinctive overlap"


def _tf(tokens: list[str]) -> dict[str, float]:
    """Log-scaled term frequency, so a word repeated 20 times isn't 20x a word said once."""
    counts = Counter(tokens)
    return {t: 1.0 + math.log(n) for t, n in counts.items()}


def _idf(docs: list[list[str]]) -> dict[str, float]:
    """Smoothed inverse document frequency, floored just above zero.

    The floor matters on small corpora. Textbook IDF gives a term appearing in
    every document a weight of exactly zero -- correct when ranking thousands of
    documents, degenerate when there are three. Scanning one company can yield
    five jobs, and at that size every shared term would cancel out and nothing
    would rank. A small positive floor keeps shared terms contributing, so
    title boosting still separates roles, while genuinely rare terms continue
    to dominate once the corpus is large enough for IDF to mean anything.
    """
    n = len(docs)
    seen = Counter()
    for doc in docs:
        seen.update(set(doc))
    return {t: max(IDF_FLOOR, math.log((n + 1) / (df + 1))) for t, df in seen.items()}


def _coverage(tokens: list[str], resume_set: set[str]) -> float:
    """How much of what a posting asks for appears in the CV, 0..1.

    Weighted by how much the posting leans on each term -- its own log-scaled
    term frequency, with the title already repeated into the stream -- and by
    nothing else. Deliberately no IDF: IDF is a property of the corpus, so the
    same posting would score differently depending on what else a scan
    returned, and a percentage on a card has to mean the same thing every time
    it is shown.

    The benefits and equal-opportunity blocks are dropped first. They are a
    third of a long advert and identical across all of them, so leaving them
    in drags every posting toward the same low number and a perfect match
    reads about as well as a poor one.
    """
    weights = {t: w for t, w in _tf(tokens).items() if t not in AD_BOILERPLATE}
    total = sum(weights.values())
    if total <= 0:
        return 0.0
    carried = sum(w for t, w in weights.items() if t in resume_set)
    return carried / total


def _cosine(a: dict[str, float], b: dict[str, float]) -> float:
    if not a or not b:
        return 0.0
    shared = a.keys() & b.keys()
    dot = sum(a[t] * b[t] for t in shared)
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    return dot / (na * nb) if na and nb else 0.0


def rank(
    resume_text: str,
    jobs: list[JobPosting],
    *,
    limit: int | None = None,
    locations: set[str] | None = None,
    title_hint: str = "",
) -> list[Candidate]:
    """Order jobs by similarity to the CV. Free, deterministic, no network.

    `locations` filters on a case-insensitive substring of the job's location --
    {"riyadh", "saudi"} keeps Saudi roles and drops the rest. `title_hint`
    nudges roles whose title matches what the user is actually looking for,
    since a JD's body can resemble a CV while the role itself does not.
    """
    if locations:
        wanted = {loc.lower() for loc in locations}
        jobs = [
            j for j in jobs
            if any(w in j.location.lower() for w in wanted) or (j.remote and "remote" in wanted)
        ]
    if not jobs:
        return []

    # Field boosting: title terms repeated so they outweigh the same words
    # buried in a long body. Job descriptions share a lot of generic prose, so
    # the title is the strongest single signal of what a role actually is.
    # `_idf` counts each document once via set(), so repetition lifts term
    # frequency without distorting document frequency.
    job_tokens = [tokenize(j.title) * TITLE_BOOST + tokenize(j.description) for j in jobs]
    resume_tokens = tokenize(resume_text)

    # IDF is computed over the postings *plus* the CV, so terms unique to the
    # candidate still carry weight when they appear in one posting.
    idf = _idf(job_tokens + [resume_tokens])

    resume_vec = {t: f * idf.get(t, 0.0) for t, f in _tf(resume_tokens).items()}
    resume_set = set(resume_tokens)
    hint_tokens = set(tokenize(title_hint))

    out: list[Candidate] = []
    for job, tokens in zip(jobs, job_tokens):
        job_vec = {t: f * idf.get(t, 0.0) for t, f in _tf(tokens).items()}
        score = _cosine(resume_vec, job_vec)

        if hint_tokens:
            title_tokens = set(tokenize(job.title))
            if title_tokens:
                score *= 1.0 + TITLE_HINT_LIFT * (
                    len(hint_tokens & title_tokens) / len(hint_tokens)
                )

        # Report the shared terms that actually discriminate, not "python" if
        # every posting says python.
        # Rarest first, so the terms shown are the ones that actually
        # discriminate. No absolute cutoff: on a small corpus every IDF sits
        # near the floor, and a threshold would report nothing at all.
        overlap = tuple(
            sorted(resume_set & set(tokens), key=lambda t: idf.get(t, 0.0), reverse=True)
        )[:10]
        out.append(Candidate(
            job=job,
            similarity=round(score, 4),
            overlap=overlap,
            coverage=round(_coverage(tokens, resume_set), 4),
        ))

    out.sort(key=lambda c: c.similarity, reverse=True)
    return out[:limit] if limit else out
