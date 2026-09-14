import type { CvReview, ReviewCheck, ReviewWeakness, Severity } from './types';

const SEVERITY_LABEL: Record<Severity, string> = {
  critical: 'Fix first',
  major: 'Important',
  minor: 'Polish',
};

const AREA_LABEL: Record<string, string> = {
  impact: 'Impact',
  clarity: 'Clarity',
  summary: 'Summary',
  skills: 'Skills',
  structure: 'Structure',
  consistency: 'Consistency',
  language: 'Language',
  completeness: 'Missing information',
};

const SLOT = /(\[add [^[\]\n]{1,40}\])/i;

/* Placeholders are the part the user fills in, so they stand out. */
function WithSlots({ text }: { text: string }) {
  return (
    <>
      {text.split(SLOT).map((part, i) =>
        i % 2 ? (
          <mark className="slot" key={i}>
            {part}
          </mark>
        ) : (
          part
        ),
      )}
    </>
  );
}

function Weakness({ w }: { w: ReviewWeakness }) {
  return (
    <article className={`finding ${w.severity}`}>
      <div className="finding-head">
        <strong className="finding-title">{w.title}</strong>
        <span className="cost">{SEVERITY_LABEL[w.severity]}</span>
      </div>
      <p className="area">{AREA_LABEL[w.area] ?? w.area}</p>

      {w.evidence && w.example ? (
        <div className="diff">
          <div className="diff-side was">{w.evidence}</div>
          <div className="diff-side now">
            <WithSlots text={w.example} />
          </div>
        </div>
      ) : w.evidence ? (
        <pre className="evidence">{w.evidence}</pre>
      ) : w.example ? (
        <div className="diff">
          <div className="diff-side now">
            <WithSlots text={w.example} />
          </div>
        </div>
      ) : null}

      <p className="fix">
        <strong>Why it matters:</strong> {w.problem}
      </p>
      <p className="fix">
        <strong>What to do:</strong> {w.recommendation}
      </p>
      {w.example_withheld && (
        <p className="note">
          An example rewrite was left out because it added details that are not in this part of
          your CV.
        </p>
      )}
    </article>
  );
}

function Check({ c }: { c: ReviewCheck }) {
  return (
    <article className={`finding ${c.severity}`}>
      <div className="finding-head">
        <strong className="finding-title">{c.title}</strong>
        <span className="cost">{SEVERITY_LABEL[c.severity]}</span>
      </div>
      <pre className="evidence">{c.evidence}</pre>
      <p className="fix">
        <strong>What to do:</strong> {c.fix}
      </p>
    </article>
  );
}

function tally(review: CvReview): string {
  const all = [...review.weaknesses, ...review.checks];
  if (all.length === 0) return 'Nothing to fix.';
  const count = (s: Severity) => all.filter((x) => x.severity === s).length;
  return (['critical', 'major', 'minor'] as const)
    .filter((s) => count(s) > 0)
    .map((s) => `${count(s)} ${SEVERITY_LABEL[s].toLowerCase()}`)
    .join(' · ');
}

export default function Review({ review }: { review: CvReview }) {
  return (
    <div className="review">
      {review.verdict && <p className="verdict">{review.verdict}</p>}
      <p className="review-tally">{tally(review)}</p>

      <h3>What to improve</h3>
      {review.weaknesses.length === 0 ? (
        <p className="empty">No weak areas found in the writing itself.</p>
      ) : (
        review.weaknesses.map((w, i) => <Weakness w={w} key={`${w.title}-${i}`} />)
      )}
      {review.withheld > 0 && (
        <p className="note">
          {review.withheld} point{review.withheld > 1 ? 's were' : ' was'} left out because the
          text quoted could not be found in your CV.
        </p>
      )}

      <h3>Automatic checks</h3>
      {!review.layout_checked && (
        <p className="note">
          This CV was pasted as text, so its layout could not be checked. Upload the file itself
          to check for columns, tables and text in headers.
        </p>
      )}
      {review.checks.length === 0 ? (
        <p className="empty">Nothing flagged.</p>
      ) : (
        review.checks.map((c) => <Check c={c} key={c.rule} />)
      )}

      {review.strengths.length > 0 && (
        <>
          <h3>What already works</h3>
          <ul className="strengths">
            {review.strengths.map((s, i) => (
              <li key={i}>
                <strong>{s.point}</strong>
                <span className="q">“{s.evidence}”</span>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
