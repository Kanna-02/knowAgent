export type AccountRole = "USER" | "SYSTEM_OWNER" | "ADMIN";
export type AccountStatus = "ACTIVE" | "DISABLED";
export type AccountSource = "LOCAL_IMPORT" | "ADMIN_CREATED" | "SSO";
export type BusinessSystemStatus = "ACTIVE" | "DISABLED";
export type SystemRole = "SYSTEM_OWNER";

export type PublicationStatus = "DRAFT" | "PUBLISHED" | "RETIRED";
export type DocumentVersionStatus =
  "UPLOADED" | "PARSING" | "CHUNKING" | "CHUNKED" | "READY_DRAFT" | "OCR_REQUIRED" | "FAILED";
export type GapSource = "refusal" | "unsolved_ticket";

export interface DocumentView {
  id: string;
  system_id: string;
  name: string;
  current_published_version_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface DocumentPage {
  items: DocumentView[];
  page: number;
  page_size: number;
  total: number;
}

export interface DocumentVersionView {
  id: string;
  document_id: string;
  system_id: string;
  version_no: number;
  filename: string;
  media_type: string;
  size_bytes: number;
  sha256: string;
  status: DocumentVersionStatus;
  publish_status: PublicationStatus;
  chunk_count: number;
  parser_name: string | null;
  parser_version: string | null;
  published_at: string | null;
  retired_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface DocumentVersionPage {
  items: DocumentVersionView[];
  page: number;
  page_size: number;
  total: number;
}

export interface PublishVersionResponse {
  document_id: string;
  version_id: string;
  system_id: string;
  publish_status: PublicationStatus;
  published_at: string;
}

export interface RetireVersionResponse {
  document_id: string;
  version_id: string;
  system_id: string;
  publish_status: PublicationStatus;
  retired_at: string;
}

export interface SystemOverviewView {
  system_id: string;
  question_count: number;
  refusal_count: number;
  open_ticket_count: number;
  resolved_ticket_count: number;
  total_ticket_count: number;
}

export interface FrequentQuestionView {
  normalized_question: string;
  occurrence_count: number;
  refusal_count: number;
  ticket_count: number;
}

export interface FrequentQuestionPage {
  items: FrequentQuestionView[];
  total: number;
}

export interface KnowledgeGapView {
  normalized_question: string;
  gap_source: GapSource;
  occurrence_count: number;
  last_seen_at: string;
}

export interface KnowledgeGapPage {
  items: KnowledgeGapView[];
  total: number;
}

export interface AuditLogView {
  id: string;
  actor_id: string | null;
  action: string;
  object_type: string | null;
  object_id: string | null;
  result: string;
  request_id: string | null;
  context_data: Record<string, string | number | boolean> | null;
  created_at: string;
  detail: string | null;
}

export interface AuditLogPage {
  items: AuditLogView[];
  page: number;
  page_size: number;
  total: number;
}

export type NotificationAuthType = "NONE" | "BEARER" | "HEADER";
export type NotificationEventType = "ticket_created" | "ticket_replied";
export type NotificationDeliveryStatus =
  | "PENDING"
  | "QUEUED"
  | "DELIVERING"
  | "RETRY_SCHEDULED"
  | "DELIVERED"
  | "PERMANENT_FAILURE"
  | "SKIPPED";

export interface NotificationConfigurationView {
  id: string;
  enabled: boolean;
  endpoint_url: string;
  auth_type: NotificationAuthType;
  auth_header_name: string | null;
  secret_reference: string | null;
  ticket_created_template: string;
  ticket_replied_template: string;
  success_status_codes: number[];
  timeout_seconds: number;
  max_attempts: number;
  retry_base_seconds: number;
  updated_by: string | null;
  created_at: string;
  updated_at: string;
}

export type NotificationConfigurationUpdate = Omit<
  NotificationConfigurationView,
  "id" | "updated_by" | "created_at" | "updated_at"
>;

export interface NotificationDeliveryView {
  id: string;
  outbox_id: string;
  event_type: NotificationEventType;
  recipient_id: string | null;
  recipient_address: string;
  status: NotificationDeliveryStatus;
  idempotency_key: string;
  attempt_count: number;
  cycle_attempt: number;
  next_attempt_at: string | null;
  last_status_code: number | null;
  last_error_code: string | null;
  last_error_message: string | null;
  provider_message_id: string | null;
  response_summary: string | null;
  delivered_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface NotificationDeliveryPage {
  items: NotificationDeliveryView[];
  page: number;
  page_size: number;
  total: number;
}

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
  conversation_id: string | null;
  retrieval_profile: string | null;
  expires_at: string;
}

export type ConversationMessageRole = "user" | "assistant";
export type IntentKind = "follow_up" | "standalone";

export interface ConversationView {
  id: string;
  system_id: string;
  account_id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

export interface ConversationPage {
  items: ConversationView[];
  page: number;
  page_size: number;
  total: number;
}

export interface ConversationMessageView {
  id: string;
  role: ConversationMessageRole;
  content: string;
  intent: IntentKind | null;
  rewritten_query: string | null;
  rewrite_prompt_version: string | null;
  created_at: string;
}

export interface ConversationDetail {
  conversation: ConversationView;
  messages: ConversationMessageView[];
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
  rewritten_query: string | null;
  intent: IntentKind | null;
  rewrite_prompt_version: string | null;
  retrieval_profile_name?: string | null;
  retrieval_profile_version?: string | null;
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
  retrieval_profile_name?: string | null;
  retrieval_profile_version?: string | null;
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
  degraded_reasons: string[];
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

export type PromptScenario = "grounded_answer" | "query_rewrite";

export interface PromptDefinitionView {
  scenario: PromptScenario;
  version: string;
  content: string;
  enabled: boolean;
  created_at: string;
  change_note: string;
}

export interface PromptDefinitionPage {
  items: PromptDefinitionView[];
  page: number;
  page_size: number;
  total: number;
}

export interface RetrievalProfileView {
  name: string;
  version: string;
  keyword_top_k: number;
  vector_top_k: number;
  result_top_k: number;
  rrf_k: number;
  keyword_weight: number;
  vector_weight: number;
  rerank_candidate_top_k: number;
  rerank_top_k: number;
  evidence_max_items: number;
  evidence_max_characters: number;
  is_active: boolean;
  created_at: string;
  change_note: string;
}

export interface RetrievalProfilePage {
  items: RetrievalProfileView[];
  page: number;
  page_size: number;
  total: number;
}

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
