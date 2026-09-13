import { useMemo, useState } from 'react';
import { findJobs, jobFromUrl, scoreJobs } from './api';
import { TailorButton } from './Tailor';
import type { FindResponse, PastedJob, ScoreResponse, ScoutCandidate } from './types';

/* The two steps are deliberately separate in the UI as well as the API.
   Searching is free and instant; scoring costs money and takes time. Folding
   them into one button would hide the cost behind a spinner and spend it on
   jobs the user never wanted. */

const DEFAULT_SHORTLIST = 8;

const LEVELS = ['intern', 'junior', 'mid', 'senior', 'lead'] as const;
const LEVEL_LABEL: Record<string, string> = {
  intern: 'Intern',
  junior: 'Junior',
  mid: 'Mid-level',
  senior: 'Senior',
  lead: 'Lead / manager',
};

const HIDDEN_LABEL: Record<string, string> = {
  work_mode: 'with another work arrangement',
  work_mode_unstated: 'that state no work arrangement',
  seniority: 'at another level',
  seniority_unstated: 'whose title states no level',
  posted: 'posted earlier',
  posted_unstated: 'with no posting date',
};

/* What filters removed, and why -- so a short list reads as "the filters
   hid 40" rather than "there are only 6 jobs". */
function hiddenSummary(hidden: Record<string, number>): string {
  const parts = Object.entries(hidden)
    .filter(([, n]) => n > 0)
    .map(([reason, n]) => `${n} ${HIDDEN_LABEL[reason] ?? reason}`);
  return parts.length ? `Filters hid ${parts.join(', ')}.` : '';
}

function postedLabel(iso: string | null): string {
  if (!iso) return 'date not stated';
  const days = Math.floor((Date.now() - new Date(iso).getTime()) / 86_400_000);
  if (days <= 0) return 'posted today';
  if (days === 1) return 'posted yesterday';
  if (days < 14) return `posted ${days} days ago`;
  if (days < 60) return `posted ${Math.round(days / 7)} weeks ago`;
  return `posted ${Math.round(days / 30)} months ago`;
}

/* Level is read from title words, so it is shown as read, not as fact. */
function metaLine(seniority: string, workMode: string, postedAt: string | null): string {
  const level =
    seniority === 'unknown' ? 'level not stated' : `${LEVEL_LABEL[seniority] ?? seniority} (from title)`;
  const mode = workMode === 'unknown' ? 'arrangement not stated' : workMode;
  return [level, mode, postedLabel(postedAt)].join(' · ');
}

function Bar({ value, max }: { value: number; max: number }) {
  /* Relative only. The raw cosine similarity is meaningless as an absolute
     number — 0.085 is a strong match in this corpus — so showing it as a score
     would imply a precision that isn't there. It ranks; it doesn't grade. */
  const pct = max > 0 ? Math.round((100 * value) / max) : 0;
  return (
    <span className="relbar" title={`${pct}% as relevant as the top result`}>
      <span style={{ width: `${Math.max(pct, 2)}%` }} />
    </span>
  );
}

export default function Scout({ resumeId }: { resumeId: string | null }) {
  const [titleHint, setTitleHint] = useState('');
  const [locations, setLocations] = useState('saudi, riyadh');
  const [linkedinOnly, setLinkedinOnly] = useState(false);
  const [includeJsearch, setIncludeJsearch] = useState(false);
  const [workMode, setWorkMode] = useState<'any' | 'remote' | 'hybrid' | 'onsite'>('any');
  const [levels, setLevels] = useState<Set<string>>(new Set());
  const [postedWithin, setPostedWithin] = useState<number | null>(null);
  const [includeUnstated, setIncludeUnstated] = useState(true);

  const [found, setFound] = useState<FindResponse | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [scored, setScored] = useState<ScoreResponse | null>(null);

  const [pastedUrl, setPastedUrl] = useState('');
  const [pasted, setPasted] = useState<PastedJob | null>(null);
  const [reading, setReading] = useState(false);

  const [searching, setSearching] = useState(false);
  const [scoring, setScoring] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const topSimilarity = useMemo(
    () => (found?.candidates.length ? found.candidates[0].similarity : 0),
    [found],
  );

  async function search(event: React.FormEvent) {
    event.preventDefault();
    if (!resumeId) return;
    setError(null);
    setSearching(true);
    setScored(null);
    try {
      const result = await findJobs({
        resumeId,
        titleHint,
        locations: locations.split(',').map((s) => s.trim()).filter(Boolean),
        includeJsearch,
        linkedinOnly,
        filters: {
          workMode,
          seniority: [...levels],
          postedWithinDays: postedWithin,
          includeUnstated,
        },
      });
      setFound(result);
      // Preselect the shortlist the user would most likely pick anyway.
      setSelected(new Set(result.candidates.slice(0, DEFAULT_SHORTLIST).map((c) => c.id)));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Search failed.');
    } finally {
      setSearching(false);
    }
  }

  async function score() {
    if (!resumeId || selected.size === 0) return;
    setError(null);
    setScoring(true);
    try {
      setScored(await scoreJobs({ resumeId, jobIds: [...selected] }));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Scoring failed.');
    } finally {
      setScoring(false);
    }
  }

  async function readUrl(event: React.FormEvent) {
    event.preventDefault();
    if (!resumeId || !pastedUrl.trim()) return;
    setError(null);
    setReading(true);
    setPasted(null);
    try {
      setPasted(await jobFromUrl({ url: pastedUrl.trim(), resumeId }));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not read that page.');
    } finally {
      setReading(false);
    }
  }

  function toggleLevel(level: string) {
    setLevels((prev) => {
      const next = new Set(prev);
      if (next.has(level)) next.delete(level);
      else next.add(level);
      return next;
    });
  }

  function toggle(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }

  if (!resumeId) {
    return (
      <p className="empty" style={{ marginTop: '2rem' }}>
        Upload a resume above first — the search ranks jobs against it.
      </p>
    );
  }

  return (
    <>
      <form className="form paste-panel" onSubmit={readUrl} style={{ marginTop: '2rem' }}>
        <label>
          <span className="label-text">Have a specific job link? Paste it</span>
          <input
            type="url"
            value={pastedUrl}
            placeholder="https://www.linkedin.com/jobs/view/..."
            onChange={(e) => setPastedUrl(e.target.value)}
          />
        </label>
        <p className="note">
          Works with a link to one specific role — LinkedIn, Bayt, or a company careers
          page. Search and listing pages won&apos;t work: those sites don&apos;t permit
          automated access to them.
        </p>
        {reading ? (
          <div className="working">
            <span className="sweep">
              <i />
            </span>
            Reading that page…
          </div>
        ) : (
          <button type="submit" disabled={!pastedUrl.trim()}>
            Read this job
          </button>
        )}
      </form>

      {pasted && (
        <article className="finding" style={{ marginTop: '1.25rem' }}>
          <div className="finding-head">
            <h3>
              <a href={pasted.apply_url} target="_blank" rel="noreferrer noopener">
                {pasted.title}
              </a>
              {' — '}
              {pasted.company}
              {pasted.location ? `, ${pasted.location}` : ''}
            </h3>
            {pasted.score !== null && (
              <span className="match-score">{pasted.score.toFixed(0)}</span>
            )}
          </div>
          {pasted.why && <p className="fix">{pasted.why}</p>}
          {pasted.gap && (
            <p className="fix" style={{ opacity: 0.85 }}>
              {pasted.gap}
            </p>
          )}
          {pasted.missing.length > 0 && (
            <div className="chips">
              {pasted.missing.map((m) => (
                <span className="pill missing" key={m}>
                  {m}
                </span>
              ))}
            </div>
          )}
          <p className="q" style={{ marginTop: '0.75rem' }}>
            read via {pasted.source}
          </p>
          <TailorButton
            key={pasted.apply_url}
            resumeId={resumeId}
            target={{
              job: {
                title: pasted.title,
                company: pasted.company,
                location: pasted.location,
                description: pasted.description,
                apply_url: pasted.apply_url,
                source: pasted.source,
              },
            }}
          />
        </article>
      )}

      <div className="eyebrow" style={{ marginTop: '2.5rem' }}>
        Or search the boards
      </div>

      <form className="form" onSubmit={search} style={{ marginTop: '1rem' }}>
        <div className="row">
          <label>
            <span className="label-text">Role you want</span>
            <input
              type="text"
              value={titleHint}
              placeholder="Backend Engineer"
              onChange={(e) => setTitleHint(e.target.value)}
            />
          </label>
          <label>
            <span className="label-text">Locations — comma separated</span>
            <input
              type="text"
              value={locations}
              placeholder="saudi, riyadh, remote"
              onChange={(e) => setLocations(e.target.value)}
            />
          </label>
        </div>

        <div className="row filters">
          <label>
            <span className="label-text">Work arrangement</span>
            <select
              value={workMode}
              onChange={(e) => setWorkMode(e.target.value as typeof workMode)}
            >
              <option value="any">Any</option>
              <option value="remote">Remote</option>
              <option value="hybrid">Hybrid</option>
              <option value="onsite">On-site</option>
            </select>
          </label>
          <label>
            <span className="label-text">Posted within</span>
            <select
              value={postedWithin ?? ''}
              onChange={(e) => setPostedWithin(e.target.value ? Number(e.target.value) : null)}
            >
              <option value="">Any time</option>
              <option value="1">24 hours</option>
              <option value="7">7 days</option>
              <option value="30">30 days</option>
            </select>
          </label>
        </div>

        <fieldset className="levels">
          <legend className="label-text">Seniority — read from the job title</legend>
          {LEVELS.map((level) => (
            <label className="check-inline" key={level}>
              <input
                type="checkbox"
                checked={levels.has(level)}
                onChange={() => toggleLevel(level)}
              />{' '}
              {LEVEL_LABEL[level]}
            </label>
          ))}
        </fieldset>

        <label className="check">
          <input
            type="checkbox"
            checked={includeUnstated}
            onChange={(e) => setIncludeUnstated(e.target.checked)}
          />
          <span>
            Keep roles that don&apos;t say
            <em>
              Most titles state no level, and many postings give no date or work arrangement.
              Untick to hide them when a filter is on.
            </em>
          </span>
        </label>

        <div className="checks">
          <label className="check">
            <input
              type="checkbox"
              checked={includeJsearch}
              onChange={(e) => setIncludeJsearch(e.target.checked)}
            />
            <span>
              Also search Google for Jobs
              <em>
                Reaches LinkedIn, Indeed and Bayt listings. Uses one request from your
                JSearch quota.
              </em>
            </span>
          </label>
          {includeJsearch && (
            <label className="check">
              <input
                type="checkbox"
                checked={linkedinOnly}
                onChange={(e) => setLinkedinOnly(e.target.checked)}
              />
              <span>
                LinkedIn listings only
                <em>Filters to roles published on LinkedIn.</em>
              </span>
            </label>
          )}
        </div>

        {error && <p className="error">{error}</p>}

        {searching ? (
          <div className="working">
            <span className="sweep">
              <i />
            </span>
            Scanning job boards…
          </div>
        ) : (
          <button type="submit">Search — free</button>
        )}
      </form>

      {found && (
        <section>
          <div className="eyebrow">
            {found.total_found} scanned · {found.candidates.length} shown
          </div>
          {hiddenSummary(found.hidden) && <p className="note">{hiddenSummary(found.hidden)}</p>}

          <p className="note" style={{ marginBottom: '1rem' }}>
            Ranked by overlap with your CV. This step is free and cost nothing to run —
            the bar shows relevance <em>relative to the top result</em>, not a score.
            Pick the ones worth a closer look.
          </p>

          {found.candidates.length === 0 ? (
            <p className="empty">
              Nothing in those locations. Try widening them, or drop the location filter.
            </p>
          ) : (
            <>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th style={{ width: '2rem' }} />
                      <th style={{ width: '6rem' }}>Relevance</th>
                      <th>Role</th>
                      <th>Company</th>
                      <th>Level · arrangement · posted</th>
                      <th>Shared with your CV</th>
                    </tr>
                  </thead>
                  <tbody>
                    {found.candidates.map((c: ScoutCandidate) => (
                      <tr key={c.id} className={selected.has(c.id) ? 'picked' : ''}>
                        <td>
                          <input
                            type="checkbox"
                            checked={selected.has(c.id)}
                            onChange={() => toggle(c.id)}
                            aria-label={`Select ${c.title}`}
                          />
                        </td>
                        <td>
                          <Bar value={c.similarity} max={topSimilarity} />
                        </td>
                        <td>
                          <a href={c.apply_url} target="_blank" rel="noreferrer noopener">
                            {c.title}
                          </a>
                          {c.publisher && <span className="via">via {c.publisher}</span>}
                        </td>
                        <td>
                          {c.company}
                          <br />
                          <span className="q">{c.location}</span>
                        </td>
                        <td className="q">{metaLine(c.seniority, c.work_mode, c.posted_at)}</td>
                        <td className="q">{c.overlap.slice(0, 5).join(', ') || '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div className="score-bar">
                {scoring ? (
                  <div className="working">
                    <span className="sweep">
                      <i />
                    </span>
                    Reading {selected.size} job{selected.size === 1 ? '' : 's'} against your CV…
                  </div>
                ) : (
                  <>
                    <button type="button" onClick={score} disabled={selected.size === 0}>
                      Score {selected.size} with AI
                    </button>
                    <span className="cost-note">
                      {selected.size === 0
                        ? 'Select at least one role.'
                        : `${selected.size} model call${selected.size === 1 ? '' : 's'}.`}
                    </span>
                  </>
                )}
              </div>
            </>
          )}
        </section>
      )}

      {scored && (
        <section>
          <div className="eyebrow">
            {scored.worth_it} worth your time
          </div>
          {scored.headline && (
            <p className="verdict" style={{ marginBottom: '1.5rem' }}>
              {scored.headline}
            </p>
          )}
          {scored.lines.map((line, i) => (
            <article className="finding" key={`${line.title}-${i}`}>
              <div className="finding-head">
                <h3>
                  <a href={line.url} target="_blank" rel="noreferrer noopener">
                    {line.title}
                  </a>
                  {' — '}
                  {line.company}
                  {line.location ? `, ${line.location}` : ''}
                </h3>
                <span className="match-score">{line.score.toFixed(0)}</span>
              </div>
              <p className="fix">{line.why}</p>
              {line.gap && (
                <p className="fix" style={{ opacity: 0.85 }}>
                  {line.gap}
                </p>
              )}
              <p className="q">{metaLine(line.seniority, line.work_mode, line.posted_at)}</p>
              {line.matched.length > 0 && (
                <div className="chips">
                  <span className="label-text">Top matches</span>
                  {line.matched.slice(0, 3).map((m) => (
                    <span className="pill present" key={m}>
                      {m}
                    </span>
                  ))}
                </div>
              )}
              {line.missing.length > 0 && (
                <div className="chips">
                  <span className="label-text">Top missing</span>
                  {line.missing.slice(0, 3).map((m) => (
                    <span className="pill missing" key={m}>
                      {m}
                    </span>
                  ))}
                </div>
              )}
              {line.id && (
                <TailorButton key={line.id} resumeId={resumeId} target={{ scoutJobId: line.id }} />
              )}
            </article>
          ))}
          {scored.failures > 0 && (
            <p className="note">
              {scored.failures} role{scored.failures === 1 ? '' : 's'} could not be scored.
            </p>
          )}
        </section>
      )}
    </>
  );
}
