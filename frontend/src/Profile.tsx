import { useEffect, useState } from 'react';
import { getFields, getProfile, getReview } from './api';
import { Entities } from './CvView';
import Review from './Review';
import type { CvReview, FieldFit, ProfileResponse } from './types';
import Versions from './Versions';

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

function Working({ label }: { label: string }) {
  return (
    <div className="working">
      <span className="sweep">
        <i />
      </span>
      {label}…
    </div>
  );
}

function message(err: unknown, fallback: string): string {
  return err instanceof Error ? err.message : fallback;
}

export default function Profile({ resumeId }: { resumeId: string | null }) {
  const [profile, setProfile] = useState<ProfileResponse | null>(null);
  const [profileError, setProfileError] = useState<string | null>(null);
  const [review, setReview] = useState<CvReview | null>(null);
  const [reviewError, setReviewError] = useState<string | null>(null);
  const [reviewAttempt, setReviewAttempt] = useState(0);
  const [fields, setFields] = useState<FieldFit[] | null>(null);
  const [fieldsError, setFieldsError] = useState<string | null>(null);

  /* The profile comes first: the review's content checks are counted from it.
     App keys this component on resumeId, so a different CV remounts it with
     fresh state rather than clearing each value by hand. */
  useEffect(() => {
    if (!resumeId) return;
    let cancelled = false;
    getProfile(resumeId)
      .then((res) => !cancelled && setProfile(res))
      .catch((err: unknown) => !cancelled && setProfileError(message(err, 'Could not read that CV.')));
    return () => {
      cancelled = true;
    };
  }, [resumeId]);

  /* Review and field matching are independent, so they run side by side, and
     one failing -- the model is busy, say -- leaves the other on screen. Both
     are cached server-side, so re-opening this tab costs nothing. */
  useEffect(() => {
    if (!resumeId || !profile) return;
    let cancelled = false;
    getReview(resumeId)
      .then((res) => !cancelled && setReview(res.review))
      .catch((err: unknown) => !cancelled && setReviewError(message(err, 'The review failed.')));
    return () => {
      cancelled = true;
    };
  }, [resumeId, profile, reviewAttempt]);

  useEffect(() => {
    if (!resumeId || !profile) return;
    let cancelled = false;
    getFields(resumeId)
      .then((res) => !cancelled && setFields(res.fields))
      .catch((err: unknown) => !cancelled && setFieldsError(message(err, 'Field matching failed.')));
    return () => {
      cancelled = true;
    };
  }, [resumeId, profile]);

  if (!resumeId) {
    return <p className="note">Upload or paste a CV to see what to improve.</p>;
  }

  const reviewing = profile && !review && !reviewError;
  const matching = profile && !fields && !fieldsError;

  return (
    <div className="profile">
      {!profile && !profileError && <Working label="Reading your CV" />}
      {profileError && <p className="error">{profileError}</p>}

      {profile && (
        <>
          <h3>CV review</h3>
          {reviewing && <Working label="Reviewing your CV for weak areas — this can take a minute" />}
          {reviewError && (
            <div>
              <p className="error">{reviewError}</p>
              <button
                type="button"
                className="retry"
                onClick={() => {
                  setReviewError(null);
                  setReviewAttempt((n) => n + 1);
                }}
              >
                Try the review again
              </button>
            </div>
          )}
          {review && <Review review={review} />}

          <h3>Fields this CV fits</h3>
          {matching && <Working label="Matching against fields" />}
          {fieldsError && <p className="error">{fieldsError}</p>}
          {fields && <Fields fields={fields} />}

          <details className="read-back">
            <summary>What we read from your CV</summary>
            <Entities profile={profile.profile} />
          </details>
        </>
      )}

      <h3>Saved versions</h3>
      <Versions resumeId={resumeId} />
    </div>
  );
}
