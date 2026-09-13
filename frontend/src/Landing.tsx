import { useRef, useState } from 'react';

// The server's limits, checked here too so a wrong file fails instantly
// instead of after a 15 MB upload.
const ACCEPT =
  '.pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document';
const MAX_BYTES = 15 * 1024 * 1024;
const MIN_PASTE = 100;

function problemWith(file: File): string | null {
  const name = file.name.toLowerCase();
  if (!name.endsWith('.pdf') && !name.endsWith('.docx')) {
    return 'Upload a PDF or a Word (.docx) file.';
  }
  if (file.size > MAX_BYTES) return 'That file is over 15 MB. Export a smaller PDF and try again.';
  return null;
}

export function Mark() {
  return (
    <svg viewBox="0 0 32 32" aria-hidden="true">
      <rect x="3" y="2" width="22" height="27" rx="6" fill="var(--accent)" />
      <path d="M9 10h10M9 15h7M9 20h5" stroke="var(--card)" strokeWidth="2.2" strokeLinecap="round" />
      <circle cx="23.5" cy="23.5" r="6.5" fill="var(--go)" stroke="var(--card)" strokeWidth="2" />
      <path
        d="M20.8 23.6l1.9 1.9 3.4-3.6"
        stroke="var(--go-ink)"
        strokeWidth="1.9"
        fill="none"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function Lock() {
  return (
    <svg viewBox="0 0 16 16" aria-hidden="true">
      <rect x="3" y="7" width="10" height="7.5" rx="1.6" fill="currentColor" />
      <path d="M5 7V5a3 3 0 0 1 6 0v2" stroke="currentColor" strokeWidth="1.6" fill="none" />
    </svg>
  );
}

const UNLOCKS = [
  {
    title: 'Read your CV',
    text: 'Every section pulled out, what is missing flagged, and the fields you fit best — each score broken down so you can check it.',
  },
  {
    title: 'Match against a job',
    text: 'Paste a posting or its link. See each requirement met, partly met or missing, with the line from your CV that proves it.',
  },
  {
    title: 'Find matching jobs',
    text: 'Search company job boards and Google for Jobs, filter by level, work arrangement and date, and rank what you find against your CV.',
  },
  {
    title: 'Tailor and export',
    text: 'Accept or reject each suggested edit — none of them can add anything your CV does not say — then download a clean PDF or Word file.',
  },
];

export default function Landing({
  working,
  error,
  onFile,
  onPaste,
}: {
  working: string | null;
  error: string | null;
  onFile: (file: File) => void;
  onPaste: (text: string) => void;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [pasting, setPasting] = useState(false);
  const [text, setText] = useState('');
  const [problem, setProblem] = useState<string | null>(null);

  function choose(file: File | undefined) {
    if (!file) return;
    const issue = problemWith(file);
    setProblem(issue);
    if (!issue) onFile(file);
  }

  const busy = working !== null;
  const shown = problem ?? error;

  return (
    <main className="landing">
      <div className="landing-inner">
        <section className="hero">
          <div className="hero-copy">
            <p className="kicker">Resume Analyzer</p>
            <h1>Will your CV get past the first screen?</h1>
            <p className="lede">
              Upload your CV to see how an applicant tracking system reads it, how well it fits
              the jobs you want, and exactly what to change — without inventing a single line.
            </p>

            <div
              className={`dropzone${dragging ? ' over' : ''}`}
              onDragOver={(e) => {
                e.preventDefault();
                if (!busy && !pasting) setDragging(true);
              }}
              onDragLeave={(e) => {
                if (!e.currentTarget.contains(e.relatedTarget as Node)) setDragging(false);
              }}
              onDrop={(e) => {
                e.preventDefault();
                setDragging(false);
                if (!busy && !pasting) choose(e.dataTransfer.files[0]);
              }}
            >
              {pasting ? (
                <>
                  <label>
                    <span className="label-text">Paste your CV</span>
                    <textarea
                      value={text}
                      placeholder="Paste the whole CV, including dates and bullet points."
                      onChange={(e) => setText(e.target.value)}
                      autoFocus
                    />
                  </label>
                  <div className="paste-actions">
                    <button
                      type="button"
                      className="upload"
                      disabled={busy || text.trim().length < MIN_PASTE}
                      onClick={() => onPaste(text)}
                    >
                      Analyze this text
                    </button>
                    <button type="button" className="linklike" onClick={() => setPasting(false)}>
                      Upload a file instead
                    </button>
                  </div>
                  {text.trim().length > 0 && text.trim().length < MIN_PASTE && (
                    <p className="dropzone-hint">That is too short to be a whole CV.</p>
                  )}
                </>
              ) : (
                <>
                  <p className="dropzone-lead">
                    Drop your CV here or choose a file.
                    <small>PDF or Word (.docx), up to 15 MB.</small>
                  </p>
                  <input
                    ref={input}
                    type="file"
                    accept={ACCEPT}
                    className="visually-hidden"
                    tabIndex={-1}
                    onChange={(e) => {
                      choose(e.target.files?.[0]);
                      e.target.value = ''; // choosing the same file again still fires
                    }}
                  />
                  <button
                    type="button"
                    className="upload"
                    disabled={busy}
                    onClick={() => input.current?.click()}
                  >
                    Upload your CV
                  </button>
                  <button
                    type="button"
                    className="linklike"
                    disabled={busy}
                    onClick={() => {
                      setProblem(null);
                      setPasting(true);
                    }}
                  >
                    or paste the text instead
                  </button>
                </>
              )}

              {working && (
                <div className="working">
                  <span className="sweep">
                    <i />
                  </span>
                  {working}…
                </div>
              )}
              {shown && <p className="error">{shown}</p>}

              <p className="privacy">
                <Lock />
                <span>
                  Your CV is stored on this computer and sent to the AI model only when you run an
                  analysis. You can delete it, and everything made from it, at any time.
                </span>
              </p>
            </div>
          </div>
        </section>

        <section className="unlocks">
          <div className="eyebrow">What opens up once your CV is in</div>
          <div className="unlock-grid">
            {UNLOCKS.map((u, i) => (
              <article className="unlock" key={u.title}>
                <span className="step">0{i + 1}</span>
                <h3>{u.title}</h3>
                <p>{u.text}</p>
              </article>
            ))}
          </div>
        </section>
      </div>
    </main>
  );
}
