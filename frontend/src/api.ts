import { currentLang } from './i18n';
import type { AnalysisResult, Industry } from './types';

const BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

/* Every request says which language the page is in. A header of our own rather
   than Accept-Language, which the browser fills in by itself: someone who picks
   English on an Arabic browser must get English back. */
function send(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers);
  headers.set('X-UI-Lang', currentLang());
  return fetch(`${BASE}${path}`, { ...init, headers });
}

/* One request per key while it is in flight. React's development mode mounts
   components twice, and a double click is a second click; either would send the
   request again -- and for the calls wrapped in this, a second model call. The
   language is part of the key: the same CV reviewed in Arabic is a different
   answer. */
const inflight = new Map<string, Promise<unknown>>();

function shared<T>(key: string, run: () => Promise<T>): Promise<T> {
  const full = `${currentLang()}:${key}`;
  const existing = inflight.get(full);
  if (existing) return existing as Promise<T>;
  const pending = run().finally(() => inflight.delete(full));
  inflight.set(full, pending);
  return pending;
}

function failed(status: number): string {
  return currentLang() === 'ar' ? `فشل الطلب (${status})` : `Request failed (${status})`;
}

async function unwrap(res: Response) {
  if (res.ok) return res.json();
  let detail = failed(res.status);
  try {
    const body = await res.json();
    if (body?.detail) detail = typeof body.detail === 'string' ? body.detail : detail;
  } catch { /* keep the status-based message */ }
  throw new Error(detail);
}

const json = (body: unknown): RequestInit => ({
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
});

export async function listIndustries(): Promise<Industry[]> {
  return unwrap(await send('/api/industries'));
}

export async function uploadResume(file: File): Promise<{ id: string; filename: string }> {
  const body = new FormData();
  body.append('file', file);
  return unwrap(await send('/api/resumes', { method: 'POST', body }));
}

export async function createAnalysis(input: {
  resumeId: string;
  jobDescription: string;
  industry: string;
  jobTitle: string;
}): Promise<{ id: string; overall_score: number; result: AnalysisResult }> {
  const body = new FormData();
  body.append('resume_id', input.resumeId);
  body.append('job_description', input.jobDescription);
  body.append('industry', input.industry);
  body.append('job_title', input.jobTitle);
  return unwrap(await send('/api/analyses', { method: 'POST', body }));
}

export async function findJobs(input: {
  resumeId: string;
  titleHint: string;
  locations: string[];
  filters?: import('./types').ScoutFilters;
}): Promise<import('./types').FindResponse> {
  return unwrap(
    await send('/api/scout/find', json({
      resume_id: input.resumeId,
      title_hint: input.titleHint,
      locations: input.locations,
      ...(input.filters
        ? {
            work_mode: input.filters.workMode,
            seniority: input.filters.seniority,
            posted_within_days: input.filters.postedWithinDays,
            include_unstated: input.filters.includeUnstated,
          }
        : {}),
    })),
  );
}

/* One search result in full. The search itself carries no descriptions -- they
   are thousands of characters each -- so the posting is fetched when the user
   opens it. */
export async function getCachedJob(
  resumeId: string,
  jobId: string,
): Promise<import('./types').CachedJob> {
  return unwrap(await send(`/api/scout/jobs/${resumeId}/${encodeURIComponent(jobId)}`));
}

export async function scoreJobs(input: {
  resumeId: string;
  jobIds: string[];
}): Promise<import('./types').ScoreResponse> {
  return unwrap(
    await send('/api/scout/score', json({ resume_id: input.resumeId, job_ids: input.jobIds })),
  );
}

export async function uploadResumeText(
  text: string,
  filename = 'pasted-cv',
): Promise<{ id: string; filename: string }> {
  const body = new FormData();
  body.append('text', text);
  body.append('filename', filename);
  return unwrap(await send('/api/resumes/text', { method: 'POST', body }));
}

export async function getProfile(
  resumeId: string,
): Promise<import('./types').ProfileResponse> {
  return shared(`profile:${resumeId}`, async () =>
    unwrap(await send(`/api/resumes/${resumeId}/profile`)),
  );
}

export async function getFields(
  resumeId: string,
): Promise<{ resume_id: string; fields: import('./types').FieldFit[] }> {
  return shared(`fields:${resumeId}`, async () =>
    unwrap(await send(`/api/resumes/${resumeId}/fields`)),
  );
}

/* Weak areas and fixes, with no job in mind. Cached server-side per CV and language. */
export async function getReview(
  resumeId: string,
): Promise<{ resume_id: string; review: import('./types').CvReview }> {
  return shared(`review:${resumeId}`, async () =>
    unwrap(await send(`/api/resumes/${resumeId}/review`)),
  );
}

/* Deletes the CV, its file on disk, and everything derived from it. Answers
   204, so there is no body to unwrap. */
export async function deleteResume(resumeId: string): Promise<void> {
  const res = await send(`/api/resumes/${resumeId}`, { method: 'DELETE' });
  if (!res.ok && res.status !== 204) await unwrap(res);
}

export async function createTailorProposal(input: {
  resumeId: string;
  target: import('./types').TailorTarget;
}): Promise<import('./types').TailorProposal> {
  const body =
    'scoutJobId' in input.target
      ? { resume_id: input.resumeId, scout_job_id: input.target.scoutJobId }
      : { resume_id: input.resumeId, job: input.target.job };
  return shared(`tailor:${JSON.stringify(body)}`, async () =>
    unwrap(await send('/api/tailor', json(body))),
  );
}

/* Sends edit IDs only. The server applies its own stored copy of each edit. */
export async function saveVersion(
  proposalId: string,
  name: string,
  acceptedIds: string[],
): Promise<import('./types').CvVersion> {
  return unwrap(
    await send(`/api/tailor/${proposalId}/versions`, json({ name, accepted_ids: acceptedIds })),
  );
}

export async function listVersions(resumeId: string): Promise<import('./types').CvVersion[]> {
  return unwrap(await send(`/api/resumes/${resumeId}/versions`));
}

export async function deleteVersion(versionId: string): Promise<void> {
  const res = await send(`/api/versions/${versionId}`, { method: 'DELETE' });
  if (!res.ok && res.status !== 204) await unwrap(res);
}

export async function getPlaceholders(
  versionId: string,
): Promise<import('./types').PlaceholderSlot[]> {
  return unwrap(await send(`/api/versions/${versionId}/placeholders`));
}

export async function fillPlaceholders(
  versionId: string,
  values: Record<number, string>,
  drop: number[],
): Promise<import('./types').CvVersion> {
  return unwrap(await send(`/api/versions/${versionId}/placeholders`, json({ values, drop })));
}

/* RFC 5987 first, so an Arabic filename survives; the plain form is the
   ASCII fallback the server also sends. */
function filenameFrom(header: string | null): string | null {
  if (!header) return null;
  const encoded = /filename\*=UTF-8''([^;]+)/i.exec(header);
  if (encoded) {
    try {
      return decodeURIComponent(encoded[1]);
    } catch {
      /* fall through to the plain form */
    }
  }
  const plain = /filename="([^"]+)"/i.exec(header);
  return plain ? plain[1] : null;
}

/* Fetched rather than linked, so a refusal -- placeholders left, Pango
   missing -- arrives as a message the page can show instead of navigating the
   browser to a JSON error. */
export async function downloadExport(
  versionId: string,
  format: import('./types').ExportFormat,
): Promise<void> {
  const res = await send(`/api/versions/${versionId}/export.${format}`);
  if (!res.ok) await unwrap(res);
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filenameFrom(res.headers.get('Content-Disposition')) ?? `cv.${format}`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export async function fetchJob(url: string): Promise<import('./types').FetchedJob> {
  return unwrap(await send('/api/jobs/fetch', json({ url })));
}

export async function getTargeting(input: {
  resumeId: string;
  title: string;
  company: string;
  jobDescription: string;
}): Promise<import('./types').Targeting> {
  const body = {
    resume_id: input.resumeId,
    title: input.title,
    company: input.company,
    job_description: input.jobDescription,
  };
  return shared(`targeting:${JSON.stringify(body)}`, async () =>
    unwrap(await send('/api/jobs/targeting', json(body))),
  );
}
