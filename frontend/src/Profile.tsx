import { useEffect, useState } from 'react';
import { getFields, getProfile, getReview } from './api';
import { Entities } from './CvView';
import { useText } from './i18n';
import Review from './Review';
import type { CvReview, FieldFit, ProfileResponse } from './types';
import Versions from './Versions';

const en = {
  noFields:
    'No field scored high enough to suggest. That usually means the CV names few concrete ' +
    'skills — the weaknesses above are the place to start.',
  direct: 'titles match this field',
  adjacent: 'adjacent discipline',
  distant: 'career change',
  years: (n: number) => ` · ${n} yrs evidenced`,
  closeGap: 'To close the gap:',
  showHow: (open: boolean, score: string) =>
    `${open ? 'Hide' : 'Show'} how this ${score} was worked out`,
  readingCv: 'Reading your CV',
  cantRead: 'Could not read that CV.',
  review: 'CV review',
  reviewing: 'Reviewing your CV for weak areas — this can take a minute',
  reviewFailed: 'The review failed.',
  tryAgain: 'Try the review again',
  fieldsTitle: 'Fields this CV fits',
  matchingFields: 'Matching against fields',
  fieldsFailed: 'Field matching failed.',
  readBack: 'What we read from your CV',
  savedVersions: 'Saved versions',
  uploadFirst: 'Upload or paste a CV to see what to improve.',
};

const ar: typeof en = {
  noFields:
    'لم يحصل أي مجال على درجة كافية لاقتراحه. يعني ذلك غالبًا أن السيرة الذاتية تذكر مهارات ' +
    'محددة قليلة — ونقاط الضعف أعلاه هي نقطة البداية.',
  direct: 'المسميات تطابق هذا المجال',
  adjacent: 'تخصص مجاور',
  distant: 'تغيير في المسار المهني',
  years: (n: number) => ` · ${n} سنة مُثبتة`,
  closeGap: 'لسدّ الفجوة:',
  showHow: (open: boolean, score: string) =>
    open ? `إخفاء طريقة حساب ${score}` : `اعرض كيف حُسبت ${score}`,
  readingCv: 'جارٍ قراءة سيرتك الذاتية',
  cantRead: 'تعذّرت قراءة هذه السيرة الذاتية.',
  review: 'مراجعة السيرة الذاتية',
  reviewing: 'جارٍ مراجعة سيرتك الذاتية بحثًا عن نقاط الضعف — قد يستغرق ذلك دقيقة',
  reviewFailed: 'فشلت المراجعة.',
  tryAgain: 'أعد المراجعة',
  fieldsTitle: 'المجالات التي تناسبها سيرتك الذاتية',
  matchingFields: 'جارٍ المطابقة مع المجالات',
  fieldsFailed: 'فشلت مطابقة المجالات.',
  readBack: 'ما قرأناه من سيرتك الذاتية',
  savedVersions: 'النسخ المحفوظة',
  uploadFirst: 'ارفع سيرتك الذاتية أو الصقها لترى ما يجب تحسينه.',
};

const TEXT = { en, ar };

/* The fit score is arithmetic, so the components are shown alongside it for the
   same reason the audit shows its ledger: a number nobody can take apart is a
   number nobody should trust. */
function Fields({ fields }: { fields: FieldFit[] }) {
  const t = useText(TEXT);
  const [open, setOpen] = useState<string | null>(null);

  if (fields.length === 0) {
    return <p className="note">{t.noFields}</p>;
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
                ? t.direct
                : fit.title_alignment === 'adjacent'
                  ? t.adjacent
                  : t.distant}
              {fit.years_in_field !== null ? t.years(fit.years_in_field) : ''}
            </span>
          </div>

          <p>{fit.justification}</p>

          {fit.matched_skills.length > 0 && (
            <div className="chips" dir="auto">
              {fit.matched_skills.map((skill) => (
                <span className="pill" key={skill}>{skill}</span>
              ))}
            </div>
          )}

          {fit.missing_skills.length > 0 && (
            <p className="fix">
              <strong>{t.closeGap}</strong> <span dir="auto">{fit.missing_skills.join(', ')}</span>
            </p>
          )}

          <button
            type="button"
            className="ledger-more"
            aria-expanded={open === fit.key}
            onClick={() => setOpen(open === fit.key ? null : fit.key)}
          >
            {t.showHow(open === fit.key, fit.score.toFixed(0))}
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
  const t = useText(TEXT);
  const [profile, setProfile] = useState<ProfileResponse | null>(null);
  const [profileError, setProfileError] = useState<string | null>(null);
  const [review, setReview] = useState<CvReview | null>(null);
  const [reviewError, setReviewError] = useState<string | null>(null);
  const [reviewAttempt, setReviewAttempt] = useState(0);
  const [fields, setFields] = useState<FieldFit[] | null>(null);
  const [fieldsError, setFieldsError] = useState<string | null>(null);

  /* The profile comes first: the review's content checks are counted from it.
     App keys this component on the CV and the language, so a different CV, or
     a switch of language, remounts it with fresh state rather than clearing
     each value by hand. */
  useEffect(() => {
    if (!resumeId) return;
    let cancelled = false;
    getProfile(resumeId)
      .then((res) => !cancelled && setProfile(res))
      .catch((err: unknown) => !cancelled && setProfileError(message(err, t.cantRead)));
    return () => {
      cancelled = true;
    };
  }, [resumeId, t.cantRead]);

  /* Review and field matching are independent, so they run side by side, and
     one failing -- the model is busy, say -- leaves the other on screen. Both
     are cached server-side per language, so re-opening this tab costs nothing. */
  useEffect(() => {
    if (!resumeId || !profile) return;
    let cancelled = false;
    getReview(resumeId)
      .then((res) => !cancelled && setReview(res.review))
      .catch((err: unknown) => !cancelled && setReviewError(message(err, t.reviewFailed)));
    return () => {
      cancelled = true;
    };
  }, [resumeId, profile, reviewAttempt, t.reviewFailed]);

  useEffect(() => {
    if (!resumeId || !profile) return;
    let cancelled = false;
    getFields(resumeId)
      .then((res) => !cancelled && setFields(res.fields))
      .catch((err: unknown) => !cancelled && setFieldsError(message(err, t.fieldsFailed)));
    return () => {
      cancelled = true;
    };
  }, [resumeId, profile, t.fieldsFailed]);

  if (!resumeId) {
    return <p className="note">{t.uploadFirst}</p>;
  }

  const reviewing = profile && !review && !reviewError;
  const matching = profile && !fields && !fieldsError;

  return (
    <div className="profile">
      {!profile && !profileError && <Working label={t.readingCv} />}
      {profileError && <p className="error">{profileError}</p>}

      {profile && (
        <>
          <h3>{t.review}</h3>
          {reviewing && <Working label={t.reviewing} />}
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
                {t.tryAgain}
              </button>
            </div>
          )}
          {review && <Review review={review} />}

          <h3>{t.fieldsTitle}</h3>
          {matching && <Working label={t.matchingFields} />}
          {fieldsError && <p className="error">{fieldsError}</p>}
          {fields && <Fields fields={fields} />}

          <details className="read-back">
            <summary>{t.readBack}</summary>
            <Entities profile={profile.profile} />
          </details>
        </>
      )}

      <h3>{t.savedVersions}</h3>
      <Versions resumeId={resumeId} />
    </div>
  );
}
