import { useEffect, useState } from 'react';
import { getFields, getProfile } from './api';
import { Entities } from './CvView';
import type { FieldFit, ProfileResponse } from './types';
import Versions from './Versions';

const SECTION_LABELS: Record<string, string> = {
  summary: 'Professional summary',
  experience: 'Work experience',
  education: 'Education',
  skills: 'Skills',
  certifications: 'Certifications',
  projects: 'Projects',
  languages: 'Languages',
};

/* The fit score is arithmetic, so the components are shown alongside it for the
   same reason the audit shows its ledger: a number nobody can take apart is a
   number nobody should trust. */
function Fields({ fields }: { fields: FieldFit[] }) {
  const [open, setOpen] = useState<string | null>(null);

  if (fields.length === 0) {
    return (
      <p className="note">
        No field scored high enough to suggest. That usually means the CV names
        few concrete skills — the weaknesses above are the place to start.
      </p>
    );
  }

  return (
    <div className="field-fits">
      {fields.map((fit) => (
        <article className="finding" key={fit.key}>
          <div className="finding-head">
            <span className="match-score">{fit.score.toFixed(0)}</span>
            <strong>{fit.label}</strong>
            <span className="via">
              {fit.title_alignment === 'direct'
                ? 'titles match this field'
                : fit.title_alignment === 'adjacent'
                  ? 'adjacent discipline'
                  : 'career change'}
              {fit.years_in_field !== null ? ` · ${fit.years_in_field} yrs evidenced` : ''}
            </span>
          </div>

          <p>{fit.justification}</p>

          {fit.matched_skills.length > 0 && (
            <div className="chips">
              {fit.matched_skills.map((skill) => (
                <span className="pill" key={skill}>{skill}</span>
              ))}
            </div>
          )}

          {fit.missing_skills.length > 0 && (
            <p className="fix">
              <strong>To close the gap:</strong> {fit.missing_skills.join(', ')}
            </p>
          )}

          <button
            type="button"
            className="ledger-more"
            aria-expanded={open === fit.key}
            onClick={() => setOpen(open === fit.key ? null : fit.key)}
          >
            {open === fit.key ? 'Hide' : 'Show'} how this {fit.score.toFixed(0)} was worked out
          </button>

          {open === fit.key && (
            <div className="bars">
              {fit.components.map((component) => {
                const pct = component.max_points
                  ? (100 * component.earned) / component.max_points
                  : 0;
                return (
                  <div key={component.key}>
                    <div className="bar-head">
                      <span className="name">{component.label}</span>
                      <span className="val">
                        {component.earned.toFixed(1)} / {component.max_points.toFixed(0)}
                      </span>
                    </div>
                    <div
                      className="track"
                      role="meter"
                      aria-valuenow={Math.round(pct)}
                      aria-valuemin={0}
                      aria-valuemax={100}
                      aria-label={component.label}
                    >
                      <div className="fill" style={{ width: `${pct}%` }} />
                    </div>
                    <p className="note">{component.why}</p>
                  </div>
                );
              })}
            </div>
          )}
        </article>
      ))}
    </div>
  );
}

export default function Profile({ resumeId }: { resumeId: string | null }) {
  const [profile, setProfile] = useState<ProfileResponse | null>(null);
  const [fields, setFields] = useState<FieldFit[] | null>(null);
  /* Seeded from the prop rather than reset inside the effect. App keys this
     component on resumeId, so a different CV remounts it with fresh state --
     which is both simpler than clearing four values by hand and avoids the
     extra render that a synchronous setState in an effect causes. */
  const [working, setWorking] = useState<string | null>(
    resumeId ? 'Reading the CV into sections' : null,
  );
  const [error, setError] = useState<string | null>(null);

  /* Both calls are cached server-side after the first run, so re-opening this
     tab costs nothing. They are kept separate because field matching is the
     more expensive of the two and is not always wanted. */
  useEffect(() => {
    if (!resumeId) return;
    let cancelled = false;

    getProfile(resumeId)
      .then((res) => {
        if (cancelled) return;
        setProfile(res);
        setWorking('Matching against fields');
        return getFields(resumeId);
      })
      .then((res) => {
        if (cancelled || !res) return;
        setFields(res.fields);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : 'Could not read that CV.');
      })
      .finally(() => {
        if (!cancelled) setWorking(null);
      });

    return () => {
      cancelled = true;
    };
  }, [resumeId]);

  if (!resumeId) {
    return <p className="note">Upload or paste a CV to see it broken into sections.</p>;
  }

  return (
    <div className="profile">
      {working && (
        <div className="working">
          <span className="sweep">
            <i />
          </span>
          {working}…
        </div>
      )}

      {error && <p className="error">{error}</p>}

      {profile && profile.sections_missing.length > 0 && (
        <div className="verdict">
          <strong>Missing sections.</strong> This CV has no{' '}
          {profile.sections_missing
            .map((s) => (SECTION_LABELS[s] ?? s).toLowerCase())
            .join(', ')}
          . Recruiters and parsers both look for these by name.
        </div>
      )}

      {profile && (
        <>
          <h3>What the CV says</h3>
          <Entities profile={profile.profile} />
        </>
      )}

      {fields && (
        <>
          <h3>Fields this CV fits</h3>
          <Fields fields={fields} />
        </>
      )}

      <h3>Saved versions</h3>
      <Versions resumeId={resumeId} />
    </div>
  );
}
