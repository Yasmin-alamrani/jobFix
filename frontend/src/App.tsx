import { useEffect, useState } from 'react';
import Dashboard from './Dashboard';
import Landing, { Mark } from './Landing';
import Profile from './Profile';
import Scout from './Scout';
import Targeting from './Targeting';
import { TailorButton } from './Tailor';
import {
  createAnalysis,
  deleteResume,
  fetchJob,
  listIndustries,
  uploadResume,
  uploadResumeText,
} from './api';
import { useTheme } from './theme';
import type { AnalysisResult, Industry } from './types';
import './styles.css';

type Mode = 'cv' | 'audit' | 'find';

function Sun() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
      <circle cx="12" cy="12" r="4.2" />
      <path d="M12 2.5v2.2M12 19.3v2.2M4.6 4.6l1.6 1.6M17.8 17.8l1.6 1.6M2.5 12h2.2M19.3 12h2.2M4.6 19.4l1.6-1.6M17.8 6.2l1.6-1.6" />
    </svg>
  );
}

function Moon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="2" strokeLinejoin="round">
      <path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z" />
    </svg>
  );
}

export default function App() {
  const [theme, toggleTheme] = useTheme();
  const [mode, setMode] = useState<Mode>('cv');
  const [industries, setIndustries] = useState<Industry[]>([]);

  // The resume is shared: provided once on the landing page, used by every
  // stage after it. Until there is one, only the landing page is shown.
  const [resumeId, setResumeId] = useState<string | null>(null);
  const [resumeName, setResumeName] = useState('');

  const [jobTitle, setJobTitle] = useState('');
  const [industry, setIndustry] = useState('tech');
  const [jobDescription, setJobDescription] = useState('');
  const [company, setCompany] = useState('');
  const [jobUrl, setJobUrl] = useState('');
  const [reading, setReading] = useState(false);
  const [readError, setReadError] = useState<string | null>(null);
  // Bumped per audit, so the targeting panel describes the run just made.
  const [runId, setRunId] = useState(0);

  const [working, setWorking] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<AnalysisResult | null>(null);

  useEffect(() => {
    listIndustries()
      .then(setIndustries)
      .catch(() => setError('Cannot reach the API. Is the backend running on port 8000?'));
  }, []);

  function clearDerived() {
    setResumeId(null);
    setResult(null);
    setError(null);
  }

  async function onPaste(text: string) {
    if (text.trim().length < 100) {
      setError('Paste the whole CV \u2014 that is too short to read.');
      return;
    }
    clearDerived();
    try {
      setWorking('Reading your CV');
      const uploaded = await uploadResumeText(text);
      setResumeId(uploaded.id);
      setResumeName('Pasted CV');
      setMode('cv');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not read that text.');
    } finally {
      setWorking(null);
    }
  }

  /* A CV is personal data, so removing it removes the file and everything
     derived from it, not just the reference held here. */
  async function onDelete() {
    if (!resumeId) return;
    if (!window.confirm(
      'Delete this CV and everything made from it \u2014 analyses, tailored versions and ' +
      'saved figures? This cannot be undone.',
    )) return;
    try {
      setWorking('Deleting');
      await deleteResume(resumeId);
      setResumeName('');
      clearDerived();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not delete that CV.');
    } finally {
      setWorking(null);
    }
  }

  /* Back to the landing page to add another CV. The current one stays saved --
     only "Delete CV" removes it. */
  function switchCv() {
    clearDerived();
    setResumeName('');
  }

  async function onFile(chosen: File) {
    clearDerived();          // a new file invalidates the old analysis
    try {
      setWorking('Uploading your CV');
      const uploaded = await uploadResume(chosen);
      setResumeId(uploaded.id);
      setResumeName(uploaded.filename);
      setMode('cv');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Upload failed.');
    } finally {
      setWorking(null);
    }
  }

  async function runAudit(event: React.FormEvent) {
    event.preventDefault();
    if (!resumeId) return;
    setError(null);
    setResult(null);
    try {
      setWorking('Reading the document and matching against the posting');
      const analysis = await createAnalysis({
        resumeId,
        jobDescription,
        industry,
        jobTitle,
      });
      setResult(analysis.result);
      setRunId((n) => n + 1);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong.');
    } finally {
      setWorking(null);
    }
  }

  /* Fills the form from a posting URL. A failure changes nothing and says why;
     the description box below is the fallback, one step away. */
  async function readPosting(event: React.FormEvent) {
    event.preventDefault();
    if (!jobUrl.trim()) return;
    setReadError(null);
    setReading(true);
    try {
      const job = await fetchJob(jobUrl.trim());
      setJobTitle(job.title);
      setCompany(job.company);
      setJobDescription(job.description);
      setResult(null);
    } catch (err) {
      setReadError(
        err instanceof Error
          ? err.message
          : 'That page could not be read. Paste the job description into the box below instead.',
      );
    } finally {
      setReading(false);
    }
  }

  const auditReady = resumeId !== null && jobDescription.trim().length >= 50 && !working;

  return (
    <>
      <header className="topbar">
        <div className="topbar-inner">
          <span className="brand">
            <Mark /> Resume Analyzer
          </span>
          <button
            type="button"
            className="theme-toggle"
            onClick={toggleTheme}
            aria-label={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
          >
            {theme === 'dark' ? <Sun /> : <Moon />}
            <span>{theme === 'dark' ? 'Light mode' : 'Dark mode'}</span>
          </button>
        </div>
      </header>

      {!resumeId ? (
        <Landing working={working} error={error} onFile={onFile} onPaste={onPaste} />
      ) : (
        <main className="shell workspace">
          <div className="cv-strip">
            <div className="cv-name">
              <Mark />
              <span>
                <span className="label-text">Analyzing</span>
                <strong>{resumeName}</strong>
              </span>
            </div>
            <div className="cv-actions">
              <button type="button" onClick={switchCv} disabled={!!working}>
                Use a different CV
              </button>
              <button type="button" className="danger" onClick={onDelete} disabled={!!working}>
                Delete CV
              </button>
            </div>
          </div>
          {error && mode !== 'audit' && <p className="error">{error}</p>}

          <div className="modes" role="tablist">
            <button
              type="button"
              role="tab"
              aria-selected={mode === 'cv'}
              onClick={() => setMode('cv')}
            >
              Read my CV
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={mode === 'audit'}
              onClick={() => setMode('audit')}
            >
              Match against one job
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={mode === 'find'}
              onClick={() => setMode('find')}
            >
              Find matching jobs
            </button>
          </div>

          {mode === 'cv' ? (
            <Profile key={resumeId ?? 'none'} resumeId={resumeId} />
          ) : mode === 'audit' ? (
            <>
              <form className="form paste-panel" onSubmit={readPosting} style={{ marginTop: '2rem' }}>
                <label>
                  <span className="label-text">Job posting link — optional</span>
                  <input
                    type="url"
                    value={jobUrl}
                    placeholder="https://…/jobs/12345"
                    onChange={(e) => setJobUrl(e.target.value)}
                  />
                </label>
                <p className="note">
                  Reads the posting into the form below. If the page can&apos;t be read — a login
                  wall, a bot check, a site that forbids automated access — paste the description
                  instead.
                </p>
                {readError && <p className="error">{readError}</p>}
                {reading ? (
                  <div className="working">
                    <span className="sweep">
                      <i />
                    </span>
                    Reading that page…
                  </div>
                ) : (
                  <button type="submit" disabled={!jobUrl.trim()}>
                    Read this posting
                  </button>
                )}
              </form>

              <form className="form" onSubmit={runAudit} style={{ marginTop: '1.5rem' }}>
                <div className="row">
                  <label>
                    <span className="label-text">Target role</span>
                    <input
                      type="text"
                      value={jobTitle}
                      placeholder="Senior Backend Engineer"
                      onChange={(e) => setJobTitle(e.target.value)}
                    />
                  </label>
                  <label>
                    <span className="label-text">Company</span>
                    <input
                      type="text"
                      value={company}
                      placeholder="Tamara"
                      onChange={(e) => setCompany(e.target.value)}
                    />
                  </label>
                  <label>
                    <span className="label-text">Industry</span>
                    <select value={industry} onChange={(e) => setIndustry(e.target.value)}>
                      {industries.map((i) => (
                        <option key={i.key} value={i.key}>
                          {i.label}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>

                <label>
                  <span className="label-text">Job description and qualifications</span>
                  <textarea
                    value={jobDescription}
                    placeholder="Paste the full posting, including the required and preferred qualifications."
                    onChange={(e) => setJobDescription(e.target.value)}
                  />
                </label>

                {jobDescription.trim().length > 0 && jobDescription.trim().length < 50 && (
                  <p className="note">
                    Paste the full posting. A short snippet doesn&apos;t give enough to match against.
                  </p>
                )}

                {error && <p className="error">{error}</p>}

                {working ? (
                  <div className="working">
                    <span className="sweep">
                      <i />
                    </span>
                    {working}…
                  </div>
                ) : (
                  <button type="submit" disabled={!auditReady}>
                    Check the match
                  </button>
                )}
              </form>

              {result && <Dashboard result={result} />}
              {result && resumeId && (
                <Targeting
                  key={runId}
                  resumeId={resumeId}
                  title={jobTitle}
                  company={company}
                  jobDescription={jobDescription}
                />
              )}
              {result && (
                <TailorButton
                  key={`${jobTitle}|${jobDescription.length}|${result.overall_score}`}
                  resumeId={resumeId}
                  target={{
                    job: {
                      title: jobTitle,
                      company,
                      location: '',
                      description: jobDescription,
                      apply_url: jobUrl.trim(),
                      source: 'audit',
                    },
                  }}
                />
              )}
            </>
          ) : (
            <Scout resumeId={resumeId} onMatchJob={() => setMode('audit')} />
          )}
        </main>
      )}
    </>
  );
}