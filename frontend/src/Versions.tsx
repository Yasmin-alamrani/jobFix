import { useEffect, useState } from 'react';
import { deleteVersion, listVersions } from './api';
import { Entities } from './CvView';
import type { CvVersion } from './types';

/* Every saved version of the CV: the original first, then each tailored copy,
   newest first. The original cannot be deleted from here -- it *is* the CV, and
   removing it means deleting the CV, which takes every version with it. */
export default function Versions({ resumeId }: { resumeId: string }) {
  const [versions, setVersions] = useState<CvVersion[] | null>(null);
  const [open, setOpen] = useState<string | null>(null);
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

  if (error) return <p className="error">{error}</p>;
  if (!versions) return null;
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
      {versions.map((v) => (
        <article className="finding" key={v.id}>
          <div className="finding-head">
            <strong>{v.name}</strong>
            <span className="via">
              {v.is_original
                ? 'your CV as provided'
                : `${plural(v.accepted_edit_ids.length, 'edit')} · ${new Date(v.created_at).toLocaleDateString()}`}
            </span>
          </div>
          {v.placeholders > 0 && (
            <p className="fix">{plural(v.placeholders, 'placeholder')} still to fill in with your real figures.</p>
          )}
          <div className="actions">
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
          {open === v.id && <Entities profile={v.profile} />}
        </article>
      ))}
    </div>
  );
}
