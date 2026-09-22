import { useRef, useState } from 'react';
import { useText } from './i18n';

// The server's limits, checked here too so a wrong file fails instantly
// instead of after a 15 MB upload.
const ACCEPT =
  '.pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document';
const MAX_BYTES = 15 * 1024 * 1024;
const MIN_PASTE = 100;

const en = {
  badType: 'Upload a PDF or a Word (.docx) file.',
  tooBig: 'That file is over 15 MB. Export a smaller PDF and try again.',
  kicker: 'jobFix',
  heading: 'Will your CV get past the first screen?',
  lede:
    'Upload your CV to see how an applicant tracking system reads it, how well it fits the ' +
    'jobs you want, and exactly what to change — without inventing a single line.',
  pasteLabel: 'Paste your CV',
  pastePlaceholder: 'Paste the whole CV, including dates and bullet points.',
  analyzeText: 'Analyze this text',
  uploadInstead: 'Upload a file instead',
  tooShort: 'That is too short to be a whole CV.',
  dropLead: 'Drop your CV here or choose a file.',
  dropHint: 'PDF or Word (.docx), up to 15 MB.',
  upload: 'Upload your CV',
  pasteInstead: 'or paste the text instead',
  privacy:
    'Your CV is stored on this computer and sent to the AI model only when you run an ' +
    'analysis. You can delete it, and everything made from it, at any time.',
  unlocksTitle: 'What opens up once your CV is in',
  unlocks: [
    {
      title: 'Read your CV',
      text: 'Your weak areas and how to fix each one, what is missing, and the fields you fit best — each score broken down so you can check it.',
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
  ],
};

const ar: typeof en = {
  badType: 'ارفع ملف PDF أو Word ‏(.docx).',
  tooBig: 'حجم هذا الملف يتجاوز 15 ميغابايت. صدّر ملف PDF أصغر وحاول مجددًا.',
  kicker: 'jobFix',
  heading: 'هل تجتاز سيرتك الذاتية الفرز الأول؟',
  lede:
    'ارفع سيرتك الذاتية لترى كيف يقرؤها نظام تتبّع المتقدمين، ومدى ملاءمتها للوظائف التي ' +
    'تريدها، وما الذي يجب تغييره بالضبط — دون اختلاق سطر واحد.',
  pasteLabel: 'الصق سيرتك الذاتية',
  pastePlaceholder: 'الصق السيرة الذاتية كاملة، بما فيها التواريخ والنقاط.',
  analyzeText: 'حلّل هذا النص',
  uploadInstead: 'ارفع ملفًا بدلًا من ذلك',
  tooShort: 'هذا أقصر من أن يكون سيرة ذاتية كاملة.',
  dropLead: 'أفلت سيرتك الذاتية هنا أو اختر ملفًا.',
  dropHint: 'PDF أو Word ‏(.docx)، حتى 15 ميغابايت.',
  upload: 'ارفع سيرتك الذاتية',
  pasteInstead: 'أو الصق النص بدلًا من ذلك',
  privacy:
    'تُحفظ سيرتك الذاتية على هذا الجهاز ولا تُرسل إلى نموذج الذكاء الاصطناعي إلا عند تشغيل ' +
    'التحليل. يمكنك حذفها، وكل ما نتج عنها، في أي وقت.',
  unlocksTitle: 'ما يتاح لك بعد رفع سيرتك الذاتية',
  unlocks: [
    {
      title: 'اقرأ سيرتك الذاتية',
      text: 'نقاط الضعف وكيفية إصلاح كل منها، وما ينقصها، والمجالات الأنسب لك — مع تفصيل كل درجة لتتحقق منها.',
    },
    {
      title: 'طابقها مع وظيفة',
      text: 'الصق إعلانًا أو رابطه. شاهد كل متطلب: مستوفى أو مستوفى جزئيًا أو مفقود، مع السطر من سيرتك الذاتية الذي يثبته.',
    },
    {
      title: 'ابحث عن وظائف مناسبة',
      text: 'ابحث في لوحات وظائف الشركات وGoogle للوظائف، وصفِّ النتائج حسب المستوى ونمط العمل والتاريخ، ورتّبها وفق سيرتك الذاتية.',
    },
    {
      title: 'خصّص وصدّر',
      text: 'اقبل كل تعديل مقترح أو ارفضه — ولا يمكن لأي منها أن يضيف شيئًا لا تقوله سيرتك الذاتية — ثم نزّل ملف PDF أو Word نظيفًا.',
    },
  ],
};

const TEXT = { en, ar };

function problemWith(file: File, t: typeof en): string | null {
  const name = file.name.toLowerCase();
  if (!name.endsWith('.pdf') && !name.endsWith('.docx')) return t.badType;
  if (file.size > MAX_BYTES) return t.tooBig;
  return null;
}

/* The jobFix mark: an eight-pointed Maltese star, traced from the icon.
   Four arms on the axes, each flaring to two points 26.5 degrees off its
   axis, with a notch cut back to 7.4 of the 15-unit radius between them and
   the arms meeting only at the centre.

   Each arm is two triangles rather than one shape, so the fold down its
   middle catches the light the way the original does. The shading is two
   opacities of one colour rather than two colours: `--accent` is already
   light-on-dark and dark-on-light, so the mark keeps its contrast in both
   themes, which a fixed navy would not. */
export function Mark() {
  return (
    <svg viewBox="0 0 32 32" aria-hidden="true">
      <g fill="var(--accent)">
        <path d="M16 16 L29.42 9.31 L23.38 16 Z" />
        <path d="M16 16 L22.69 29.42 L16 23.38 Z" />
        <path d="M16 16 L2.58 22.69 L8.62 16 Z" />
        <path d="M16 16 L9.31 2.58 L16 8.62 Z" />
      </g>
      <g fill="var(--accent)" opacity="0.62">
        <path d="M16 16 L23.38 16 L29.42 22.69 Z" />
        <path d="M16 16 L16 23.38 L9.31 29.42 Z" />
        <path d="M16 16 L8.62 16 L2.58 9.31 Z" />
        <path d="M16 16 L16 8.62 L22.69 2.58 Z" />
      </g>
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
  const t = useText(TEXT);
  const input = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [pasting, setPasting] = useState(false);
  const [text, setText] = useState('');
  const [problem, setProblem] = useState<string | null>(null);

  function choose(file: File | undefined) {
    if (!file) return;
    const issue = problemWith(file, t);
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
            <p className="kicker">{t.kicker}</p>
            <h1>{t.heading}</h1>
            <p className="lede">{t.lede}</p>

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
                    <span className="label-text">{t.pasteLabel}</span>
                    <textarea
                      dir="auto"
                      value={text}
                      placeholder={t.pastePlaceholder}
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
                      {t.analyzeText}
                    </button>
                    <button type="button" className="linklike" onClick={() => setPasting(false)}>
                      {t.uploadInstead}
                    </button>
                  </div>
                  {text.trim().length > 0 && text.trim().length < MIN_PASTE && (
                    <p className="dropzone-hint">{t.tooShort}</p>
                  )}
                </>
              ) : (
                <>
                  <p className="dropzone-lead">
                    {t.dropLead}
                    <small>{t.dropHint}</small>
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
                    {t.upload}
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
                    {t.pasteInstead}
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
                <span>{t.privacy}</span>
              </p>
            </div>
          </div>
        </section>

        <section className="unlocks">
          <div className="eyebrow">{t.unlocksTitle}</div>
          <div className="unlock-grid">
            {t.unlocks.map((u, i) => (
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
