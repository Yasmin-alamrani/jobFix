import { useEffect, useState } from 'react';
import { getTargeting } from './api';
import type { Targeting as TargetingResult, TargetingBasis } from './types';

/* "Stated" is earned: the server keeps the label only when the point carries a
   quote that is really in the posting. Everything else is shown as an
   inference, because a reading of a posting is not a fact about an employer. */
function Basis({ basis, quote }: { basis: TargetingBasis; quote: string }) {
  return basis === 'stated' ? (
    <span className="pill stated" title={`The posting says: “${quote}”`}>
      stated
    </span>
  ) : (
    <span className="pill inferred" title="A reading of the posting, not a fact about the company">
      inferred
    </span>
  );
}

export default function Targeting({
  resumeId,
  title,
  company,
  jobDescription,
}: {
  resumeId: string;
  title: string;
  company: string;
  jobDescription: string;
}) {
  /* Captured once: the form can change after the audit ran, and this panel
     describes the posting that was actually analysed. */
  const [request] = useState({ resumeId, title, company, jobDescription });
  const [result, setResult] = useState<TargetingResult | null>(null);
  const [working, setWorking] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getTargeting(request)
      .then((found) => {
        if (!cancelled) setResult(found);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Could not read the employer.');
      })
      .finally(() => {
        if (!cancelled) setWorking(false);
      });
    return () => {
      cancelled = true;
    };
  }, [request]);

  return (
    <section className="targeting">
      <div className="eyebrow">What this employer is looking for</div>

      {working && (
        <div className="working">
          <span className="sweep">
            <i />
          </span>
          Reading the posting for what the employer values…
        </div>
      )}
      {error && <p className="error">{error}</p>}

      {result && (
        <>
          <p className="note">{result.caveat}</p>

          {result.values.length > 0 && (
            <>
              <h4>What they value</h4>
              <ul className="signals">
                {result.values.map((v, i) => (
                  <li key={i}>
                    <Basis basis={v.basis} quote={v.quote} /> {v.point}
                    {v.basis === 'stated' && v.quote && (
                      <span className="quote" dir="auto">
                        “{v.quote}”
                      </span>
                    )}
                  </li>
                ))}
              </ul>
            </>
          )}

          {result.tone.point && (
            <>
              <h4>Tone to match</h4>
              <p>
                <Basis basis={result.tone.basis} quote={result.tone.quote} /> {result.tone.point}
              </p>
            </>
          )}

          {result.keywords.length > 0 && (
            <>
              <h4>ATS keywords in the posting</h4>
              <p className="note">
                Use the ones your CV genuinely supports, in the posting&apos;s own words. The rest
                are gaps, not words to add.
              </p>
              <div className="chips" dir="auto">
                {result.keywords.map((k) => (
                  <span className="pill" key={k}>
                    {k}
                  </span>
                ))}
              </div>
            </>
          )}

          {result.actions.length > 0 && (
            <>
              <h4>What to do about it</h4>
              <ol className="signals">
                {result.actions.map((a, i) => (
                  <li key={i}>
                    <Basis basis={a.basis} quote={a.quote} /> <strong>{a.action}</strong>
                    {a.why && <span className="why"> — {a.why}</span>}
                  </li>
                ))}
              </ol>
            </>
          )}
        </>
      )}
    </section>
  );
}
