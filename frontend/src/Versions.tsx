import { useEffect, useState } from 'react';
import {
  deleteVersion,
  downloadExport,
  fillPlaceholders,
  getPlaceholders,
  listVersions,
} from './api';
import { Entities } from './CvView';
import { Filled } from './Tailor';
import type { CvProfile, CvVersion, ExportFormat, PlaceholderSlot } from './types';

const HAS_DIGIT = /[0-9٠-٩]/;
const ARABIC_LETTERS = /[؀-ۿ]/g;
const LATIN_LETTERS = /[A-Za-z]/g;

/* The same rule the server uses to lay the export out right to left: Arabic
   letters outnumber Latin ones. Counted over the CV's words, not its JSON, so
   field names cannot tip the balance. */
function isArabic(profile: CvProfile) {
  const text = [
    profile.contact.name,
    profile.summary,
    ...profile.skills,
    ...profile.experience.flatMap((r) => [r.title, r.company, ...r.bullets]),
  ].join(' ');
  return (text.match(ARABIC_LETTERS)?.length ?? 0) > (text.match(LATIN_LETTERS)?.length ?? 0);
}

/* The one place a user types into a saved CV: their own figure for an [add …]
   slot. The other way out -- "I don't have this figure" -- restores the item's
   original wording rather than deleting the placeholder, which would leave a
   sentence hanging. The server enforces both; this form just asks. */
function PlaceholderForm({
  version,
  onDone,
  onCancel,
}: {
  version: CvVersion;
  onDone: (updated: CvVersion) => void;
  onCancel: () => void;
}) {
  const [slots, setSlots] = useState<PlaceholderSlot[] | null>(null);
  const [values, setValues] = useState<Record<number, string>>({});
  const [dropped, setDropped] = useState<Set<number>>(new Set());
  const [working, setWorking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getPlaceholders(version.id)
      .then((found) => {
        if (!cancelled) setSlots(found);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Could not load placeholders.');
      });
    return () => {
      cancelled = true;
    };
  }, [version.id]);

  /* Dropping restores the whole item, so it settles every slot in that item. */
  const droppedTargets = new Set(
    (slots ?? []).filter((s) => dropped.has(s.index)).map((s) => s.target),
  );
  const settled = (s: PlaceholderSlot) =>
    droppedTargets.has(s.target) || HAS_DIGIT.test(values[s.index] ?? '');
  const ready = !!slots && slots.length > 0 && slots.every(settled);

  function toggleDrop(index: number) {
    setDropped((prev) => {
      const next = new Set(prev);
      if (next.has(index)) next.delete(index);
      else next.add(index);
      return next;
    });
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!slots) return;
    setWorking(true);
    setError(null);
    try {
      const fills = Object.fromEntries(
        slots
          .filter((s) => !droppedTargets.has(s.target) && (values[s.index] ?? '').trim())
          .map((s) => [s.index, values[s.index].trim()]),
      );
      onDone(await fillPlaceholders(version.id, fills, [...dropped]));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not save those figures.');
    } finally {
      setWorking(false);
    }
  }

  if (error && !slots) return <p className="error">{error}</p>;
  if (!slots) return <p className="note">Loading placeholders…</p>;

  return (
    <form className="placeholder-form" onSubmit={submit}>
      <p className="note">
        Each figure must be your real one. If you don&apos;t have it, restore the original
        wording instead — a guessed number is the kind of claim you will be asked about.
      </p>
      <ol>
        {slots.map((slot) => {
          const restored = droppedTargets.has(slot.target);
          return (
            <li className="slot" key={slot.index}>
              <p className="note">{slot.label}</p>
              <p className="slot-text" dir="auto">
                <Filled text={slot.text} />
              </p>
              <label>
                <span className="label-text">Your figure for {slot.placeholder}</span>
                <input
                  type="text"
                  maxLength={32}
                  value={values[slot.index] ?? ''}
                  disabled={restored}
                  placeholder="e.g. 40%"
                  onChange={(e) => setValues((prev) => ({ ...prev, [slot.index]: e.target.value }))}
                />
              </label>
              <label className="check">
                <input
                  type="checkbox"
                  checked={dropped.has(slot.index)}
                  onChange={() => toggleDrop(slot.index)}
                />
                <span>
                  I don&apos;t have this figure
                  <em>Restores this item&apos;s original wording.</em>
                </span>
              </label>
            </li>
          );
        })}
      </ol>
      {error && <p className="error">{error}</p>}
      <div className="actions">
        <button type="submit" disabled={!ready || working}>
          {working ? 'Saving…' : 'Save figures'}
        </button>
        <button type="button" onClick={onCancel}>
          Cancel
        </button>
      </div>
      {!ready && (
        <p className="cost-note">
          Every placeholder needs a figure with at least one digit, or to be restored.
        </p>
      )}
    </form>
  );
}

/* Every saved version of the CV: the original first, then each tailored copy,
   newest first. The original cannot be deleted from here -- it *is* the CV, and
   removing it means deleting the CV, which takes every version with it. */
export default function Versions({ resumeId }: { resumeId: string }) {
  const [versions, setVersions] = useState<CvVersion[] | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const [filling, setFilling] = useState<string | null>(null);
  const [exporting, setExporting] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    listVersions(resumeId)
      .then((rows) => {
        if (!cancelled) setVersions(rows);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Could not load versions.');
      });
    return () => {
      cancelled = true;
    };
  }, [resumeId]);

  async function remove(id: string) {
    setError(null);
    try {
      await deleteVersion(id);
      setVersions((prev) => prev?.filter((v) => v.id !== id) ?? null);
      if (open === id) setOpen(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not delete that version.');
    }
  }

  async function download(version: CvVersion, format: ExportFormat) {
    setError(null);
    setExporting(`${version.id}:${format}`);
    try {
      await downloadExport(version.id, format);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not export that version.');
    } finally {
      setExporting(null);
    }
  }

  function replaced(updated: CvVersion) {
    setVersions((prev) => prev?.map((v) => (v.id === updated.id ? updated : v)) ?? null);
    setFilling(null);
  }

  if (!versions) return error ? <p className="error">{error}</p> : null;
  if (versions.length === 0) {
    return (
      <p className="note">
        No saved versions yet. Tailor your CV for a job — from an audit or a search result — to
        create one.
      </p>
    );
  }

  const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? '' : 's'}`;

  return (
    <div className="versions">
      {error && <p className="error">{error}</p>}
      {versions.map((v) => {
        const blocked = v.placeholders > 0;
        return (
          <article className="finding" key={v.id}>
            <div className="finding-head">
              <strong>{v.name}</strong>
              <span className="via">
                {v.is_original
                  ? 'your CV as provided'
                  : `${plural(v.accepted_edit_ids.length, 'edit')} · ${new Date(v.created_at).toLocaleDateString()}`}
              </span>
            </div>

            {blocked && (
              <p className="fix">
                {plural(v.placeholders, 'placeholder')} still to fill in with your real figures.
                It can&apos;t be exported until each has a figure or is restored.
              </p>
            )}

            <div className="actions export-row">
              {(['pdf', 'docx'] as ExportFormat[]).map((format) => {
                const busy = exporting === `${v.id}:${format}`;
                return (
                  <button
                    type="button"
                    key={format}
                    disabled={blocked || exporting !== null}
                    title={blocked ? 'Fill in the placeholders first' : undefined}
                    onClick={() => download(v, format)}
                  >
                    {busy ? 'Preparing…' : format === 'pdf' ? 'Download PDF' : 'Download Word'}
                  </button>
                );
              })}
              {blocked && (
                <button
                  type="button"
                  aria-expanded={filling === v.id}
                  onClick={() => setFilling(filling === v.id ? null : v.id)}
                >
                  Fill in placeholders
                </button>
              )}
              <button
                type="button"
                aria-expanded={open === v.id}
                onClick={() => setOpen(open === v.id ? null : v.id)}
              >
                {open === v.id ? 'Hide' : 'View'}
              </button>
              {!v.is_original && (
                <button type="button" onClick={() => remove(v.id)}>
                  Delete
                </button>
              )}
            </div>

            {isArabic(v.profile) && !blocked && (
              <p className="note">
                For online applications, send the Word file. A PDF stores Arabic in a way some
                applicant tracking systems misread — joined letters can come back swapped, and
                lines mixing Arabic with numbers or English out of order. The Word file keeps
                the text exactly as written. The PDF is best for reading and printing.
              </p>
            )}

            {filling === v.id && (
              <PlaceholderForm version={v} onDone={replaced} onCancel={() => setFilling(null)} />
            )}
            {open === v.id && <Entities profile={v.profile} />}
          </article>
        );
      })}
    </div>
  );
}
