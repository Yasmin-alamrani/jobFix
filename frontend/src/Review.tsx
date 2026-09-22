import type { ReactNode } from 'react';
import { arCount, useText } from './i18n';
import type { CvReview, ReviewCheck, ReviewWeakness, Severity } from './types';

/* The report reads as one checklist: a line per thing that was looked at,
   ticked when it passes and marked when it does not, with the evidence folded
   away until asked for. What passes matters as much as what fails -- a page of
   nothing but problems does not tell the user their contact details are fine. */

const SLOT = /(\[add [^[\]\n]{1,80}\])/i;

/* Every check the CV is put through, and which of the server's rules would
   fail it. A group with no failing rule is a line the user has passed. */
const GROUPS: { key: 'contact' | 'sections' | 'layout' | 'results' | 'links'; rules: string[] }[] = [
  {
    key: 'contact',
    rules: ['ats.no_email', 'ats.no_phone', 'content.no_email', 'content.no_phone',
            'fmt.phone_not_e164', 'ats.header_footer'],
  },
  {
    key: 'sections',
    rules: ['content.no_summary', 'content.no_experience', 'content.no_education',
            'content.no_skills', 'fmt.nonstandard_headings', 'fmt.missing_sections'],
  },
  {
    key: 'layout',
    rules: ['ats.no_text_layer', 'ats.multi_column', 'ats.tables',
            'ats.fonts_not_embedded', 'fmt.too_long'],
  },
  {
    key: 'results',
    rules: ['content.few_numbers', 'content.roles_without_bullets',
            'content.roles_without_dates'],
  },
  { key: 'links', rules: ['content.no_links'] },
];

const en = {
  severity: { critical: 'Fix first', major: 'Important', minor: 'Polish' } as Record<Severity, string>,
  area: {
    impact: 'Impact',
    clarity: 'Clarity',
    summary: 'Summary',
    skills: 'Skills',
    structure: 'Structure',
    consistency: 'Consistency',
    language: 'Language',
    completeness: 'Missing information',
  } as Record<string, string>,
  group: {
    contact: 'Contact details',
    sections: 'Section headings',
    layout: 'Layout an ATS can read',
    results: 'Results, dates and descriptions',
    links: 'Links to your work',
  } as Record<string, string>,
  pass: {
    contact: 'Your email and phone are where a parser can read them.',
    sections: 'Summary, experience, education and skills are all present and named as expected.',
    layout: 'One column, no tables, and nothing hidden in a page header.',
    results: 'Your bullet points carry numbers, and every role has dates and a description.',
    links: 'Your CV points to your profile or your work.',
  } as Record<string, string>,
  notChecked: 'Not checked: this CV was pasted as text, so it has no layout of its own. Upload the file to check columns, tables and headers.',
  writing: 'How it reads',
  writingPass: 'Nothing to change in the writing itself.',
  issues: (n: number) => (n === 1 ? '1 to fix' : `${n} to fix`),
  allGood: 'All clear',
  details: 'Show details',
  why: 'Why it matters:',
  whatToDo: 'What to do:',
  exampleWithheld:
    'An example rewrite was left out because it added details that are not in this part of your CV.',
  withheld: (n: number) =>
    `${n} point${n > 1 ? 's were' : ' was'} left out because the text quoted could not be found in your CV.`,
  works: 'What already works',
  summaryLine: (bad: number, good: number) =>
    `${bad === 0 ? 'Nothing' : bad} to fix · ${good} already right`,
};

const ar: typeof en = {
  severity: { critical: 'أصلحه أولًا', major: 'مهم', minor: 'تحسين' },
  area: {
    impact: 'الأثر',
    clarity: 'الوضوح',
    summary: 'الملخص',
    skills: 'المهارات',
    structure: 'البنية',
    consistency: 'الاتساق',
    language: 'اللغة',
    completeness: 'معلومات ناقصة',
  },
  group: {
    contact: 'بيانات التواصل',
    sections: 'عناوين الأقسام',
    layout: 'تنسيق تقرؤه أنظمة التوظيف',
    results: 'النتائج والتواريخ والوصف',
    links: 'روابط أعمالك',
  },
  pass: {
    contact: 'بريدك الإلكتروني ورقمك في مكان تقرؤه أنظمة القراءة.',
    sections: 'الملخص والخبرة والتعليم والمهارات موجودة كلها وبعناوين مألوفة.',
    layout: 'عمود واحد، بلا جداول، ولا شيء مخفي في رأس الصفحة.',
    results: 'نقاطك تتضمن أرقامًا، ولكل دور تواريخ ووصف.',
    links: 'سيرتك الذاتية تشير إلى ملفك أو أعمالك.',
  },
  notChecked:
    'لم يُفحص: لُصقت هذه السيرة الذاتية كنص، فلا تنسيق لها. ارفع الملف لفحص الأعمدة والجداول ورؤوس الصفحات.',
  writing: 'كيف تُقرأ',
  writingPass: 'لا شيء يحتاج إلى تغيير في الصياغة نفسها.',
  issues: (n: number) =>
    arCount(n, { one: 'نقطة واحدة للإصلاح', two: 'نقطتان للإصلاح', few: 'نقاط للإصلاح', many: 'نقطة للإصلاح' }),
  allGood: 'سليم',
  details: 'اعرض التفاصيل',
  why: 'لماذا يهم:',
  whatToDo: 'ما العمل:',
  exampleWithheld:
    'حُذف مثال إعادة الصياغة لأنه أضاف تفاصيل غير موجودة في هذا الجزء من سيرتك الذاتية.',
  withheld: (n: number) =>
    `حُذفت ${arCount(n, { one: 'نقطة واحدة', two: 'نقطتان', few: 'نقاط', many: 'نقطة' })} ` +
    'لأن النص المقتبس لم يُعثر عليه في سيرتك الذاتية.',
  works: 'ما يعمل جيدًا',
  summaryLine: (bad: number, good: number) =>
    `${bad === 0 ? 'لا شيء' : bad} للإصلاح · ${good} سليم بالفعل`,
};

const TEXT = { en, ar };
type T = typeof en;

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

function Row({
  ok,
  severity,
  title,
  note,
  tag,
  children,
}: {
  ok: boolean;
  severity?: Severity;
  title: string;
  note?: string;
  tag?: string;
  children?: ReactNode;
}) {
  const t = useText(TEXT);
  return (
    <li className={`check-row ${ok ? 'ok' : severity ?? 'major'}`}>
      <span className="mark" aria-hidden="true">{ok ? '✓' : '✕'}</span>
      <div className="check-body">
        <p className="check-title">
          <strong>{title}</strong>
          {tag && <span className="check-tag">{tag}</span>}
        </p>
        {note && <p className="check-note">{note}</p>}
        {children && (
          <details>
            <summary>{t.details}</summary>
            <div className="check-detail">{children}</div>
          </details>
        )}
      </div>
    </li>
  );
}

function CheckRow({ check }: { check: ReviewCheck }) {
  const t = useText(TEXT);
  return (
    <Row ok={false} severity={check.severity} title={check.title} tag={t.severity[check.severity]}>
      <pre className="evidence" dir="auto">{check.evidence}</pre>
      <p className="fix">
        <strong>{t.whatToDo}</strong> {check.fix}
      </p>
    </Row>
  );
}

function WeaknessRow({ w }: { w: ReviewWeakness }) {
  const t = useText(TEXT);
  return (
    <Row
      ok={false}
      severity={w.severity}
      title={w.title}
      note={t.area[w.area] ?? w.area}
      tag={t.severity[w.severity]}
    >
      {w.evidence && w.example ? (
        <div className="diff">
          <div className="diff-side was" dir="auto">{w.evidence}</div>
          <div className="diff-side now" dir="auto">
            <WithSlots text={w.example} />
          </div>
        </div>
      ) : w.evidence ? (
        <pre className="evidence" dir="auto">{w.evidence}</pre>
      ) : w.example ? (
        <div className="diff">
          <div className="diff-side now" dir="auto">
            <WithSlots text={w.example} />
          </div>
        </div>
      ) : null}
      <p className="fix">
        <strong>{t.why}</strong> {w.problem}
      </p>
      <p className="fix">
        <strong>{t.whatToDo}</strong> {w.recommendation}
      </p>
      {w.example_withheld && <p className="note">{t.exampleWithheld}</p>}
    </Row>
  );
}

function Group({
  title,
  failing,
  passLine,
  children,
}: {
  title: string;
  failing: number;
  passLine: string;
  children?: ReactNode;
}) {
  const t = useText(TEXT);
  return (
    <section className="check-group">
      <div className="check-head">
        <h4>{title}</h4>
        <span className={failing ? 'count bad' : 'count ok'}>
          {failing ? t.issues(failing) : t.allGood}
        </span>
      </div>
      <ul className="check-list">
        {children ?? <Row ok title={passLine} />}
      </ul>
    </section>
  );
}

export default function Review({ review }: { review: CvReview }) {
  const t: T = useText(TEXT);

  const grouped = GROUPS.map((group) => ({
    key: group.key,
    checks: review.checks.filter((c) => group.rules.includes(c.rule)),
  }));
  // Anything the server flagged that no group claims still has to be shown.
  const claimed = new Set(GROUPS.flatMap((g) => g.rules));
  const other = review.checks.filter((c) => !claimed.has(c.rule));

  const problems = review.checks.length + review.weaknesses.length;
  const passing =
    grouped.filter((g) => g.checks.length === 0).length + (review.weaknesses.length ? 0 : 1);

  return (
    <div className="review">
      {review.verdict && <p className="verdict">{review.verdict}</p>}
      <p className="review-tally">{t.summaryLine(problems, passing)}</p>

      {grouped.map(({ key, checks }) => (
        <Group
          key={key}
          title={t.group[key]}
          failing={checks.length}
          passLine={
            key === 'layout' && !review.layout_checked ? t.notChecked : t.pass[key]
          }
        >
          {checks.length > 0
            ? checks.map((c) => <CheckRow check={c} key={c.rule} />)
            : undefined}
        </Group>
      ))}

      <Group title={t.writing} failing={review.weaknesses.length} passLine={t.writingPass}>
        {review.weaknesses.length > 0
          ? review.weaknesses.map((w, i) => <WeaknessRow w={w} key={`${w.title}-${i}`} />)
          : undefined}
      </Group>

      {other.length > 0 && (
        <ul className="check-list">
          {other.map((c) => (
            <CheckRow check={c} key={c.rule} />
          ))}
        </ul>
      )}

      {review.withheld > 0 && <p className="note">{t.withheld(review.withheld)}</p>}

      {review.strengths.length > 0 && (
        <section className="check-group">
          <div className="check-head">
            <h4>{t.works}</h4>
          </div>
          <ul className="check-list">
            {review.strengths.map((s, i) => (
              <Row ok title={s.point} key={i}>
                <span className="q" dir="auto">“{s.evidence}”</span>
              </Row>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
