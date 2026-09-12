import { useEffect, useMemo, useState } from 'react';
import { createTailorProposal, saveVersion } from './api';
import type { CvVersion, TailorEdit, TailorProposal, TailorTarget } from './types';

type Decision = 'accepted' | 'rejected';

const PLACEHOLDER_SPLIT = /(\[add [^[\]\n]{1,40}\])/i;
const IS_PLACEHOLDER = /^\[add [^[\]\n]{1,40}\]$/i;

/* A placeholder is the one thing an edit may add that the CV does not say: a
   slot for the user's own real figure. It is highlighted so it cannot be sent
   to an employer by accident. */
function Filled({ text }: { text: string }) {
  return (
    <>
      {text.split(PLACEHOLDER_SPLIT).map((part, i) =>
        IS_PLACEHOLDER.test(part) ? (
          <mark className="placeholder" key={i} title="Replace with your real figure, or delete it">
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
   an Arabic bullet lay out right to left. */
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

function defaultName(p: TailorProposal) {
  return [p.job_title, p.company].filter(Boolean).join(' — ') || 'Tailored CV';
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
  /* Captured once. The parent builds `target` afresh on every render, and a new
     object each time would re-run the effect below -- and the model call in it. */
  const [initialTarget] = useState(target);
  const [proposal, setProposal] = useState<TailorProposal | null>(null);
  const [decisions, setDecisions] = useState<Record<string, Decision>>({});
  const [name, setName] = useState('');
  const [working, setWorking] = useState<string | null>('Reading the posting against your CV');
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState<CvVersion | null>(null);
  const [showWithheld, setShowWithheld] = useState(false);

  useEffect(() => {
    let cancelled = false;
    createTailorProposal({ resumeId, target: initialTarget })
      .then((p) => {
        if (cancelled) return;
        setProposal(p);
        setName(defaultName(p));
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Could not tailor for that job.');
      })
      .finally(() => {
        if (!cancelled) setWorking(null);
      });
    return () => {
      cancelled = true;
    };
  }, [resumeId, initialTarget]);

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
    setWorking('Saving');
    try {
      setSaved(await saveVersion(proposal.proposal_id, name, accepted.map((e) => e.id)));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not save that version.');
    } finally {
      setWorking(null);
    }
  }

  const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? '' : 's'}`;

  return (
    <section className="tailor">
      <div className="tailor-head">
        <h3>Tailor for {proposal ? defaultName(proposal) : 'this job'}</h3>
        <button type="button" className="ledger-more" onClick={onClose}>
          Close
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
            {proposal.edits.length === 0
              ? 'No edits to suggest — your CV already presents what this job asks for as well as its own wording allows.'
              : `${plural(proposal.edits.length, 'suggested edit')}. Nothing changes until you accept it.`}{' '}
            Every suggestion only rewords, reorders or re-emphasises what your CV already says.
          </p>

          {proposal.edits.length > 0 && (
            <div className="actions" style={{ marginBottom: '1rem' }}>
              <button type="button" onClick={() => decideAll('accepted')}>
                Accept all
              </button>
              <button type="button" onClick={() => decideAll('rejected')}>
                Reject all
              </button>
            </div>
          )}

          {proposal.edits.map((edit) => (
            <article className={`redline ${decisions[edit.id] ?? ''}`} key={edit.id}>
              <div className="finding-head">
                <strong>{edit.label}</strong>
                {edit.requirement && <span className="pill">{edit.requirement}</span>}
              </div>
              {edit.why && <p className="note">{edit.why}</p>}
              <Change edit={edit} />
              {edit.kind === 'add_skill' && edit.evidence && (
                <p className="note">Shown in your CV: “{edit.evidence}”</p>
              )}
              {edit.has_placeholder && (
                <p className="fix">
                  Replace the highlighted placeholder with your real figure before you send this
                  CV, or delete it. Never estimate one.
                </p>
              )}
              <div className="actions">
                <button
                  type="button"
                  aria-pressed={decisions[edit.id] === 'accepted'}
                  onClick={() => decide(edit.id, 'accepted')}
                >
                  Accept
                </button>
                <button
                  type="button"
                  aria-pressed={decisions[edit.id] === 'rejected'}
                  onClick={() => decide(edit.id, 'rejected')}
                >
                  Reject
                </button>
              </div>
            </article>
          ))}

          {proposal.gaps.length > 0 && (
            <>
              <h4>Gaps — not edits</h4>
              <p className="note">
                The posting asks for these and your CV does not show them, so they are not added
                to it. Close them for real, or add them yourself if you have the experience and
                left it off.
              </p>
              <ul className="gaps">
                {proposal.gaps.map((gap) => (
                  <li key={gap.requirement}>
                    <span className={`pill ${gap.importance === 'critical' ? 'missing' : 'preferred'}`}>
                      {gap.importance === 'critical' ? 'required' : 'preferred'}
                    </span>{' '}
                    <strong>{gap.requirement}</strong>
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
                {showWithheld ? 'Hide' : 'Show'} {plural(proposal.blocked.length, 'suggestion')}{' '}
                withheld because {proposal.blocked.length === 1 ? 'it' : 'they'} would have added
                something your CV does not say
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
                <span className="label-text">Name this version</span>
                <input type="text" value={name} onChange={(e) => setName(e.target.value)} />
              </label>
              <button type="button" onClick={save} disabled={!!working}>
                Save with {plural(accepted.length, 'edit')}
              </button>
              {undecided > 0 && (
                <span className="cost-note">
                  {undecided} not yet decided — those parts stay as they are.
                </span>
              )}
            </div>
          )}

          {saved && (
            <p className="verdict">
              Saved “{saved.name}”. It is under <strong>Read my CV → Saved versions</strong>.
              {saved.placeholders > 0 &&
                ` It has ${plural(saved.placeholders, 'placeholder')} to fill in before you send it.`}
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
  label = 'Tailor my CV for this job',
}: {
  resumeId: string | null;
  target: TailorTarget;
  label?: string;
}) {
  const [open, setOpen] = useState(false);
  if (!resumeId) return null;
  if (open) return <Tailor resumeId={resumeId} target={target} onClose={() => setOpen(false)} />;
  return (
    <div className="score-bar tailor-launch">
      <button type="button" onClick={() => setOpen(true)}>
        {label}
      </button>
      <span className="cost-note">One model call. Suggests edits; changes nothing until you accept them.</span>
    </div>
  );
}
