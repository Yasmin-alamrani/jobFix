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
import { useLang, useSetLang, useText } from './i18n';
import { useTheme } from './theme';
import type { AnalysisResult, Industry } from './types';
import './styles.css';

type Mode = 'cv' | 'audit' | 'find';

const en = {
  title: 'Resume Analyzer',
  apiDown: 'Cannot reach the API. Is the backend running on port 8000?',
  pasteShort: 'Paste the whole CV — that is too short to read.',
  readingCv: 'Reading your CV',
  pastedCv: 'Pasted CV',
  readTextFailed: 'Could not read that text.',
  confirmDelete:
    'Delete this CV and everything made from it — analyses, tailored versions and ' +
    'saved figures? This cannot be undone.',
  deleting: 'Deleting',
  deleteFailed: 'Could not delete that CV.',
  uploading: 'Uploading your CV',
  uploadFailed: 'Upload failed.',
  matching: 'Reading the document and matching against the posting',
  failed: 'Something went wrong.',
  pageUnreadable:
    'That page could not be read. Paste the job description into the box below instead.',
  toLight: 'Switch to light mode',
  toDark: 'Switch to dark mode',
  light: 'Light mode',
  dark: 'Dark mode',
  otherLang: 'العربية',
  otherLangCode: 'ar',
  otherLangLabel: 'اعرض الصفحة بالعربية',
  analyzing: 'Analyzing',
  differentCv: 'Use a different CV',
  deleteCv: 'Delete CV',
  tabCv: 'Read my CV',
  tabAudit: 'Match against one job',
  tabFind: 'Find jobs',
  postingLink: 'Job posting link — optional',
  postingNote:
    'Reads the posting into the form below. Any job link: if the page itself cannot be read — a ' +
    'login wall, a bot check, a site that forbids automated reading — the posting is looked up ' +
    'on Google for Jobs instead. Failing that, paste the description.',
  readingPage: 'Reading that page…',
  readPosting: 'Read this posting',
  targetRole: 'Target role',
  rolePlaceholder: 'Senior Backend Engineer',
  company: 'Company',
  companyPlaceholder: 'Tamara',
  industry: 'Industry',
  jd: 'Job description and qualifications',
  jdPlaceholder: 'Paste the full posting, including the required and preferred qualifications.',
  jdShort: 'Paste the full posting. A short snippet doesn’t give enough to match against.',
  check: 'Check the match',
};

const ar: typeof en = {
  title: 'محلل السيرة الذاتية',
  apiDown: 'تعذّر الوصول إلى الخادم. هل الواجهة الخلفية تعمل على المنفذ 8000؟',
  pasteShort: 'الصق السيرة الذاتية كاملة — هذا النص أقصر من أن يُقرأ.',
  readingCv: 'جارٍ قراءة سيرتك الذاتية',
  pastedCv: 'سيرة ذاتية ملصوقة',
  readTextFailed: 'تعذّرت قراءة هذا النص.',
  confirmDelete:
    'هل تريد حذف هذه السيرة الذاتية وكل ما نتج عنها — التحليلات والنسخ المخصّصة والأرقام ' +
    'المحفوظة؟ لا يمكن التراجع عن ذلك.',
  deleting: 'جارٍ الحذف',
  deleteFailed: 'تعذّر حذف هذه السيرة الذاتية.',
  uploading: 'جارٍ رفع سيرتك الذاتية',
  uploadFailed: 'فشل الرفع.',
  matching: 'جارٍ قراءة المستند ومطابقته مع الإعلان',
  failed: 'حدث خطأ ما.',
  pageUnreadable: 'تعذّرت قراءة هذه الصفحة. الصق الوصف الوظيفي في المربع أدناه بدلًا من ذلك.',
  toLight: 'التبديل إلى الوضع الفاتح',
  toDark: 'التبديل إلى الوضع الداكن',
  light: 'الوضع الفاتح',
  dark: 'الوضع الداكن',
  otherLang: 'English',
  otherLangCode: 'en',
  otherLangLabel: 'Show the page in English',
  analyzing: 'قيد التحليل',
  differentCv: 'استخدم سيرة ذاتية أخرى',
  deleteCv: 'حذف السيرة الذاتية',
  tabCv: 'اقرأ سيرتي الذاتية',
  tabAudit: 'طابقها مع وظيفة',
  tabFind: 'ابحث عن وظائف',
  postingLink: 'رابط الإعلان الوظيفي — اختياري',
  postingNote:
    'يقرأ الإعلان ويملأ النموذج أدناه. أي رابط وظيفة: إذا تعذّرت قراءة الصفحة نفسها — جدار تسجيل ' +
    'دخول أو فحص للروبوتات أو موقع يمنع القراءة الآلية — يُبحث عن الإعلان في Google للوظائف. ' +
    'وإن لم يُعثر عليه، فالصق الوصف.',
  readingPage: 'جارٍ قراءة الصفحة…',
  readPosting: 'اقرأ هذا الإعلان',
  targetRole: 'الدور المستهدف',
  rolePlaceholder: 'مهندس برمجيات أول',
  company: 'الشركة',
  companyPlaceholder: 'تمارا',
  industry: 'القطاع',
  jd: 'الوصف الوظيفي والمؤهلات',
  jdPlaceholder: 'الصق الإعلان كاملًا، بما في ذلك المؤهلات المطلوبة والمفضّلة.',
  jdShort: 'الصق الإعلان كاملًا. المقتطف القصير لا يكفي للمطابقة.',
  check: 'تحقّق من التطابق',
};

const TEXT = { en, ar };

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
  const t = useText(TEXT);
  const lang = useLang();
  const setLang = useSetLang();
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
    document.title = t.title;
  }, [t.title]);

  // Refetched per language: the industry names come back translated.
  useEffect(() => {
    listIndustries()
      .then(setIndustries)
      .catch(() => setError(TEXT[lang].apiDown));
  }, [lang]);

  function clearDerived() {
    setResumeId(null);
    setResult(null);
    setError(null);
  }

  async function onPaste(text: string) {
    if (text.trim().length < 100) {
      setError(t.pasteShort);
      return;
    }
    clearDerived();
    try {
      setWorking(t.readingCv);
      const uploaded = await uploadResumeText(text);
      setResumeId(uploaded.id);
      setResumeName(t.pastedCv);
      setMode('cv');
    } catch (err) {
      setError(err instanceof Error ? err.message : t.readTextFailed);
    } finally {
      setWorking(null);
    }
  }

  /* A CV is personal data, so removing it removes the file and everything
     derived from it, not just the reference held here. */
  async function onDelete() {
    if (!resumeId) return;
    if (!window.confirm(t.confirmDelete)) return;
    try {
      setWorking(t.deleting);
      await deleteResume(resumeId);
      setResumeName('');
      clearDerived();
    } catch (err) {
      setError(err instanceof Error ? err.message : t.deleteFailed);
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
      setWorking(t.uploading);
      const uploaded = await uploadResume(chosen);
      setResumeId(uploaded.id);
      setResumeName(uploaded.filename);
      setMode('cv');
    } catch (err) {
      setError(err instanceof Error ? err.message : t.uploadFailed);
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
      setWorking(t.matching);
      const analysis = await createAnalysis({
        resumeId,
        jobDescription,
        industry,
        jobTitle,
      });
      setResult(analysis.result);
      setRunId((n) => n + 1);
    } catch (err) {
      setError(err instanceof Error ? err.message : t.failed);
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
      setReadError(err instanceof Error ? err.message : t.pageUnreadable);
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
            <Mark /> {t.title}
          </span>
          <div className="topbar-actions">
            <button
              type="button"
              className="theme-toggle"
              lang={t.otherLangCode}
              onClick={() => setLang(lang === 'ar' ? 'en' : 'ar')}
              aria-label={t.otherLangLabel}
            >
              <span>{t.otherLang}</span>
            </button>
            <button
              type="button"
              className="theme-toggle"
              onClick={toggleTheme}
              aria-label={theme === 'dark' ? t.toLight : t.toDark}
            >
              {theme === 'dark' ? <Sun /> : <Moon />}
              <span>{theme === 'dark' ? t.light : t.dark}</span>
            </button>
          </div>
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
                <span className="label-text">{t.analyzing}</span>
                <strong dir="auto">{resumeName}</strong>
              </span>
            </div>
            <div className="cv-actions">
              <button type="button" onClick={switchCv} disabled={!!working}>
                {t.differentCv}
              </button>
              <button type="button" className="danger" onClick={onDelete} disabled={!!working}>
                {t.deleteCv}
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
              {t.tabCv}
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={mode === 'audit'}
              onClick={() => setMode('audit')}
            >
              {t.tabAudit}
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={mode === 'find'}
              onClick={() => setMode('find')}
            >
              {t.tabFind}
            </button>
          </div>

          {mode === 'cv' ? (
            /* Keyed on the language too: switching remounts the tab, which
               fetches the review and fields again in the new language. */
            <Profile key={`${resumeId ?? 'none'}:${lang}`} resumeId={resumeId} />
          ) : mode === 'audit' ? (
            <>
              <form className="form paste-panel" onSubmit={readPosting} style={{ marginTop: '2rem' }}>
                <label>
                  <span className="label-text">{t.postingLink}</span>
                  <input
                    type="url"
                    value={jobUrl}
                    placeholder="https://…/jobs/12345"
                    onChange={(e) => setJobUrl(e.target.value)}
                  />
                </label>
                <p className="note">{t.postingNote}</p>
                {readError && <p className="error">{readError}</p>}
                {reading ? (
                  <div className="working">
                    <span className="sweep">
                      <i />
                    </span>
                    {t.readingPage}
                  </div>
                ) : (
                  <button type="submit" disabled={!jobUrl.trim()}>
                    {t.readPosting}
                  </button>
                )}
              </form>

              <form className="form" onSubmit={runAudit} style={{ marginTop: '1.5rem' }}>
                <div className="row">
                  <label>
                    <span className="label-text">{t.targetRole}</span>
                    <input
                      type="text"
                      dir="auto"
                      value={jobTitle}
                      placeholder={t.rolePlaceholder}
                      onChange={(e) => setJobTitle(e.target.value)}
                    />
                  </label>
                  <label>
                    <span className="label-text">{t.company}</span>
                    <input
                      type="text"
                      dir="auto"
                      value={company}
                      placeholder={t.companyPlaceholder}
                      onChange={(e) => setCompany(e.target.value)}
                    />
                  </label>
                  <label>
                    <span className="label-text">{t.industry}</span>
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
                  <span className="label-text">{t.jd}</span>
                  <textarea
                    dir="auto"
                    value={jobDescription}
                    placeholder={t.jdPlaceholder}
                    onChange={(e) => setJobDescription(e.target.value)}
                  />
                </label>

                {jobDescription.trim().length > 0 && jobDescription.trim().length < 50 && (
                  <p className="note">{t.jdShort}</p>
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
                    {t.check}
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
            <Scout
              resumeId={resumeId}
              onMatchJob={(job) => {
                /* A search result opens in the Match tab with the posting
                   already in it: the same analysis, nothing to copy across. */
                setJobTitle(job.title);
                setCompany(job.company);
                setJobDescription(job.description);
                setJobUrl(job.apply_url ?? '');
                setResult(null);
                setError(null);
                setMode('audit');
              }}
            />
          )}
        </main>
      )}
    </>
  );
}
