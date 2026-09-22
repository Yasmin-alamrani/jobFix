import { useEffect, useMemo, useState } from 'react';
import { createTailorProposal, saveVersion } from './api';
import { arCount, useText } from './i18n';
import type { CvVersion, TailorEdit, TailorProposal, TailorTarget } from './types';

type Decision = 'accepted' | 'rejected';

const PLACEHOLDER_SPLIT = /(\[add [^[\]\n]{1,40}\])/i;
const IS_PLACEHOLDER = /^\[add [^[\]\n]{1,40}\]$/i;

const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? '' : 's'}`;

const en = {
  placeholderTitle: 'Replace with your real figure, or delete it',
  tailoredCv: 'Tailored CV',
  readingPosting: 'Reading the posting against your CV',
  saving: 'Saving',
  tailorFailed: 'Could not tailor for that job.',
  saveFailed: 'Could not save that version.',
  head: (name: string) => `Tailor for ${name}`,
  thisJob: 'this job',
  close: 'Close',
  noEdits:
    'No edits to suggest — your CV already presents what this job asks for as well as its own wording allows.',
  count: (n: number) => `${plural(n, 'suggested edit')}. Nothing changes until you accept it.`,
  always: 'Every suggestion only rewords, reorders or re-emphasises what your CV already says.',
  acceptAll: 'Accept all',
  rejectAll: 'Reject all',
  accept: 'Accept',
  reject: 'Reject',
  shownIn: (q: string) => `Shown in your CV: “${q}”`,
  placeholderFix:
    'Replace the highlighted placeholder with your real figure before you send this CV, or delete it. Never estimate one.',
  gapsTitle: 'Gaps — not edits',
  gapsNote:
    'The posting asks for these and your CV does not show them, so they are not added to it. ' +
    'Close them for real, or add them yourself if you have the experience and left it off.',
  required: 'required',
  preferred: 'preferred',
  withheld: (show: boolean, n: number) =>
    `${show ? 'Hide' : 'Show'} ${plural(n, 'suggestion')} withheld because ` +
    `${n === 1 ? 'it' : 'they'} would have added something your CV does not say`,
  nameVersion: 'Name this version',
  saveWith: (n: number) => `Save with ${plural(n, 'edit')}`,
  undecided: (n: number) => `${n} not yet decided — those parts stay as they are.`,
  savedA: (name: string) => `Saved “${name}”. It is under `,
  savedWhere: 'Read my CV → Saved versions',
  savedB: (n: number) =>
    `.${n > 0 ? ` It has ${plural(n, 'placeholder')} to fill in before you send it.` : ''}`,
  launch: 'Tailor my CV for this job',
  launchNote: 'One model call. Suggests edits; changes nothing until you accept them.',
};

const ar: typeof en = {
  placeholderTitle: 'استبدلها برقمك الحقيقي أو احذفها',
  tailoredCv: 'سيرة ذاتية مخصّصة',
  readingPosting: 'جارٍ قراءة الإعلان مقابل سيرتك الذاتية',
  saving: 'جارٍ الحفظ',
  tailorFailed: 'تعذّر التخصيص لهذه الوظيفة.',
  saveFailed: 'تعذّر حفظ هذه النسخة.',
  head: (name: string) => `خصّص لـ${name}`,
  thisJob: 'هذه الوظيفة',
  close: 'إغلاق',
  noEdits: 'لا تعديلات مقترحة — سيرتك الذاتية تعرض ما تطلبه هذه الوظيفة بأفضل ما تسمح به صياغتها.',
  count: (n: number) =>
    `${arCount(n, { one: 'تعديل مقترح واحد', two: 'تعديلان مقترحان', few: 'تعديلات مقترحة', many: 'تعديلًا مقترحًا' })}. ` +
    'لا يتغير شيء حتى تقبله.',
  always: 'كل اقتراح يعيد صياغة ما تقوله سيرتك الذاتية أو يعيد ترتيبه أو إبرازه فقط.',
  acceptAll: 'قبول الكل',
  rejectAll: 'رفض الكل',
  accept: 'قبول',
  reject: 'رفض',
  shownIn: (q: string) => `موجودة في سيرتك الذاتية: «${q}»`,
  placeholderFix:
    'استبدل الخانة المظللة برقمك الحقيقي قبل إرسال هذه السيرة الذاتية، أو احذفها. لا تقدّر رقمًا أبدًا.',
  gapsTitle: 'فجوات — لا تعديلات',
  gapsNote:
    'يطلب الإعلان هذه الأمور ولا تُظهرها سيرتك الذاتية، لذا لا تُضاف إليها. اسدّها فعلًا، أو ' +
    'أضفها بنفسك إن كانت لديك الخبرة وأغفلتها.',
  required: 'مطلوب',
  preferred: 'مفضَّل',
  withheld: (show: boolean, n: number) =>
    `${show ? 'إخفاء' : 'عرض'} ` +
    `${arCount(n, { one: 'اقتراح واحد محجوب', two: 'اقتراحين محجوبين', few: 'اقتراحات محجوبة', many: 'اقتراحًا محجوبًا' })} ` +
    'لأنها كانت ستضيف شيئًا لا تقوله سيرتك الذاتية',
  nameVersion: 'سمِّ هذه النسخة',
  saveWith: (n: number) =>
    `احفظ مع ${arCount(n, { one: 'تعديل واحد', two: 'تعديلين', few: 'تعديلات', many: 'تعديلًا' })}`,
  undecided: (n: number) => `${n} لم يُحسم بعد — تبقى تلك الأجزاء كما هي.`,
  savedA: (name: string) => `حُفظت «${name}». ستجدها في `,
  savedWhere: 'اقرأ سيرتي الذاتية ← النسخ المحفوظة',
  savedB: (n: number) =>
    `.${n > 0 ? ` فيها ${arCount(n, { one: 'خانة واحدة', two: 'خانتان', few: 'خانات', many: 'خانة' })} يجب ملؤها قبل الإرسال.` : ''}`,
  launch: 'خصّص سيرتي الذاتية لهذه الوظيفة',
  launchNote: 'استدعاء واحد للنموذج. يقترح تعديلات ولا يغيّر شيئًا حتى تقبلها.',
};

const TEXT = { en, ar };

/* A placeholder is the one thing an edit may add that the CV does not say: a
   slot for the user's own real figure. It is highlighted so it cannot be sent
   to an employer by accident. */
export function Filled({ text }: { text: string }) {
  const t = useText(TEXT);
  return (
    <>
      {text.split(PLACEHOLDER_SPLIT).map((part, i) =>
        IS_PLACEHOLDER.test(part) ? (
          <mark className="placeholder" key={i} title={t.placeholderTitle}>
            {part}
          </mark>
        ) : (
          <span key={i}>{part}</span>
        ),
      )}
    </>
  );
}

/* One redline rather than two blocks side by side. The server's diff reproduces
   both versions exactly, so struck and inserted runs can be interleaved in place
   and the reader sees what changed without comparing by eye. `dir="auto"` lets
   an Arabic bullet lay out right to left, and an English one left to right. */
function Change({ edit }: { edit: TailorEdit }) {
  if (edit.kind === 'rewrite') {
    return (
      <div className="diff-inline" dir="auto">
        {edit.diff.map((op, i) =>
          op.op === 'equal' ? (
            <span key={i}>{op.text}</span>
          ) : op.op === 'delete' ? (
            <del key={i}>{op.text}</del>
          ) : (
            <ins key={i}>
              <Filled text={op.text} />
            </ins>
          ),
        )}
      </div>
    );
  }

  if (edit.kind === 'reorder') {
    return (
      <div className="diff">
        <ol className="diff-side was" dir="auto">
          {edit.before_items.map((item, i) => (
            <li key={i}>{item}</li>
          ))}
        </ol>
        <ol className="diff-side now" dir="auto">
          {edit.after_items.map((item, i) => (
            <li key={i} className={edit.order[i] !== i ? 'moved' : undefined}>
              {item}
            </li>
          ))}
        </ol>
      </div>
    );
  }

  return (
    <div className="diff-inline" dir="auto">
      <span>{edit.before_items.join(', ')}</span>
      {edit.before_items.length > 0 && <span>, </span>}
      <ins>{edit.after_text}</ins>
    </div>
  );
}

function defaultName(p: TailorProposal, fallback: string) {
  return [p.job_title, p.company].filter(Boolean).join(' — ') || fallback;
}

export default function Tailor({
  resumeId,
  target,
  onClose,
}: {
  resumeId: string;
  target: TailorTarget;
  onClose: () => void;
}) {
  const t = useText(TEXT);
  /* Captured once. The parent builds `target` afresh on every render, and a new
     object each time would re-run the effect below -- and the model call in it. */
  const [initialTarget] = useState(target);
  const [proposal, setProposal] = useState<TailorProposal | null>(null);
  const [decisions, setDecisions] = useState<Record<string, Decision>>({});
  const [name, setName] = useState('');
  const [working, setWorking] = useState<string | null>(t.readingPosting);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState<CvVersion | null>(null);
  const [showWithheld, setShowWithheld] = useState(false);
  const [fallbacks] = useState({ name: t.tailoredCv, failed: t.tailorFailed });

  useEffect(() => {
    let cancelled = false;
    createTailorProposal({ resumeId, target: initialTarget })
      .then((p) => {
        if (cancelled) return;
        setProposal(p);
        setName(defaultName(p, fallbacks.name));
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : fallbacks.failed);
      })
      .finally(() => {
        if (!cancelled) setWorking(null);
      });
    return () => {
      cancelled = true;
    };
  }, [resumeId, initialTarget, fallbacks]);

  const accepted = useMemo(
    () => (proposal ? proposal.edits.filter((e) => decisions[e.id] === 'accepted') : []),
    [proposal, decisions],
  );
  const undecided = proposal ? proposal.edits.filter((e) => !decisions[e.id]).length : 0;

  /* Clicking the active choice again clears it: undecided is a real state,
     and it means "leave this part of the CV as it is". */
  function decide(id: string, choice: Decision) {
    setSaved(null);
    setDecisions((prev) => {
      const next = { ...prev };
      if (next[id] === choice) delete next[id];
      else next[id] = choice;
      return next;
    });
  }

  function decideAll(choice: Decision) {
    if (!proposal) return;
    setSaved(null);
    setDecisions(Object.fromEntries(proposal.edits.map((e) => [e.id, choice])));
  }

  /* Only IDs leave the browser. The server applies its own stored copy of each
     accepted edit, so nothing typed or altered here can reach a saved CV. */
  async function save() {
    if (!proposal) return;
    setError(null);
    setWorking(t.saving);
    try {
      setSaved(await saveVersion(proposal.proposal_id, name, accepted.map((e) => e.id)));
    } catch (err) {
      setError(err instanceof Error ? err.message : t.saveFailed);
    } finally {
      setWorking(null);
    }
  }

  return (
    <section className="tailor">
      <div className="tailor-head">
        <h3>{t.head(proposal ? defaultName(proposal, t.tailoredCv) : t.thisJob)}</h3>
        <button type="button" className="ledger-more" onClick={onClose}>
          {t.close}
        </button>
      </div>

      {working && (
        <div className="working">
          <span className="sweep">
            <i />
          </span>
          {working}…
        </div>
      )}
      {error && <p className="error">{error}</p>}

      {proposal && (
        <>
          <p className="note">
            {proposal.edits.length === 0 ? t.noEdits : t.count(proposal.edits.length)} {t.always}
          </p>

          {proposal.edits.length > 0 && (
            <div className="actions" style={{ marginBottom: '1rem' }}>
              <button type="button" onClick={() => decideAll('accepted')}>
                {t.acceptAll}
              </button>
              <button type="button" onClick={() => decideAll('rejected')}>
                {t.rejectAll}
              </button>
            </div>
          )}

          {proposal.edits.map((edit) => (
            <article className={`redline ${decisions[edit.id] ?? ''}`} key={edit.id}>
              <div className="finding-head">
                <strong>{edit.label}</strong>
                {edit.requirement && <span className="pill" dir="auto">{edit.requirement}</span>}
              </div>
              {edit.why && <p className="note">{edit.why}</p>}
              <Change edit={edit} />
              {edit.kind === 'add_skill' && edit.evidence && (
                <p className="note" dir="auto">{t.shownIn(edit.evidence)}</p>
              )}
              {edit.has_placeholder && <p className="fix">{t.placeholderFix}</p>}
              <div className="actions">
                <button
                  type="button"
                  aria-pressed={decisions[edit.id] === 'accepted'}
                  onClick={() => decide(edit.id, 'accepted')}
                >
                  {t.accept}
                </button>
                <button
                  type="button"
                  aria-pressed={decisions[edit.id] === 'rejected'}
                  onClick={() => decide(edit.id, 'rejected')}
                >
                  {t.reject}
                </button>
              </div>
            </article>
          ))}

          {proposal.gaps.length > 0 && (
            <>
              <h4>{t.gapsTitle}</h4>
              <p className="note">{t.gapsNote}</p>
              <ul className="gaps">
                {proposal.gaps.map((gap) => (
                  <li key={gap.requirement}>
                    <span className={`pill ${gap.importance === 'critical' ? 'missing' : 'preferred'}`}>
                      {gap.importance === 'critical' ? t.required : t.preferred}
                    </span>{' '}
                    <strong dir="auto">{gap.requirement}</strong>
                    {gap.advice ? ` — ${gap.advice}` : ''}
                  </li>
                ))}
              </ul>
            </>
          )}

          {proposal.blocked.length > 0 && (
            <div className="withheld">
              <button
                type="button"
                className="ledger-more"
                aria-expanded={showWithheld}
                onClick={() => setShowWithheld(!showWithheld)}
              >
                {t.withheld(showWithheld, proposal.blocked.length)}
              </button>
              {showWithheld && (
                <ul>
                  {proposal.blocked.map((edit) => (
                    <li key={edit.id}>
                      <strong>{edit.label || edit.target}</strong>
                      {edit.after_text && <span dir="auto"> — “{edit.after_text}”</span>}
                      <br />
                      <span className="note">{edit.violations.join(' ')}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}

          {proposal.edits.length > 0 && (
            <div className="save-version">
              <label>
                <span className="label-text">{t.nameVersion}</span>
                <input type="text" dir="auto" value={name} onChange={(e) => setName(e.target.value)} />
              </label>
              <button type="button" onClick={save} disabled={!!working}>
                {t.saveWith(accepted.length)}
              </button>
              {undecided > 0 && <span className="cost-note">{t.undecided(undecided)}</span>}
            </div>
          )}

          {saved && (
            <p className="verdict">
              {t.savedA(saved.name)}
              <strong>{t.savedWhere}</strong>
              {t.savedB(saved.placeholders)}
            </p>
          )}
        </>
      )}
    </section>
  );
}

/* Tailoring costs a model call, so it starts from an explicit click rather than
   automatically wherever a job is shown. */
export function TailorButton({
  resumeId,
  target,
  label,
}: {
  resumeId: string | null;
  target: TailorTarget;
  label?: string;
}) {
  const t = useText(TEXT);
  const [open, setOpen] = useState(false);
  if (!resumeId) return null;
  if (open) return <Tailor resumeId={resumeId} target={target} onClose={() => setOpen(false)} />;
  return (
    <div className="score-bar tailor-launch">
      <button type="button" onClick={() => setOpen(true)}>
        {label ?? t.launch}
      </button>
      <span className="cost-note">{t.launchNote}</span>
    </div>
  );
}
