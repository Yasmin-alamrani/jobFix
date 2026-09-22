import { useState } from 'react';
import { findJobs, getCachedJob } from './api';
import { useText } from './i18n';
import Matching from './Matching';
import MatchBadge from './MatchBadge';
import type { FindResponse, JobIn, ScoutCandidate } from './types';

/* Finding jobs is free: the search runs over job boards and Google for Jobs,
   and the ranking against the CV is arithmetic, not a model call. So the page
   asks for nothing but a search -- no sources to tick, no shortlist to select.
   The one paid step, reading a posting against the CV in full, is a button on
   the job the user actually wants. */

const LEVELS = ['intern', 'junior', 'mid', 'senior', 'lead'] as const;

const en = {
  level: {
    intern: 'Intern',
    junior: 'Junior',
    mid: 'Mid-level',
    senior: 'Senior',
    lead: 'Lead / manager',
  } as Record<string, string>,
  mode: { remote: 'remote', hybrid: 'hybrid', onsite: 'on-site' } as Record<string, string>,
  hidden: {
    work_mode: 'with another work arrangement',
    work_mode_unstated: 'that state no work arrangement',
    seniority: 'at another level',
    seniority_unstated: 'whose title states no level',
    posted: 'posted earlier',
    posted_unstated: 'with no posting date',
  } as Record<string, string>,
  hiddenPart: (n: number, label: string) => `${n} ${label}`,
  listSep: ', ',
  filtersHid: (parts: string) => `Filters hid ${parts}.`,
  fromBoards: (n: number) => `${n} from company job boards`,
  fromGoogle: (n: number) => `${n} from Google for Jobs (LinkedIn, Bayt, Indeed and others)`,
  noDate: 'date not stated',
  today: 'today',
  yesterday: 'yesterday',
  daysAgo: (n: number) => `${n} days ago`,
  weeksAgo: (n: number) => `${n} weeks ago`,
  monthsAgo: (n: number) => `${n} months ago`,
  noLevel: 'level not stated',
  noMode: 'arrangement not stated',
  searchFailed: 'Search failed.',
  uploadFirst: 'Upload a resume above first — the search ranks jobs against it.',
  role: 'Role you want',
  rolePlaceholder: 'Leave empty to use your CV',
  locations: 'Where',
  filters: 'Filters',
  anyTime: 'Any time',
  day: 'Last 24 hours',
  week: 'Last 7 days',
  month: 'Last 30 days',
  anyMode: 'Anywhere',
  remote: 'Remote',
  hybrid: 'Hybrid',
  onsite: 'On-site',
  anyLevel: 'Any level',
  clear: 'Clear filters',
  searching: 'Searching job boards and Google for Jobs…',
  search: 'Find jobs',
  found: (shown: number, total: number) => `${shown} best matches of ${total} found`,
  ranked:
    'Each card shows how much of the posting’s wording your CV already carries — ' +
    'counted, not analysed, and free. Open one to score it properly.',
  nothing: 'No jobs matched. Try a different role, or widen the places.',
  matchIt: 'Match against my CV',
  opening: 'Opening…',
  shared: 'Shared with your CV:',
  via: (publisher: string) => `via ${publisher}`,
  openPosting: 'Open posting',
  expired: 'That result has expired. Search again.',
};

const ar: typeof en = {
  level: {
    intern: 'متدرب',
    junior: 'مبتدئ',
    mid: 'متوسط الخبرة',
    senior: 'أول',
    lead: 'قائد / مدير',
  },
  mode: { remote: 'عن بُعد', hybrid: 'هجين', onsite: 'في المقر' },
  hidden: {
    work_mode: 'بنمط عمل آخر',
    work_mode_unstated: 'لا تذكر نمط العمل',
    seniority: 'بمستوى آخر',
    seniority_unstated: 'لا يذكر مسماها المستوى',
    posted: 'منشورة قبل ذلك',
    posted_unstated: 'بلا تاريخ نشر',
  },
  hiddenPart: (n: number, label: string) => `${n} ${label}`,
  listSep: '، ',
  filtersHid: (parts: string) => `أخفت عوامل التصفية ${parts}.`,
  fromBoards: (n: number) => `${n} من لوحات وظائف الشركات`,
  fromGoogle: (n: number) => `${n} من Google للوظائف (LinkedIn وبيت.كوم وIndeed وغيرها)`,
  noDate: 'التاريخ غير مذكور',
  today: 'اليوم',
  yesterday: 'أمس',
  daysAgo: (n: number) => `قبل ${n} أيام`,
  weeksAgo: (n: number) => `قبل ${n} أسابيع`,
  monthsAgo: (n: number) => `قبل ${n} أشهر`,
  noLevel: 'المستوى غير مذكور',
  noMode: 'نمط العمل غير مذكور',
  searchFailed: 'فشل البحث.',
  uploadFirst: 'ارفع سيرتك الذاتية أولًا — فالبحث يرتّب الوظائف وفقها.',
  role: 'الدور الذي تريده',
  rolePlaceholder: 'اتركه فارغًا لاستخدام سيرتك الذاتية',
  locations: 'أين',
  filters: 'عوامل التصفية',
  anyTime: 'أي وقت',
  day: 'آخر 24 ساعة',
  week: 'آخر 7 أيام',
  month: 'آخر 30 يومًا',
  anyMode: 'أي مكان',
  remote: 'عن بُعد',
  hybrid: 'هجين',
  onsite: 'في المقر',
  anyLevel: 'أي مستوى',
  clear: 'امسح عوامل التصفية',
  searching: 'جارٍ البحث في لوحات الوظائف وGoogle للوظائف…',
  search: 'ابحث عن وظائف',
  found: (shown: number, total: number) => `أفضل ${shown} نتيجة من أصل ${total}`,
  ranked:
    'تعرض كل بطاقة نسبة ما تتضمنه سيرتك الذاتية من مفردات الإعلان — إحصاء لا تحليل، ' +
    'وبالمجان. افتح أحدها لتقييمه فعليًا.',
  nothing: 'لا توجد وظائف مطابقة. جرّب دورًا آخر أو وسّع المواقع.',
  matchIt: 'طابقها مع سيرتي الذاتية',
  opening: 'جارٍ الفتح…',
  shared: 'مشترك مع سيرتك الذاتية:',
  via: (publisher: string) => `عبر ${publisher}`,
  openPosting: 'افتح الإعلان',
  expired: 'انتهت صلاحية هذه النتيجة. ابحث مرة أخرى.',
};

const TEXT = { en, ar };
type T = typeof en;

function hiddenSummary(hidden: Record<string, number>, t: T): string {
  const parts = Object.entries(hidden)
    .filter(([, n]) => n > 0)
    .map(([reason, n]) => t.hiddenPart(n, t.hidden[reason] ?? reason));
  return parts.length ? t.filtersHid(parts.join(t.listSep)) : '';
}

/* Where the results came from. Without this, a search with nothing from Google
   looks the same as one that never asked it. */
function sourceSummary(bySource: Record<string, number>, t: T): string {
  const google = bySource.jsearch ?? 0;
  const boards = Object.entries(bySource)
    .filter(([source]) => source !== 'jsearch')
    .reduce((sum, [, n]) => sum + n, 0);
  return [boards ? t.fromBoards(boards) : '', google ? t.fromGoogle(google) : '']
    .filter(Boolean)
    .join(' · ');
}

function postedLabel(iso: string | null, t: T): string {
  if (!iso) return t.noDate;
  const days = Math.floor((Date.now() - new Date(iso).getTime()) / 86_400_000);
  if (days <= 0) return t.today;
  if (days === 1) return t.yesterday;
  if (days < 14) return t.daysAgo(days);
  if (days < 60) return t.weeksAgo(Math.round(days / 7));
  return t.monthsAgo(Math.round(days / 30));
}

/* Level is read from title words, so it is shown as read, not as fact. */
function metaLine(c: ScoutCandidate, t: T): string {
  const level = c.seniority === 'unknown' ? t.noLevel : (t.level[c.seniority] ?? c.seniority);
  const mode = c.work_mode === 'unknown' ? t.noMode : (t.mode[c.work_mode] ?? c.work_mode);
  return [level, mode, postedLabel(c.posted_at, t)].join(' · ');
}

export default function Scout({
  resumeId,
  onMatchJob,
}: {
  resumeId: string | null;
  onMatchJob: (job: JobIn) => void;
}) {
  const t = useText(TEXT);
  const [titleHint, setTitleHint] = useState('');
  const [locations, setLocations] = useState('saudi, riyadh');
  const [workMode, setWorkMode] = useState<'any' | 'remote' | 'hybrid' | 'onsite'>('any');
  const [level, setLevel] = useState('');
  const [postedWithin, setPostedWithin] = useState<number | null>(null);

  const [found, setFound] = useState<FindResponse | null>(null);
  const [searching, setSearching] = useState(false);
  const [opening, setOpening] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function search(event: React.FormEvent) {
    event.preventDefault();
    if (!resumeId) return;
    setError(null);
    setSearching(true);
    try {
      setFound(
        await findJobs({
          resumeId,
          titleHint,
          locations: locations.split(/[,،]/).map((s) => s.trim()).filter(Boolean),
          filters: {
            workMode,
            seniority: level ? [level] : [],
            postedWithinDays: postedWithin,
            includeUnstated: true,
          },
        }),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : t.searchFailed);
    } finally {
      setSearching(false);
    }
  }

  /* The posting's text lives on the server until a job is opened. Fetching it
     here means the Match tab starts with the real description rather than a
     title the user would have to paste around. */
  async function match(candidate: ScoutCandidate) {
    if (!resumeId) return;
    setError(null);
    setOpening(candidate.id);
    try {
      const job = await getCachedJob(resumeId, candidate.id);
      onMatchJob({
        title: job.title,
        company: job.company,
        location: job.location,
        description: job.description,
        apply_url: job.apply_url,
        source: job.source,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : t.expired);
    } finally {
      setOpening(null);
    }
  }

  function clearFilters() {
    setWorkMode('any');
    setLevel('');
    setPostedWithin(null);
  }

  if (!resumeId) {
    return (
      <p className="empty" style={{ marginTop: '2rem' }}>
        {t.uploadFirst}
      </p>
    );
  }

  const filtersOn = workMode !== 'any' || level !== '' || postedWithin !== null;

  return (
    <>
      <form className="form job-search" onSubmit={search} style={{ marginTop: '2rem' }}>
        <div className="search-row">
          <label>
            <span className="label-text">{t.role}</span>
            <input
              type="text"
              dir="auto"
              value={titleHint}
              placeholder={t.rolePlaceholder}
              onChange={(e) => setTitleHint(e.target.value)}
            />
          </label>
          <label>
            <span className="label-text">{t.locations}</span>
            <input
              type="text"
              dir="ltr"
              value={locations}
              placeholder="saudi, riyadh, remote"
              onChange={(e) => setLocations(e.target.value)}
            />
          </label>
          <button type="submit" disabled={searching}>
            {t.search}
          </button>
        </div>

        <div className="filter-row">
          <span className="label-text">{t.filters}</span>
          <select
            value={postedWithin ?? ''}
            onChange={(e) => setPostedWithin(e.target.value ? Number(e.target.value) : null)}
          >
            <option value="">{t.anyTime}</option>
            <option value="1">{t.day}</option>
            <option value="7">{t.week}</option>
            <option value="30">{t.month}</option>
          </select>
          <select value={workMode} onChange={(e) => setWorkMode(e.target.value as typeof workMode)}>
            <option value="any">{t.anyMode}</option>
            <option value="remote">{t.remote}</option>
            <option value="hybrid">{t.hybrid}</option>
            <option value="onsite">{t.onsite}</option>
          </select>
          <select value={level} onChange={(e) => setLevel(e.target.value)}>
            <option value="">{t.anyLevel}</option>
            {LEVELS.map((l) => (
              <option key={l} value={l}>
                {t.level[l]}
              </option>
            ))}
          </select>
          {filtersOn && (
            <button type="button" className="linklike" onClick={clearFilters}>
              {t.clear}
            </button>
          )}
        </div>

        {error && <p className="error">{error}</p>}
        {searching && <Matching label={t.searching} />}
      </form>

      {found && !searching && (
        <section>
          <div className="eyebrow">{t.found(found.candidates.length, found.total_found)}</div>
          {sourceSummary(found.by_source, t) && (
            <p className="note">{sourceSummary(found.by_source, t)}</p>
          )}
          {(found.notes ?? []).map((note) => (
            <p className="note" key={note}>
              {note}
            </p>
          ))}
          {hiddenSummary(found.hidden, t) && <p className="note">{hiddenSummary(found.hidden, t)}</p>}

          {found.candidates.length === 0 ? (
            <p className="empty">{t.nothing}</p>
          ) : (
            <>
              <p className="note" style={{ marginBottom: '1rem' }}>{t.ranked}</p>
              <div className="job-grid">
                {found.candidates.map((c) => (
                  <article className="job-card" key={c.id}>
                    <div className="job-card-head">
                      <div className="job-card-id">
                        <p className="job-company" dir="auto">
                          {c.company}
                          {c.publisher && <span className="via">{t.via(c.publisher)}</span>}
                        </p>
                        <h3 dir="auto">
                          <a href={c.apply_url} target="_blank" rel="noreferrer noopener">
                            {c.title}
                          </a>
                        </h3>
                      </div>
                      <MatchBadge coverage={c.coverage} />
                    </div>
                    <p className="q" dir="auto">{c.location}</p>
                    <p className="q">{metaLine(c, t)}</p>
                    {c.overlap.length > 0 && (
                      <p className="job-overlap" dir="auto">
                        <span className="label-text">{t.shared}</span>{' '}
                        {c.overlap.slice(0, 5).join(', ')}
                      </p>
                    )}
                    <div className="actions">
                      <button type="button" onClick={() => match(c)} disabled={opening !== null}>
                        {opening === c.id ? t.opening : t.matchIt}
                      </button>
                    </div>
                  </article>
                ))}
              </div>
            </>
          )}
        </section>
      )}
    </>
  );
}
