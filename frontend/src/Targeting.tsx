import { useEffect, useState } from 'react';
import { getTargeting } from './api';
import { useText } from './i18n';
import type { Targeting as TargetingResult, TargetingBasis } from './types';

const en = {
  stated: 'stated',
  inferred: 'inferred',
  says: (quote: string) => `The posting says: “${quote}”`,
  reading: 'A reading of the posting, not a fact about the company',
  failed: 'Could not read the employer.',
  heading: 'What this employer is looking for',
  working: 'Reading the posting for what the employer values…',
  values: 'What they value',
  tone: 'Tone to match',
  keywords: 'ATS keywords in the posting',
  keywordsNote:
    'Use the ones your CV genuinely supports, in the posting’s own words. The rest are gaps, not words to add.',
  actions: 'What to do about it',
};

const ar: typeof en = {
  stated: 'مذكور',
  inferred: 'مستنتَج',
  says: (quote: string) => `يقول الإعلان: «${quote}»`,
  reading: 'قراءة للإعلان، لا حقيقة عن الشركة',
  failed: 'تعذّرت قراءة جهة العمل.',
  heading: 'ما الذي تبحث عنه جهة العمل هذه',
  working: 'جارٍ قراءة الإعلان لمعرفة ما تقدّره جهة العمل…',
  values: 'ما يقدّرونه',
  tone: 'الأسلوب المناسب',
  keywords: 'الكلمات المفتاحية في الإعلان',
  keywordsNote:
    'استخدم منها ما تدعمه سيرتك الذاتية فعلًا، بكلمات الإعلان نفسها. أما البقية ففجوات لا كلمات تُضاف.',
  actions: 'ما الذي يجب فعله',
};

const TEXT = { en, ar };

/* "Stated" is earned: the server keeps the label only when the point carries a
   quote that is really in the posting. Everything else is shown as an
   inference, because a reading of a posting is not a fact about an employer. */
function Basis({ basis, quote }: { basis: TargetingBasis; quote: string }) {
  const t = useText(TEXT);
  return basis === 'stated' ? (
    <span className="pill stated" title={t.says(quote)}>
      {t.stated}
    </span>
  ) : (
    <span className="pill inferred" title={t.reading}>
      {t.inferred}
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
  const t = useText(TEXT);
  /* Captured once: the form can change after the audit ran, and this panel
     describes the posting that was actually analysed. */
  const [request] = useState({ resumeId, title, company, jobDescription });
  const [failedText] = useState(t.failed);
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
        if (!cancelled) setError(err instanceof Error ? err.message : failedText);
      })
      .finally(() => {
        if (!cancelled) setWorking(false);
      });
    return () => {
      cancelled = true;
    };
  }, [request, failedText]);

  return (
    <section className="targeting">
      <div className="eyebrow">{t.heading}</div>

      {working && (
        <div className="working">
          <span className="sweep">
            <i />
          </span>
          {t.working}
        </div>
      )}
      {error && <p className="error">{error}</p>}

      {result && (
        <>
          <p className="note">{result.caveat}</p>

          {result.values.length > 0 && (
            <>
              <h4>{t.values}</h4>
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
              <h4>{t.tone}</h4>
              <p>
                <Basis basis={result.tone.basis} quote={result.tone.quote} /> {result.tone.point}
              </p>
            </>
          )}

          {result.keywords.length > 0 && (
            <>
              <h4>{t.keywords}</h4>
              <p className="note">{t.keywordsNote}</p>
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
              <h4>{t.actions}</h4>
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
