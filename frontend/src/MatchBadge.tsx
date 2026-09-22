import { useText } from './i18n';
import { BAND_TEXT, coverageBand } from './match';

/* The small ring on a search result. It is the same idea as the ring on a
   finished analysis, at a size that fits a card, and it is careful to be a
   different claim: nothing here has been analysed.

   What it shows is how much of the posting's own vocabulary the CV carries --
   arithmetic, free, and computed before any model is called. The tooltip says
   so, because "68%" on a job card invites being read as a verdict, and the
   verdict costs an API call and lives behind "Match against my CV". */

const SIZE = 52;
const STROKE = 5;
const R = (SIZE - STROKE) / 2;
const C = 2 * Math.PI * R;

const en = {
  /* Deliberately "of this posting's wording", not "match": the number is a
     measure of overlap, and saying so is what keeps it honest. */
  explain: (pct: number) =>
    `Your CV carries ${pct}% of this posting's wording. Counted, not analysed — ` +
    `run the match for a real score.`,
};

const ar: typeof en = {
  explain: (pct: number) =>
    `سيرتك الذاتية تتضمن ${pct}% من مفردات هذا الإعلان. إحصاء، لا تحليل — ` +
    `شغّل المطابقة للحصول على تقييم حقيقي.`,
};

const TEXT = { en, ar };

export default function MatchBadge({ coverage }: { coverage: number }) {
  const t = useText(TEXT);
  const bands = useText(BAND_TEXT);
  const band = coverageBand(coverage);
  const pct = Math.round(coverage * 100);
  /* The arc is drawn against a 60% ceiling, not 100. Coverage above that does
     not happen on a real advert, so a full-scale ring would leave every badge
     looking a third full and tell the eye nothing. */
  const filled = Math.min(1, coverage / 0.6);

  return (
    <div className={`match-badge ${band}`} title={t.explain(pct)}>
      <div className="badge-ring">
        <svg viewBox={`0 0 ${SIZE} ${SIZE}`} aria-hidden="true">
          <circle
            className="badge-track"
            cx={SIZE / 2}
            cy={SIZE / 2}
            r={R}
            fill="none"
            strokeWidth={STROKE}
          />
          <circle
            className="badge-value"
            cx={SIZE / 2}
            cy={SIZE / 2}
            r={R}
            fill="none"
            strokeWidth={STROKE}
            strokeLinecap="round"
            strokeDasharray={C}
            strokeDashoffset={C * (1 - filled)}
          />
        </svg>
        <span className="badge-num">{pct}</span>
      </div>
      <span className="badge-band">{bands[band]}</span>
    </div>
  );
}
