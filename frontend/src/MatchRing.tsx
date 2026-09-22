import { useEffect, useState } from 'react';
import { useText } from './i18n';
import { BAND_TEXT, scoreBand } from './match';
import type { SubScore } from './types';

/* The headline number. Everything below it on the page is the argument for it;
   this is the verdict, read in one glance.

   The ring is drawn from the score the server computed in Python -- it is not
   a restatement of anything the model said, and the note under it says so,
   because a big confident number is exactly the kind of thing a user is
   entitled to distrust. */

const SIZE = 148;
const STROKE = 10;
const R = (SIZE - STROKE) / 2;
const C = 2 * Math.PI * R;

/* A dimension counts as carried when it kept 70% of its points. Below that
   there is a deduction in the ledger worth reading. */
const CARRIED = 0.7;

const en = {
  rate: 'Match rate',
  computed: 'Worked out in Python from the evidence — not a number the model picked.',
};

const ar: typeof en = {
  rate: 'نسبة التطابق',
  computed: 'محسوبة في بايثون من الأدلة — ليست رقمًا اختاره النموذج.',
};

const TEXT = { en, ar };

function prefersStillness(): boolean {
  return !!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
}

/* Counts from zero to the score once, on arrival. A result that appears
   already finished reads as a number that was sitting there all along; the
   sweep is what makes it read as measured.

   Asked to keep still, the score is derived straight from the prop rather
   than animated into place -- no frames, and nothing to fall out of date if a
   second result arrives. */
function useCountUp(target: number, ms = 1200): number {
  const still = prefersStillness();
  const [swept, setSwept] = useState(0);

  useEffect(() => {
    if (still) return;
    let frame = 0;
    const start = performance.now();
    const step = (now: number) => {
      const p = Math.min(1, (now - start) / ms);
      /* Smoothstep, not an ease-out. A plain ease-out covers most of the
         distance in the first few frames, so the number reads as though it
         had never counted at all; a cubic S-curve overcorrects and holds at
         zero long enough to look stalled. This starts moving at once and
         still spends real time crossing the middle. */
      const eased = p * p * (3 - 2 * p);
      setSwept(target * eased);
      if (p < 1) frame = requestAnimationFrame(step);
    };
    frame = requestAnimationFrame(step);
    return () => cancelAnimationFrame(frame);
  }, [target, ms, still]);

  return still ? target : swept;
}

export default function MatchRing({
  score,
  subScores,
}: {
  score: number;
  subScores: SubScore[];
}) {
  const t = useText(TEXT);
  const bands = useText(BAND_TEXT);
  const band = scoreBand(score);
  const shown = useCountUp(score);
  const offset = C * (1 - Math.min(100, Math.max(0, shown)) / 100);

  return (
    <section className={`match-ring ${band}`}>
      <div className="ring-wrap">
        <svg
          className="ring"
          viewBox={`0 0 ${SIZE} ${SIZE}`}
          role="img"
          aria-label={`${t.rate}: ${Math.round(score)} / 100 — ${bands[band]}`}
        >
          <defs>
            {/* The stops take their colour from the band, through CSS custom
                properties -- var() does not resolve in a presentation
                attribute, so they are set as style rules instead. */}
            <linearGradient id="match-ring-grad" x1="0" y1="1" x2="1" y2="0">
              <stop className="g1" offset="0%" />
              <stop className="g2" offset="100%" />
            </linearGradient>
          </defs>
          <circle
            className="ring-track"
            cx={SIZE / 2}
            cy={SIZE / 2}
            r={R}
            fill="none"
            strokeWidth={STROKE}
          />
          <circle
            className="ring-value"
            cx={SIZE / 2}
            cy={SIZE / 2}
            r={R}
            fill="none"
            strokeWidth={STROKE}
            strokeLinecap="round"
            stroke="url(#match-ring-grad)"
            strokeDasharray={C}
            strokeDashoffset={offset}
          />
        </svg>
        <div className="ring-figure" aria-hidden="true">
          {/* Number and unit share a baseline, so the % sits on the figure
              rather than floating beside it. */}
          <span className="ring-read">
            <span className="ring-num">{Math.round(shown)}</span>
            <span className="ring-pct">%</span>
          </span>
        </div>
      </div>

      <p className="ring-band">{bands[band]}</p>

      <ul className="ring-facts">
        {subScores.map((s) => {
          const carried = s.max_points > 0 && s.earned / s.max_points >= CARRIED;
          return (
            <li className={carried ? 'ok' : 'low'} key={s.key}>
              <span className="tick" aria-hidden="true">{carried ? '✓' : '✕'}</span>
              <span className="what" dir="auto">{s.label}</span>
              <span className="pts">
                {s.earned.toFixed(0)}/{s.max_points.toFixed(0)}
              </span>
            </li>
          );
        })}
      </ul>

      <p className="ring-note">{t.computed}</p>
    </section>
  );
}
