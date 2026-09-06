import type { AnalysisResult, Industry } from './types';

const BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

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
