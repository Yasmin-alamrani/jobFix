import { useEffect, useState } from 'react';
import Dashboard from './Dashboard';
import Profile from './Profile';
import Scout from './Scout';
import { TailorButton } from './Tailor';
import {
  createAnalysis,
  deleteResume,
  listIndustries,
  uploadResume,
  uploadResumeText,
} from './api';
import type { AnalysisResult, Industry } from './types';
import './styles.css';

type Mode = 'cv' | 'audit' | 'find';
type Source = 'file' | 'paste';

export default function App() {
  const [mode, setMode] = useState<Mode>('cv');
  const [industries, setIndustries] = useState<Industry[]>([]);

  // The resume is shared: provided once, used by every stage after it.
  const [source, setSource] = useState<Source>('file');
  const [file, setFile] = useState<File | null>(null);
  const [cvText, setCvText] = useState('');
  const [resumeId, setResumeId] = useState<string | null>(null);
  const [resumeName, setResumeName] = useState('');

  const [jobTitle, setJobTitle] = useState('');
  const [industry, setIndustry] = useState('tech');
  const [jobDescription, setJobDescription] = useState('');

  const [working, setWorking] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<AnalysisResult | null>(null);

  useEffect(() => {
    listIndustries()
      .then(setIndustries)
      .catch(() => setError('Cannot reach the API. Is the backend running on port 8000?'));
  }, []);

  async function ensureUploaded(): Promise<string> {
    if (resumeId) return resumeId;
    if (!file) throw new Error('Choose a resume file first.');
    setWorking('Uploading resume');
    const uploaded = await uploadResume(file);
    setResumeId(uploaded.id);
    setResumeName(uploaded.filename);
    return uploaded.id;
  }

  function clearDerived() {
    setResumeId(null);
    setResult(null);
    setError(null);
  }

  async function onPaste() {
    if (cvText.trim().length < 100) {
      setError('Paste the whole CV \u2014 that is too short to read.');
      return;
    }
    clearDerived();
    try {
      setWorking('Reading the pasted CV');
      const uploaded = await uploadResumeText(cvText);
      setResumeId(uploaded.id);
      setResumeName('pasted CV');
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
    try {
      setWorking('Deleting');
      await deleteResume(resumeId);
      setFile(null);
      setCvText('');
      setResumeName('');
      clearDerived();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not delete that CV.');
    } finally {
      setWorking(null);
    }
  }

  async function onFile(chosen: File | null) {
    setFile(chosen);
    clearDerived();          // a new file invalidates the old analysis
    if (!chosen) return;
    try {
      setWorking('Uploading resume');
      const uploaded = await uploadResume(chosen);
      setResumeId(uploaded.id);
      setResumeName(uploaded.filename);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Upload failed.');
    } finally {
      setWorking(null);
    }
  }

  async function runAudit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setResult(null);
    try {
      const id = await ensureUploaded();
      setWorking('Reading the document and matching against the posting');
      const analysis = await createAnalysis({
        resumeId: id,
        jobDescription,
        industry,
        jobTitle,
      });
      setResult(analysis.result);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong.');
    } finally {
      setWorking(null);
    }
  }

  const auditReady = resumeId !== null && jobDescription.trim().length >= 50 && !working;

  return (
    <div className="shell">
      <header className="masthead">
        <h1>Resume audit</h1>
        <p>
          Score your CV against one posting and see exactly which points it lost — or search
          job boards and rank what's out there against it.
        </p>
      </header>

      <div className="modes" role="tablist" style={{ marginTop: '1.75rem' }}>
        <button
          type="button"
          role="tab"
          aria-selected={source === 'file'}
          onClick={() => setSource('file')}
        >
          Upload a file
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={source === 'paste'}
          onClick={() => setSource('paste')}
        >
          Paste the text
        </button>
      </div>

      {source === 'file' ? (
        <label style={{ marginTop: '1rem' }}>
          <span className="label-text">Resume — PDF or DOCX</span>
          <input
            type="file"
            accept=".pdf,.docx,application/pdf"
            onChange={(e) => onFile(e.target.files?.[0] ?? null)}
          />
        </label>
      ) : (
        <div className="paste-panel" style={{ marginTop: '1rem' }}>
          <label>
            <span className="label-text">Paste your CV</span>
            <textarea
              value={cvText}
              placeholder="Paste the whole CV, including dates and bullet points."
              onChange={(e) => setCvText(e.target.value)}
            />
          </label>
          <button type="button" onClick={onPaste} disabled={!!working}>
            Use this text
          </button>
        </div>
      )}

      {resumeId && (
        <p className="note" style={{ marginTop: '0.625rem' }}>
          Using <strong>{resumeName}</strong> for every stage below.{' '}
          <button type="button" className="ledger-more" onClick={onDelete}>
            Delete it and everything derived from it
          </button>
        </p>
      )}

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
          Audit against one job
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
          <form className="form" onSubmit={runAudit} style={{ marginTop: '2rem' }}>
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
                Run the audit
              </button>
            )}
          </form>

          {result && <Dashboard result={result} />}
          {result && (
            <TailorButton
              key={`${jobTitle}|${jobDescription.length}|${result.overall_score}`}
              resumeId={resumeId}
              target={{
                job: {
                  title: jobTitle,
                  company: '',
                  location: '',
                  description: jobDescription,
                  apply_url: '',
                  source: 'audit',
                },
              }}
            />
          )}
        </>
      ) : (
        <Scout resumeId={resumeId} />
      )}
    </div>
  );
}
