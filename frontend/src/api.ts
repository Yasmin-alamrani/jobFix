import type { AnalysisResult, Industry } from './types';

const BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

/* One request per key while it is in flight. React's development mode mounts
   components twice, and a double click is a second click; either would send the
   request again -- and for the calls wrapped in this, a second model call. */
const inflight = new Map<string, Promise<unknown>>();

function shared<T>(key: string, run: () => Promise<T>): Promise<T> {
  const existing = inflight.get(key);
  if (existing) return existing as Promise<T>;
  const pending = run().finally(() => inflight.delete(key));
  inflight.set(key, pending);
  return pending;
}

async function unwrap(res: Response) {
  if (res.ok) return res.json();
  let detail = `Request failed (${res.status})`;
  try {
    const body = await res.json();
    if (body?.detail) detail = typeof body.detail === 'string' ? body.detail : detail;
  } catch { /* keep the status-based message */ }
  throw new Error(detail);
}

export async function listIndustries(): Promise<Industry[]> {
  return unwrap(await fetch(`${BASE}/api/industries`));
}

export async function uploadResume(file: File): Promise<{ id: string; filename: string }> {
  const body = new FormData();
  body.append('file', file);
  return unwrap(await fetch(`${BASE}/api/resumes`, { method: 'POST', body }));
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
  return unwrap(await fetch(`${BASE}/api/analyses`, { method: 'POST', body }));
}

export async function findJobs(input: {
  resumeId: string;
  titleHint: string;
  locations: string[];
  includeJsearch: boolean;
  linkedinOnly: boolean;
}): Promise<import('./types').FindResponse> {
  return unwrap(
    await fetch(`${BASE}/api/scout/find`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        resume_id: input.resumeId,
        title_hint: input.titleHint,
        locations: input.locations,
        include_jsearch: input.includeJsearch,
        linkedin_only: input.linkedinOnly,
      }),
    }),
  );
}

export async function scoreJobs(input: {
  resumeId: string;
  jobIds: string[];
}): Promise<import('./types').ScoreResponse> {
  return unwrap(
    await fetch(`${BASE}/api/scout/score`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ resume_id: input.resumeId, job_ids: input.jobIds }),
    }),
  );
}

export async function jobFromUrl(input: {
  url: string;
  resumeId: string;
}): Promise<import('./types').PastedJob> {
  return unwrap(
    await fetch(`${BASE}/api/scout/from-url`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url: input.url, resume_id: input.resumeId }),
    }),
  );
}

export async function uploadResumeText(
  text: string,
  filename = 'pasted-cv',
): Promise<{ id: string; filename: string }> {
  const body = new FormData();
  body.append('text', text);
  body.append('filename', filename);
  return unwrap(await fetch(`${BASE}/api/resumes/text`, { method: 'POST', body }));
}

export async function getProfile(
  resumeId: string,
): Promise<import('./types').ProfileResponse> {
  return shared(`profile:${resumeId}`, async () =>
    unwrap(await fetch(`${BASE}/api/resumes/${resumeId}/profile`)),
  );
}

export async function getFields(
  resumeId: string,
): Promise<{ resume_id: string; fields: import('./types').FieldFit[] }> {
  return shared(`fields:${resumeId}`, async () =>
    unwrap(await fetch(`${BASE}/api/resumes/${resumeId}/fields`)),
  );
}

/* Deletes the CV, its file on disk, and everything derived from it. Answers
   204, so there is no body to unwrap. */
export async function deleteResume(resumeId: string): Promise<void> {
  const res = await fetch(`${BASE}/api/resumes/${resumeId}`, { method: 'DELETE' });
  if (!res.ok && res.status !== 204) {
    throw new Error(`Could not delete that CV (${res.status}).`);
  }
}

export async function createTailorProposal(input: {
  resumeId: string;
  target: import('./types').TailorTarget;
}): Promise<import('./types').TailorProposal> {
  const body =
    'scoutJobId' in input.target
      ? { resume_id: input.resumeId, scout_job_id: input.target.scoutJobId }
      : { resume_id: input.resumeId, job: input.target.job };
  const payload = JSON.stringify(body);
  return shared(`tailor:${payload}`, async () =>
    unwrap(
      await fetch(`${BASE}/api/tailor`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: payload,
      }),
    ),
  );
}

/* Sends edit IDs only. The server applies its own stored copy of each edit. */
export async function saveVersion(
  proposalId: string,
  name: string,
  acceptedIds: string[],
): Promise<import('./types').CvVersion> {
  return unwrap(
    await fetch(`${BASE}/api/tailor/${proposalId}/versions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, accepted_ids: acceptedIds }),
    }),
  );
}

export async function listVersions(resumeId: string): Promise<import('./types').CvVersion[]> {
  return unwrap(await fetch(`${BASE}/api/resumes/${resumeId}/versions`));
}

export async function deleteVersion(versionId: string): Promise<void> {
  const res = await fetch(`${BASE}/api/versions/${versionId}`, { method: 'DELETE' });
  if (!res.ok && res.status !== 204) await unwrap(res);
}
