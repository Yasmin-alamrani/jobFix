import { useEffect, useState } from 'react';
import Dashboard from './Dashboard';
import Scout from './Scout';
import { createAnalysis, listIndustries, uploadResume } from './api';
import type { AnalysisResult, Industry } from './types';
import './styles.css';

type Mode = 'audit' | 'find';

export default function App() {
  const [mode, setMode] = useState<Mode>('audit');
  const [industries, setIndustries] = useState<Industry[]>([]);

  // The resume is shared: uploaded once, used by both agents.
  const [file, setFile] = useState<File | null>(null);
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

  async function onFile(chosen: File | null) {
    setFile(chosen);
    setResumeId(null);      // a new file invalidates the old analysis
    setResult(null);
    setError(null);
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

      <label style={{ marginTop: '1.75rem' }}>
        <span className="label-text">Resume — PDF or DOCX</span>
        <input
          type="file"
          accept=".pdf,.docx,application/pdf"
          onChange={(e) => onFile(e.target.files?.[0] ?? null)}
        />
      </label>
      {resumeId && (
        <p className="note" style={{ marginTop: '0.625rem' }}>
          Using <strong>{resumeName}</strong> for both the audit and the search.
        </p>
      )}

      <div className="modes" role="tablist">
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

      {mode === 'audit' ? (
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
        </>
      ) : (
        <Scout resumeId={resumeId} />
      )}
    </div>
  );
}
