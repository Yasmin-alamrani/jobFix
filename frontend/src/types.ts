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

export type RequirementCategory =
  | 'skill'
  | 'experience'
  | 'education'
  | 'certification'
  | 'language'
  | 'location';

export interface Requirement {
  skill: string;
  // Absent on analyses stored before categories existed.
  category?: RequirementCategory;
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
  seniority: string;
  work_mode: string;
  posted_at: string | null;
}

export interface FindResponse {
  total_found: number;
  by_source: Record<string, number>;
  candidates: ScoutCandidate[];
  hidden: Record<string, number>;
}

export interface ScoredLine {
  id: string;
  score: number;
  seniority: string;
  work_mode: string;
  posted_at: string | null;
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

// --- Feature 1: the CV as structured entities -------------------------------

export interface CvContact {
  name: string;
  email: string;
  phone: string;
  location: string;
  links: string[];
}

export interface CvExperience {
  title: string;
  company: string;
  location: string;
  start: string;
  end: string;
  start_year: number | null;
  end_year: number | null;
  current: boolean;
  bullets: string[];
}

export interface CvEducation {
  degree: string;
  field_of_study: string;
  institution: string;
  location: string;
  start: string;
  end: string;
  end_year: number | null;
  grade: string;
}

export interface CvCertification { name: string; issuer: string; year: string; }
export interface CvProject {
  name: string;
  description: string;
  technologies: string[];
  link: string;
}
export interface CvLanguage { name: string; proficiency: string; }

export interface CvProfile {
  is_resume: boolean;
  contact: CvContact;
  summary: string;
  experience: CvExperience[];
  education: CvEducation[];
  skills: string[];
  certifications: CvCertification[];
  projects: CvProject[];
  languages: CvLanguage[];
}

export interface ProfileResponse {
  resume_id: string;
  profile: CvProfile;
  prompt_version: string;
  sections_present: string[];
  sections_missing: string[];
}

export interface FieldComponent {
  key: string;
  label: string;
  earned: number;
  max_points: number;
  why: string;
}

export interface FieldFit {
  key: string;
  label: string;
  score: number;
  components: FieldComponent[];
  matched_skills: string[];
  missing_skills: string[];
  years_in_field: number | null;
  title_alignment: 'direct' | 'adjacent' | 'distant' | string;
  justification: string;
}

// --- Tailoring and saved versions ------------------------------------------

export interface JobIn {
  title: string;
  company: string;
  location: string;
  description: string;
  apply_url: string;
  source: string;
}

/* A search result is named by ID and resolved from the server's cache; a pasted
   or audited posting travels as fields. */
export type TailorTarget = { scoutJobId: string } | { job: JobIn };

export interface DiffOp {
  op: 'equal' | 'insert' | 'delete';
  text: string;
}

export interface TailorEdit {
  id: string;
  kind: 'rewrite' | 'reorder' | 'add_skill';
  target: string;
  label: string;
  before_text: string;
  after_text: string;
  before_items: string[];
  after_items: string[];
  order: number[];
  diff: DiffOp[];
  evidence: string;
  why: string;
  requirement: string;
  has_placeholder: boolean;
  violations: string[];
}

export interface TailorGap {
  requirement: string;
  importance: 'critical' | 'preferred';
  advice: string;
}

export interface TailorProposal {
  proposal_id: string;
  job_id: string;
  job_title: string;
  company: string;
  edits: TailorEdit[];
  blocked: TailorEdit[];
  gaps: TailorGap[];
  prompt_version: string;
}

export interface CvVersion {
  id: string;
  name: string;
  resume_id: string;
  job_id: string | null;
  job_title: string;
  company: string;
  is_original: boolean;
  accepted_edit_ids: string[];
  placeholders: number;
  created_at: string;
  profile: CvProfile;
}

// --- Export -----------------------------------------------------------------

export type ExportFormat = 'pdf' | 'docx';

export interface PlaceholderSlot {
  index: number;
  target: string;
  label: string;
  text: string;
  placeholder: string;
}

// --- Job search filters and job-link analysis -------------------------------

export type WorkMode = 'any' | 'remote' | 'hybrid' | 'onsite';

export interface ScoutFilters {
  workMode: WorkMode;
  seniority: string[];
  postedWithinDays: number | null;
  includeUnstated: boolean;
}

export interface FetchedJob {
  title: string;
  company: string;
  location: string;
  description: string;
  apply_url: string;
  source: string;
}

export type TargetingBasis = 'stated' | 'inferred';

export interface TargetingSignal {
  point: string;
  basis: TargetingBasis;
  quote: string;
}

export interface TargetingAction {
  action: string;
  why: string;
  basis: TargetingBasis;
  quote: string;
}

export interface Targeting {
  values: TargetingSignal[];
  tone: TargetingSignal;
  keywords: string[];
  actions: TargetingAction[];
  caveat: string;
  prompt_version: string;
}
