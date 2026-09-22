# Resume Analyzer

Two agents for a Saudi job search:

1. **Resume analyst** — reviews a CV on its own (weak areas, why each one hurts, and what to change, with every quote checked against the CV), and scores it against one job posting out of 100, showing exactly which points it lost and why.
2. **Job scout** — finds roles across ATS boards and Google for Jobs, ranks them against your CV with the *same* scorer, and opens any of them in the match view. It cannot apply to anything.

Pasting a job link reads the posting cheapest-way-first: structured data, then the page's own text, then a rendered copy, and only then the model. A site that forbids automated reading (LinkedIn) is never fetched — the posting is looked up through Google for Jobs, which is where it is syndicated on purpose.

Both are built. An earlier plan had Agent 2 emailing companies from a contact dataset; that was dropped in favour of discovery, and its artifacts removed.

The whole app works in **English or Arabic**, with a switch in the top bar; it opens in the browser's language until you choose. In Arabic the page reads right to left, the model writes its reviews and advice in Arabic, and the app's own messages are translated from one catalogue (`backend/app/core/i18n_ar.py`). Quotes from your CV and the posting are never translated — they stay as written, so the checks that they really are quotes still hold.

## What makes the score trustworthy

The number is **computed in Python, not produced by the model**. The model (Gemini Flash) supplies evidence — which requirements exist, which are missing, what reads weakly — and `scoring.py` does the arithmetic. That split means:

- Every deduction names a rule, quotes the span it came from, and gives the fix.
- The same inputs always produce the same score (unit-tested over 20 runs).
- Machine-parseability is measured with a real PDF parser, not guessed at.

The agent is also constrained never to invent experience. A missing skill is reported as a genuine gap to close, never as text to add.

## Run it

PDF export renders through WeasyPrint, which needs the Pango library from the
system. On macOS:

```bash
brew install pango
```

Then the Python side:

```bash
cd backend && python3 -m venv .venv && ./.venv/bin/python -m pip install -r requirements.txt
```

Commands here call tools through `python -m` rather than `./.venv/bin/<tool>`.
A venv's scripts hard-code the path it was created at, so moving the project
folder breaks every one of them with "bad interpreter" — while `python` itself,
a symlink, keeps working.

Add your keys:

```bash
cp backend/.env.example backend/.env
```

| Key | Needed for | Getting one |
|---|---|---|
| `GEMINI_API_KEY` | Every AI step, in both agents: reading the CV, matching, tailoring, company targeting, and scoring search results — the scores themselves are still computed in Python | [aistudio.google.com/apikey](https://aistudio.google.com/apikey) — turn on billing before uploading real CVs (see below) |
| `JSEARCH_API_KEY` | *Optional.* Google for Jobs, which is how LinkedIn roles reach the scan | [openwebninja.com/api/jsearch](https://www.openwebninja.com/api/jsearch) — free tier is 200 requests/month |

Without the JSearch key the scout still runs; it just searches the free ATS
boards -- a handful of companies -- and says so under the results. The same key
is what lets a link to a site we may not fetch be looked up instead.

**CVs are personal data.** On the Gemini API's free tier, Google may use what
you send to improve its products and human reviewers may read it; its terms say
not to send personal information there. With billing turned on for the key's
project, it does neither. Use the free tier only with made-up CVs.

The server reads `.env` once, at start-up. `--reload` watches code, not `.env`,
so restart it after changing a key.

Start the API:

```bash
cd backend && PYTHONPATH=. ./.venv/bin/python -m uvicorn app.main:app --port 8000 --reload
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
  their job pages, for every agent, even logged out. Their roles reach the scan
  two other ways: through Google for Jobs, which LinkedIn syndicates to
  deliberately, or by pasting a URL — one user action, one fetch. Neither path
  touches a disallowed page, and pasting a link to LinkedIn's guest search or
  Bayt's listings does not unlock them.
- **The scout agent cannot apply.** It has no tool that submits a form, types a
  password, or uploads a file. That is enforced in the browser wrapper, not in a
  prompt, so a prompt injection in a job listing cannot make it apply to
  something.
- **No stealth.** No fingerprint spoofing, proxy rotation, or CAPTCHA solving.
  An auth wall stops the run and reports it.

See [PLAN.md](PLAN.md) for the scout agent design.
