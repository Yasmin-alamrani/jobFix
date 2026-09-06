# Resume audit + job hunt

Two agents for a Saudi job search:

1. **Resume analyst** (built) — scores a resume against one job posting out of 100 and shows exactly which points it lost and why.
2. **Recruiter** (planned, Phase 3) — matches jobs, tailors applications, sends from Gmail behind a review queue.

## What makes the score trustworthy

The number is **computed in Python, not produced by the model**. Claude supplies evidence — which requirements exist, which are missing, what reads weakly — and `scoring.py` does the arithmetic. That split means:

- Every deduction names a rule, quotes the span it came from, and gives the fix.
- The same inputs always produce the same score (unit-tested over 20 runs).
- Machine-parseability is measured with a real PDF parser, not guessed at.

The agent is also constrained never to invent experience. A missing skill is reported as a genuine gap to close, never as text to add.

## Run it

```bash
cd backend && python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt
```

Add your key:

```bash
cp backend/.env.example backend/.env && echo "Now put your ANTHROPIC_API_KEY in backend/.env"
```

Start the API:

```bash
cd backend && PYTHONPATH=. ./.venv/bin/uvicorn app.main:app --port 8000 --reload
```

Start the UI in a second terminal:

```bash
cd frontend && npm install && npm run dev
```

Then open http://localhost:5173. To see the dashboard with sample data and no API spend, open http://localhost:5173/demo.html.

## Tests

```bash
cd backend && PYTHONPATH=. ./.venv/bin/python -m pytest tests/ -q
```

No test hits the API — the model is stubbed throughout.

## How scoring breaks down

| Dimension | Points | Source |
|---|---|---|
| ATS parseability | 25 | Deterministic PDF parser only |
| Keyword & skill match | 35 | Weighted set intersection over extracted requirements |
| Experience & seniority fit | 20 | Model evidence, scored in Python |
| Formatting & structure | 20 | Parser + model |

A resume with no machine-readable text scores **0**, not a partial score — every dimension is unassessable, and reporting a comfortable number for a resume that reaches recruiters blank would be misleading.

## Deliberate limits

- **No LinkedIn or Bayt crawling.** Both robots.txt forbid automated access to
  their job pages, for every agent, even logged out. Jobs from those sites come
  in by pasting a URL — one user action, one fetch.
- **The scout agent cannot apply.** It has no tool that submits a form, types a
  password, or uploads a file. That is enforced in the browser wrapper, not in a
  prompt, so a prompt injection in a job listing cannot make it apply to
  something.
- **No stealth.** No fingerprint spoofing, proxy rotation, or CAPTCHA solving.
  An auth wall stops the run and reports it.

See [PLAN.md](PLAN.md) for the scout agent design.
