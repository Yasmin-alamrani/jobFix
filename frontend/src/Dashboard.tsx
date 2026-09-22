import { useMemo, useState } from 'react';
import { arCount, useText } from './i18n';
import MatchRing from './MatchRing';
import type {
  AnalysisResult,
  Deduction,
  Requirement,
  RequirementCategory,
  Severity,
  SubScore,
} from './types';

const CATEGORY_ORDER: RequirementCategory[] = [
  'skill', 'experience', 'education', 'certification', 'language', 'location',
];

const en = {
  status: { present: 'met', weak: 'partly met', missing: 'missing' },
  category: {
    skill: 'Skills',
    experience: 'Experience',
    education: 'Education',
    certification: 'Certifications',
    language: 'Languages',
    location: 'Location & visa',
  } as Record<RequirementCategory, string>,
  severity: { critical: 'critical', major: 'major', minor: 'minor' } as Record<Severity, string>,
  mustHave: 'Must-have',
  niceToHave: 'Nice to have',
  noneStated: 'None stated.',
  starting: 'Starting score',
  more: (n: number, total: string) =>
    `+ ${n} smaller ${n === 1 ? 'deduction' : 'deductions'} totalling −${total}`,
  outOf: 'out of 100',
  points: (p: string) => `−${p} pts`,
  fix: 'Fix:',
  noRequirements: 'No requirements were extracted from this job description.',
  requirement: 'Requirement',
  type: 'Type',
  weight: 'Weight',
  statusHead: 'Status',
  evidence: 'Evidence in your resume',
  required: 'required',
  preferred: 'preferred',
  noEdits: 'No wording changes suggested — the writing holds up.',
  accepted: (a: number, n: number) => `${a} of ${n} accepted. Nothing is rewritten until you say so.`,
  accept: 'Accept',
  reject: 'Reject',
  howReached: 'How the score was reached',
  whereSit: 'Where the points sit',
  fixFirst: 'Fix these first',
  fromPosting: 'Requirements from the posting',
  suggested: 'Suggested edits',
  measured: 'What the parser measured',
  pages: 'pages',
  characters: 'characters',
  language: 'language',
  bilingual: 'bilingual',
  sections: 'sections',
  noneFound: 'none found',
  yes: 'true',
  no: 'false',
};

const ar: typeof en = {
  status: { present: 'مستوفى', weak: 'مستوفى جزئيًا', missing: 'مفقود' },
  category: {
    skill: 'المهارات',
    experience: 'الخبرة',
    education: 'التعليم',
    certification: 'الشهادات',
    language: 'اللغات',
    location: 'الموقع والتأشيرة',
  },
  severity: { critical: 'حرج', major: 'متوسط', minor: 'بسيط' },
  mustHave: 'أساسي',
  niceToHave: 'مفضَّل',
  noneStated: 'لا شيء مذكور.',
  starting: 'الدرجة الابتدائية',
  more: (n: number, total: string) =>
    `+ ${arCount(n, { one: 'خصم أصغر', two: 'خصمان أصغر', few: 'خصومات أصغر', many: 'خصمًا أصغر' })} بمجموع −${total}`,
  outOf: 'من 100',
  points: (p: string) => `−${p} نقطة`,
  fix: 'الإصلاح:',
  noRequirements: 'لم تُستخرج أي متطلبات من هذا الوصف الوظيفي.',
  requirement: 'المتطلب',
  type: 'النوع',
  weight: 'الأهمية',
  statusHead: 'الحالة',
  evidence: 'الدليل في سيرتك الذاتية',
  required: 'مطلوب',
  preferred: 'مفضَّل',
  noEdits: 'لا تعديلات مقترحة على الصياغة — الكتابة جيدة.',
  accepted: (a: number, n: number) => `قُبل ${a} من ${n}. لا يُعاد كتابة شيء حتى توافق.`,
  accept: 'قبول',
  reject: 'رفض',
  howReached: 'كيف حُسبت الدرجة',
  whereSit: 'توزيع النقاط',
  fixFirst: 'أصلح هذه أولًا',
  fromPosting: 'متطلبات الإعلان',
  suggested: 'تعديلات مقترحة',
  measured: 'ما قاسه المحلّل',
  pages: 'الصفحات',
  characters: 'الأحرف',
  language: 'اللغة',
  bilingual: 'ثنائية اللغة',
  sections: 'الأقسام',
  noneFound: 'لم يُعثر على شيء',
  yes: 'نعم',
  no: 'لا',
};

const TEXT = { en, ar };

/* Must-haves against nice-to-haves, grouped the way a recruiter reads a
   posting. Each pill is coloured by whether the CV meets it. */
function Breakdown({ requirements }: { requirements: Requirement[] }) {
  const t = useText(TEXT);
  if (requirements.length === 0) return null;
  const groups = (importance: 'critical' | 'preferred') =>
    CATEGORY_ORDER.map((category) => ({
      category,
      items: requirements.filter(
        (r) => r.importance === importance && (r.category ?? 'skill') === category,
      ),
    })).filter((g) => g.items.length > 0);

  return (
    <div className="breakdown">
      {(['critical', 'preferred'] as const).map((importance) => (
        <div key={importance}>
          <h4>{importance === 'critical' ? t.mustHave : t.niceToHave}</h4>
          {groups(importance).length === 0 ? (
            <p className="empty">{t.noneStated}</p>
          ) : (
            groups(importance).map((g) => (
              <div className="breakdown-group" key={g.category}>
                <span className="label-text">{t.category[g.category]}</span>
                <div className="chips" dir="auto">
                  {g.items.map((r, i) => (
                    <span className={`pill ${r.status}`} key={i} title={t.status[r.status]}>
                      {r.skill}
                    </span>
                  ))}
                </div>
              </div>
            ))
          )}
        </div>
      ))}
    </div>
  );
}

/* The ledger is the page's argument: the score is arithmetic, so it is shown
   as arithmetic. Every line names the rule that cost the points. */
function Ledger({ result }: { result: AnalysisResult }) {
  const t = useText(TEXT);
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
        <span className="what">{t.starting}</span>
        <span className="rule-id" />
      </div>

      {shown.map((d, i) => (
        <div className={`ledger-line ${d.severity}`} key={`${d.rule}-${i}`}>
          <span className="amount">−{d.points.toFixed(1)}</span>
          <span className="what">{d.title}</span>
          <span className="rule-id">{d.rule}</span>
        </div>
      ))}

      {rest.length > 0 && <div className="ledger-more">{t.more(rest.length, restTotal.toFixed(1))}</div>}

      <div className="ledger-rule" />
      <div className="ledger-total">
        <span className="figure">{result.overall_score.toFixed(1)}</span>
        <span className="of">{t.outOf}</span>
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
  const t = useText(TEXT);
  return (
    <article className={`finding ${d.severity}`}>
      <div className="finding-head">
        <h3>{d.title}</h3>
        <span className="cost">{t.points(d.points.toFixed(1))}</span>
      </div>
      <pre className="evidence" dir="auto">{d.evidence}</pre>
      <p className="fix">
        <strong>{t.fix}</strong> {d.fix}
      </p>
    </article>
  );
}

function Requirements({ requirements }: { requirements: Requirement[] }) {
  const t = useText(TEXT);
  if (requirements.length === 0) {
    return <p className="empty">{t.noRequirements}</p>;
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
            <th>{t.requirement}</th>
            <th>{t.type}</th>
            <th>{t.weight}</th>
            <th>{t.statusHead}</th>
            <th>{t.evidence}</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((r, i) => (
            <tr key={`${r.skill}-${i}`}>
              <td dir="auto">{r.skill}</td>
              <td className="q">{t.category[r.category ?? 'skill'].toLowerCase()}</td>
              <td>
                <span
                  className={`pill ${r.importance === 'critical' ? 'critical-req' : 'preferred'}`}
                >
                  {r.importance === 'critical' ? t.required : t.preferred}
                </span>
              </td>
              <td>
                <span className={`pill ${r.status}`}>{t.status[r.status]}</span>
              </td>
              <td className="q" dir="auto">{r.evidence || (r.note ? r.note : '—')}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* Redlines are proposals, never silent rewrites: the user decides each one. */
function Redlines({ result }: { result: AnalysisResult }) {
  const t = useText(TEXT);
  const [decisions, setDecisions] = useState<Record<number, 'accepted' | 'rejected' | undefined>>({});
  const issues = result.writing.issues;

  if (issues.length === 0) {
    return <p className="empty">{t.noEdits}</p>;
  }

  const accepted = Object.values(decisions).filter((d) => d === 'accepted').length;

  return (
    <>
      <p className="note" style={{ marginBottom: '1rem' }}>
        {t.accepted(accepted, issues.length)}
      </p>
      {issues.map((issue, i) => (
        <article className={`redline ${decisions[i] ?? ''}`} key={i}>
          <div className="finding-head">
            <h3>{issue.section}</h3>
            <span className={`cost ${issue.severity}`}>{t.severity[issue.severity]}</span>
          </div>
          <div className="diff">
            <div className="diff-side was" dir="auto">{issue.original}</div>
            <div className="diff-side now" dir="auto">{issue.suggested}</div>
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
              {t.accept}
            </button>
            <button
              type="button"
              aria-pressed={decisions[i] === 'rejected'}
              onClick={() =>
                setDecisions((d) => ({ ...d, [i]: d[i] === 'rejected' ? undefined : 'rejected' }))
              }
            >
              {t.reject}
            </button>
          </div>
        </article>
      ))}
    </>
  );
}

export default function Dashboard({ result }: { result: AnalysisResult }) {
  const t = useText(TEXT);
  const facts = result.parse_facts as Record<string, unknown>;
  return (
    <>
      <section className="score-head">
        <MatchRing score={result.overall_score} subScores={result.sub_scores} />
        <div className="score-head-main">
          <div className="eyebrow">{t.howReached}</div>
          <Ledger result={result} />
        </div>
      </section>

      <section>
        <div className="eyebrow">{t.whereSit}</div>
        <Bars subScores={result.sub_scores} />
      </section>

      {result.top_fixes.length > 0 && (
        <section>
          <div className="eyebrow">{t.fixFirst}</div>
          {result.top_fixes.map((d, i) => (
            <Finding d={d} key={`${d.rule}-${i}`} />
          ))}
        </section>
      )}

      <section>
        <div className="eyebrow">{t.fromPosting}</div>
        <Breakdown requirements={result.requirements} />
        <Requirements requirements={result.requirements} />
      </section>

      <section>
        <div className="eyebrow">{t.suggested}</div>
        {result.writing.summary_verdict && (
          <p className="verdict" style={{ marginBottom: '1.25rem' }}>
            {result.writing.summary_verdict}
          </p>
        )}
        <Redlines result={result} />
      </section>

      <section>
        <div className="eyebrow">{t.measured}</div>
        <div className="facts">
          <span>{t.pages}: {String(facts.page_count ?? '—')}</span>
          <span>{t.characters}: {String(facts.char_count ?? '—')}</span>
          <span>{t.language}: {String(facts.primary_language ?? '—')}</span>
          <span>{t.bilingual}: {facts.is_bilingual ? t.yes : t.no}</span>
          <span>
            {t.sections}: {(facts.detected_sections as string[] | undefined)?.join(', ') || t.noneFound}
          </span>
        </div>
      </section>
    </>
  );
}
