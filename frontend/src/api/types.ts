export type AccountRole = "USER" | "SYSTEM_OWNER" | "ADMIN";
export type AccountStatus = "ACTIVE" | "DISABLED";
export type AccountSource = "LOCAL_IMPORT" | "ADMIN_CREATED" | "SSO";
export type BusinessSystemStatus = "ACTIVE" | "DISABLED";
export type SystemRole = "SYSTEM_OWNER";

export interface SystemRoleView {
  system_id: string;
  role: SystemRole;
}

export interface CurrentUser {
  id: string;
  username: string;
  display_name: string;
  role: AccountRole;
  status: AccountStatus;
  must_change_password: boolean;
  system_roles: SystemRoleView[];
}

export interface SessionView {
  user: CurrentUser;
  must_change_password: boolean;
  csrf_token: string;
  expires_at: string;
}

export interface AccountView {
  id: string;
  username: string;
  display_name: string;
  role: AccountRole;
  source: AccountSource;
  status: AccountStatus;
  must_change_password: boolean;
  credential_batch: string | null;
  external_provider: string | null;
  created_at: string;
  updated_at: string;
}

export interface AccountPage {
  items: AccountView[];
  page: number;
  page_size: number;
  total: number;
}

export interface SystemOwnerView {
  account_id: string;
  username: string;
  display_name: string;
}

export interface BusinessSystemView {
  id: string;
  code: string;
  name: string;
  description: string | null;
  status: BusinessSystemStatus;
  owners: SystemOwnerView[];
  created_at: string;
  updated_at: string;
}

export interface BusinessSystemPage {
  items: BusinessSystemView[];
  page: number;
  page_size: number;
  total: number;
}

export type TicketStatus = "open" | "assigned" | "in_progress" | "resolved" | "closed";
export type TicketPriority = "normal";
export type ReplyAuthorRole = "requester" | "assignee" | "reviewer";
export type CandidateStatus = "pending" | "approved" | "published" | "rejected";
export type EvidenceDecisionOutcome = "sufficient" | "insufficient" | "conflicting";
export type EvidenceReasonCode =
  | "no_evidence"
  | "source_location_missing"
  | "score_below_threshold"
  | "score_gap_too_small"
  | "required_term_not_covered"
  | "conflicting_evidence"
  | "evidence_budget_empty"
  | "answer_not_grounded";
export type QuestionResolutionStatus = "answered" | "refused";

export interface SseAuthToken {
  token: string;
  account_id: string;
  run_id: string;
  system_id: string;
  question: string;
  required_terms: string[];
  expires_at: string;
}

export interface LocatorView {
  document_id: string | null;
  document_version_id: string | null;
  source_type: string;
  block_index: number;
  page_number: number | null;
  bounding_box: [number, number, number, number] | null;
  heading_path: string[];
  paragraph_start: number | null;
  paragraph_end: number | null;
  line_start: number | null;
  line_end: number | null;
  table_index: number | null;
  table_row_start: number | null;
  table_row_end: number | null;
  sheet_name: string | null;
  cell_range: string | null;
  ticket_id: string | null;
}

export interface CitationView {
  rank: number;
  claim_rank: number;
  chunk_id: string;
  source_id: string;
  source_name: string;
  source_version: string;
  quoted_text: string;
  locators: LocatorView[];
}

export interface ClaimView {
  rank: number;
  text: string;
  citation_ranks: number[];
}

export interface AnswerView {
  text: string;
  claims: ClaimView[];
  citations: CitationView[];
  model: string;
  prompt_version: string;
}

export interface EvidenceItemView {
  evidence_id: string;
  source_name: string;
  source_version: string;
  quoted_text: string;
}

export interface RetrievalStartedEvent {
  type: "retrieval_started";
  run_id: string;
  system_id: string;
  question: string;
}

export interface EvidenceReadyEvent {
  type: "evidence_ready";
  run_id: string;
  evidence: EvidenceItemView[];
  degraded_reasons: string[];
}

export interface DecisionEvent {
  type: "decision";
  run_id: string;
  outcome: EvidenceDecisionOutcome;
  policy_version: string;
  reason_codes: EvidenceReasonCode[];
  decided_at: string;
}

export interface AnswerDeltaEvent {
  type: "answer_delta";
  run_id: string;
  delta: string;
}

export interface AnswerCompletedEvent {
  type: "answer_completed";
  run_id: string;
  answer: AnswerView;
  degraded_reasons: string[];
}

export interface RefusedEvent {
  type: "refused";
  run_id: string;
  ticket_id: string;
  outcome: EvidenceDecisionOutcome;
  reason_codes: EvidenceReasonCode[];
  policy_version: string;
  decided_at: string;
}

export interface StreamErrorEvent {
  type: "error";
  run_id: string;
  code: string;
  message: string;
}

export type QuestionStreamEvent =
  | RetrievalStartedEvent
  | EvidenceReadyEvent
  | DecisionEvent
  | AnswerDeltaEvent
  | AnswerCompletedEvent
  | RefusedEvent
  | StreamErrorEvent;

export interface TicketView {
  id: string;
  system_id: string;
  requester_id: string;
  source_run_id: string;
  assignee_id: string | null;
  status: TicketStatus;
  priority: TicketPriority;
  title: string;
  question: string;
  normalized_question: string;
  occurrence_count: number;
  created_at: string;
  updated_at: string;
}

export interface TicketPage {
  items: TicketView[];
  page: number;
  page_size: number;
  total: number;
}

export interface TicketReplyView {
  id: string;
  ticket_id: string;
  system_id: string;
  author_id: string;
  author_role: ReplyAuthorRole;
  body: string;
  created_at: string;
}

export interface TicketTransitionView {
  id: string;
  ticket_id: string;
  system_id: string;
  actor_id: string;
  from_status: TicketStatus | null;
  to_status: TicketStatus;
  action: string;
  created_at: string;
}

export interface KnowledgeCandidateView {
  id: string;
  ticket_id: string;
  system_id: string;
  answer: string;
  author_id: string;
  reviewer_id: string | null;
  status: CandidateStatus;
  knowledge_source_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface ApiErrorBody {
  code: string;
  message: string;
  request_id: string;
  details?: Record<string, string | number | boolean> | null;
}
