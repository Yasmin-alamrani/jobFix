export type Severity = 'critical' | 'major' | 'minor';
export type Status = 'present' | 'weak' | 'missing';
export type Importance = 'critical' | 'preferred';

export interface Deduction {
  rule: string;
  title: string;
  evidence: string;
  fix: string;
  points: number;
  severity: Severity;
}

export interface SubScore {
  key: string;
  label: string;
  earned: number;
  max_points: number;
  deductions: Deduction[];
}

export interface Requirement {
  skill: string;
  importance: Importance;
  status: Status;
  evidence: string;
  note: string;
}

export interface ExperienceFit {
  jd_seniority: string;
  resume_seniority: string;
  years_required: number | null;
  years_evidenced: number | null;
  fit: 'over' | 'match' | 'under' | 'far_under';
  gaps: string[];
  evidence: string[];
}

export interface WritingIssue {
  section: string;
  original: string;
  suggested: string;
  why: string;
  severity: Severity;
}

export interface AnalysisResult {
  overall_score: number;
  sub_scores: SubScore[];
  requirements: Requirement[];
  experience: ExperienceFit;
  writing: { issues: WritingIssue[]; summary_verdict: string };
  top_fixes: Deduction[];
  parse_facts: Record<string, unknown>;
}

export interface Industry { key: string; label: string; }

// --- Agent 2: job scout -----------------------------------------------------

export interface ScoutCandidate {
  id: string;
  title: string;
  company: string;
  location: string;
  similarity: number;
  overlap: string[];
  apply_url: string;
  source: string;
  publisher: string;
  remote: boolean;
}

export interface FindResponse {
  total_found: number;
  by_source: Record<string, number>;
  candidates: ScoutCandidate[];
}

export interface ScoredLine {
  score: number;
  title: string;
  company: string;
  location: string;
  why: string;
  gap: string;
  url: string;
  publisher: string;
  matched: string[];
  missing: string[];
}

export interface ScoreResponse {
  headline: string;
  rendered: string;
  worth_it: number;
  failures: number;
  lines: ScoredLine[];
}

export interface PastedJob {
  title: string;
  company: string;
  location: string;
  description: string;
  apply_url: string;
  source: string;
  score: number | null;
  why: string;
  gap: string;
  matched: string[];
  missing: string[];
}
