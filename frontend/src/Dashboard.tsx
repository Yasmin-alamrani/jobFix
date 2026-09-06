import { useMemo, useState } from 'react';
import type { AnalysisResult, Deduction, Requirement, SubScore } from './types';

/* The ledger is the page's argument: the score is arithmetic, so it is shown
   as arithmetic. Every line names the rule that cost the points. */
function Ledger({ result }: { result: AnalysisResult }) {
  const all = useMemo(
    () =>
      result.sub_scores
        .flatMap((s) => s.deductions)
        .sort((a, b) => b.points - a.points),
    [result],
  );
  const shown = all.slice(0, 12);
  const rest = all.slice(12);
  const restTotal = rest.reduce((sum, d) => sum + d.points, 0);

  return (
    <div className="ledger">
      <div className="ledger-line start">
        <span className="amount">100.0</span>
        <span className="what">Starting score</span>
        <span className="rule-id" />
      </div>

      {shown.map((d, i) => (
        <div className={`ledger-line ${d.severity}`} key={`${d.rule}-${i}`}>
          <span className="amount">−{d.points.toFixed(1)}</span>
          <span className="what">{d.title}</span>
          <span className="rule-id">{d.rule}</span>
        </div>
      ))}

      {rest.length > 0 && (
        <div className="ledger-more">
          + {rest.length} smaller {rest.length === 1 ? 'deduction' : 'deductions'} totalling −
          {restTotal.toFixed(1)}
        </div>
      )}

      <div className="ledger-rule" />
      <div className="ledger-total">
        <span className="figure">{result.overall_score.toFixed(1)}</span>
        <span className="of">out of 100</span>
      </div>
    </div>
  );
}

function Bars({ subScores }: { subScores: SubScore[] }) {
  return (
    <div className="bars">
      {subScores.map((s) => {
        const pct = s.max_points ? (100 * s.earned) / s.max_points : 0;
        return (
          <div key={s.key}>
            <div className="bar-head">
              <span className="name">{s.label}</span>
              <span className="val">
                {s.earned.toFixed(1)} / {s.max_points.toFixed(0)}
              </span>
            </div>
            <div
              className="track"
              role="meter"
              aria-valuenow={Math.round(pct)}
              aria-valuemin={0}
              aria-valuemax={100}
              aria-label={s.label}
            >
              <div className="fill" style={{ width: `${pct}%` }} />
            </div>
          </div>
        );
      })}
    </div>
  );
}

function Finding({ d }: { d: Deduction }) {
  return (
    <article className={`finding ${d.severity}`}>
      <div className="finding-head">
        <h3>{d.title}</h3>
        <span className="cost">−{d.points.toFixed(1)} pts</span>
      </div>
      <pre className="evidence">{d.evidence}</pre>
      <p className="fix">
        <strong>Fix:</strong> {d.fix}
      </p>
    </article>
  );
}

function Requirements({ requirements }: { requirements: Requirement[] }) {
  if (requirements.length === 0) {
    return <p className="empty">No requirements were extracted from this job description.</p>;
  }
  const order = { missing: 0, weak: 1, present: 2 } as const;
  const sorted = [...requirements].sort(
    (a, b) =>
      order[a.status] - order[b.status] ||
      (a.importance === 'critical' ? -1 : 1) - (b.importance === 'critical' ? -1 : 1),
  );

  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Requirement</th>
            <th>Weight</th>
            <th>Status</th>
            <th>Evidence in your resume</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((r, i) => (
            <tr key={`${r.skill}-${i}`}>
              <td>{r.skill}</td>
              <td>
                <span
                  className={`pill ${r.importance === 'critical' ? 'critical-req' : 'preferred'}`}
                >
                  {r.importance === 'critical' ? 'required' : 'preferred'}
                </span>
              </td>
              <td>
                <span className={`pill ${r.status}`}>{r.status}</span>
              </td>
              <td className="q">{r.evidence || (r.note ? r.note : '—')}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* Redlines are proposals, never silent rewrites: the user decides each one. */
function Redlines({ result }: { result: AnalysisResult }) {
  const [decisions, setDecisions] = useState<Record<number, 'accepted' | 'rejected' | undefined>>({});
  const issues = result.writing.issues;

  if (issues.length === 0) {
    return <p className="empty">No wording changes suggested — the writing holds up.</p>;
  }

  const accepted = Object.values(decisions).filter((d) => d === 'accepted').length;

  return (
    <>
      <p className="note" style={{ marginBottom: '1rem' }}>
        {accepted} of {issues.length} accepted. Nothing is rewritten until you say so.
      </p>
      {issues.map((issue, i) => (
        <article className={`redline ${decisions[i] ?? ''}`} key={i}>
          <div className="finding-head">
            <h3>{issue.section}</h3>
            <span className={`cost ${issue.severity}`}>{issue.severity}</span>
          </div>
          <div className="diff">
            <div className="diff-side was">{issue.original}</div>
            <div className="diff-side now">{issue.suggested}</div>
          </div>
          <p className="fix" style={{ marginBottom: '0.75rem' }}>
            {issue.why}
          </p>
          <div className="actions">
            <button
              type="button"
              aria-pressed={decisions[i] === 'accepted'}
              onClick={() =>
                setDecisions((d) => ({ ...d, [i]: d[i] === 'accepted' ? undefined : 'accepted' }))
              }
            >
              Accept
            </button>
            <button
              type="button"
              aria-pressed={decisions[i] === 'rejected'}
              onClick={() =>
                setDecisions((d) => ({ ...d, [i]: d[i] === 'rejected' ? undefined : 'rejected' }))
              }
            >
              Reject
            </button>
          </div>
        </article>
      ))}
    </>
  );
}

export default function Dashboard({ result }: { result: AnalysisResult }) {
  const facts = result.parse_facts as Record<string, unknown>;
  return (
    <>
      <section>
        <div className="eyebrow">How the score was reached</div>
        <Ledger result={result} />
      </section>

      <section>
        <div className="eyebrow">Where the points sit</div>
        <Bars subScores={result.sub_scores} />
      </section>

      {result.top_fixes.length > 0 && (
        <section>
          <div className="eyebrow">Fix these first</div>
          {result.top_fixes.map((d, i) => (
            <Finding d={d} key={`${d.rule}-${i}`} />
          ))}
        </section>
      )}

      <section>
        <div className="eyebrow">Requirements from the posting</div>
        <Requirements requirements={result.requirements} />
      </section>

      <section>
        <div className="eyebrow">Suggested edits</div>
        {result.writing.summary_verdict && (
          <p className="verdict" style={{ marginBottom: '1.25rem' }}>
            {result.writing.summary_verdict}
          </p>
        )}
        <Redlines result={result} />
      </section>

      <section>
        <div className="eyebrow">What the parser measured</div>
        <div className="facts">
          <span>pages: {String(facts.page_count ?? '—')}</span>
          <span>characters: {String(facts.char_count ?? '—')}</span>
          <span>language: {String(facts.primary_language ?? '—')}</span>
          <span>bilingual: {String(facts.is_bilingual ?? false)}</span>
          <span>
            sections: {(facts.detected_sections as string[] | undefined)?.join(', ') || 'none found'}
          </span>
        </div>
      </section>
    </>
  );
}
