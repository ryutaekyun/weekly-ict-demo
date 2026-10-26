const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const UNSAFE_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);

export class UnauthorizedError extends Error {}

function readCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
  return match ? decodeURIComponent(match[1]) : null;
}

/**
 * 인증은 전부 httpOnly 쿠키로 처리한다 — 토큰을 JS(localStorage 등)에 저장하지 않는다.
 * 쿠키는 fetch의 credentials:"include"로 자동 전송되고, 상태를 바꾸는 요청에는
 * 쿠키 기반 CSRF 방어를 위해 csrf_token 쿠키 값을 x-csrf-token 헤더로 함께 보낸다.
 */
export async function apiFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  headers.set("Content-Type", "application/json");

  const method = (options.method ?? "GET").toUpperCase();
  if (UNSAFE_METHODS.has(method)) {
    const csrfToken = readCookie("csrf_token");
    if (csrfToken) headers.set("x-csrf-token", csrfToken);
  }

  const res = await fetch(`${API_BASE}${path}`, { ...options, headers, credentials: "include" });

  if (res.status === 401) throw new UnauthorizedError("로그인이 필요합니다");
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    const detail = body.detail;
    if (detail && typeof detail === "object" && !Array.isArray(detail)) {
      // 구조화된 오류(예: 출력용 확정 차단 사유) — 메시지와 사유 목록을 함께 보여준다
      const reasons = Array.isArray(detail.blocking) ? ` (${detail.blocking.map((b: { message: string }) => b.message).join(" / ")})` : "";
      throw new Error(`${detail.message ?? "요청 실패"}${reasons}`);
    }
    throw new Error(typeof detail === "string" ? detail : `요청 실패 (${res.status})`);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export async function logout(): Promise<void> {
  await fetch(`${API_BASE}/auth/logout`, { method: "POST", credentials: "include" });
}

export type CandidateStatus = "rec" | "review" | "hold" | "final" | "rejected";

export interface Candidate {
  id: string;
  field_code: string;
  title: string;
  summary: string | null;
  issue_cluster_id: string | null;
  source_document_id: string | null;
  announced_date: string | null;
  source_org: string | null;
  recommended_reason: string | null;
  status: CandidateStatus;
  created_by_user_id: string;
  created_at: string;
  updated_at: string;
}

export interface CandidateReview {
  id: string;
  reviewer_user_id: string;
  comment_text: string;
  is_final_approval: boolean;
  decided_status: CandidateStatus | null;
  created_at: string;
}

export interface CandidateRecommendationScore {
  candidate_id: string;
  issue_cluster_id: string | null;
  policy_impact_score: number | null;
  timeliness_score: number | null;
  domestic_relevance_score: number | null;
  novelty_score: number | null;
  analysis_depth_score: number | null;
  total_score: number | null;
  weights_snapshot_json: string;
  reasoning_json: string;
  duplicate_check_json: string | null;
  method: string;
  scored_at: string;
}

export interface CandidateDetail extends Candidate {
  reviews: CandidateReview[];
  recommendation_score: CandidateRecommendationScore | null;
}

export function listCandidates(filters: { field_code?: string; status?: string; q?: string } = {}): Promise<Candidate[]> {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([k, v]) => { if (v) params.set(k, v); });
  const qs = params.toString();
  return apiFetch<Candidate[]>(`/candidates${qs ? `?${qs}` : ""}`);
}

export function updateCandidate(id: string, payload: Partial<{ title: string; summary: string; recommended_reason: string; status: CandidateStatus }>): Promise<Candidate> {
  return apiFetch<Candidate>(`/candidates/${id}`, { method: "PATCH", body: JSON.stringify(payload) });
}

export interface CurrentUser {
  id: string;
  email: string;
  display_name: string;
  role: "researcher" | "reviewer" | "approver" | "admin";
  job_title: string | null;
  is_active: boolean;
}

export function getCurrentUser(): Promise<CurrentUser> {
  return apiFetch<CurrentUser>("/auth/me");
}

// --- 문서(수집자료) --------------------------------------------------------

export interface DocumentListItem {
  id: string;
  title: string;
  origin_url: string;
  attachment_url: string | null;
  source_id: string;
  source_name: string;
  source_org_name: string;
  country_code: string | null;
  published_at: string | null;
  collected_at: string;
  document_type: string;
  status: string;
  primary_field_code: string | null;
  relevance: string | null;
  classification_method: string | null;
  value_rating: string | null;
  extraction_status: string | null;
  issue_cluster_id: string | null;
}

export interface DocumentListResponse {
  items: DocumentListItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface DocumentFilters {
  field_code?: string;
  country_code?: string;
  document_type?: string;
  source_id?: string;
  relevance?: string;
  value_rating?: string;
  q?: string;
  page?: number;
  page_size?: number;
}

export function listDocuments(filters: DocumentFilters = {}): Promise<DocumentListResponse> {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== "") params.set(k, String(v));
  });
  const qs = params.toString();
  return apiFetch<DocumentListResponse>(`/documents${qs ? `?${qs}` : ""}`);
}

export interface ClassificationOut {
  document_id: string;
  primary_field_code: string | null;
  related_field_codes: string[];
  relevance: string;
  confidence: number | null;
  method: string;
  reasoning: string | null;
  is_researcher_overridden: boolean;
  classified_at: string;
}

export interface FullTextOut {
  document_id: string;
  extraction_status: string;
  extraction_method: string;
  char_count: number;
  source_location: string | null;
  content_changed: boolean;
  failure_reason: string | null;
  extracted_at: string;
  full_text: string | null;
}

export interface ValueAssessmentOut {
  document_id: string;
  rating: string;
  reasoning: string | null;
  evidence_quote: string | null;
  method: string;
  is_researcher_overridden: boolean;
  recency_bucket: string | null;
}

export interface StructuredExtractOut {
  document_id: string;
  key_content: string | null;
  background_purpose: string | null;
  policy_tech_change: string | null;
  contested_points: string | null;
  expected_impact_facts: string | null;
  expected_impact_ai_analysis: string | null;
  open_questions: string | null;
  verification_status: string;
  generated_by: string;
}

export interface DocumentAnalysis {
  document_id: string;
  classification: ClassificationOut | null;
  full_text: FullTextOut | null;
  value_assessment: ValueAssessmentOut | null;
  structured_extract: StructuredExtractOut | null;
  ai_runs: unknown[];
}

export function getDocumentMeta(id: string): Promise<DocumentListItem> {
  return apiFetch<DocumentListItem>(`/documents/${id}`);
}

export function getDocumentAnalysis(id: string): Promise<DocumentAnalysis> {
  return apiFetch<DocumentAnalysis>(`/documents/${id}/analysis`);
}

export function getDocumentFullText(id: string): Promise<FullTextOut> {
  return apiFetch<FullTextOut>(`/documents/${id}/full-text`);
}

export function overrideClassification(
  id: string,
  payload: { primary_field_code: string | null; related_field_codes: string[]; relevance: string; reason?: string }
): Promise<ClassificationOut> {
  return apiFetch<ClassificationOut>(`/documents/${id}/classification`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function overrideValueAssessment(
  id: string,
  payload: { rating: string; reason?: string }
): Promise<ValueAssessmentOut> {
  return apiFetch<ValueAssessmentOut>(`/documents/${id}/value-assessment`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

// --- 이슈 클러스터 -----------------------------------------------------------

export interface IssueClusterOut {
  id: string;
  title: string;
  field_code: string;
  first_seen_at: string;
  last_activity_at: string | null;
  status: string;
  summary: string | null;
  review_status: string;
  created_by_method: string | null;
  document_count: number;
}

export interface IssueMemberDocument {
  document_id: string;
  title: string;
  origin_url: string;
  published_at: string | null;
  membership_type: string;
  similarity_score: number | null;
  judgment_reasoning: string | null;
}

export interface IssueTimelineEventOut {
  id: string;
  document_id: string;
  compared_to_document_id: string | null;
  event_type: string;
  event_date: string | null;
  event_date_label: string | null;
  description: string | null;
}

export interface IssueAnalysisOut {
  issue_cluster_id: string;
  key_summary: string | null;
  background_purpose: string | null;
  policy_tech_change: string | null;
  key_figures_json: string | null;
  technical_issues_json: string | null;
  policy_issues_json: string | null;
  industry_concerns_json: string | null;
  unconfirmed_points_json: string | null;
  country_positions_json: string | null;
  domestic_industry_relevance: string | null;
  domestic_rnd_impact: string | null;
  domestic_policy_considerations: string | null;
  domestic_monitoring_points: string | null;
  domestic_has_sufficient_basis: boolean;
  dispute_status: string;
  source_citations_json: string | null;
  verification_status: string;
  generated_by: string;
}

export interface IssueDisputePointOut {
  id: string;
  dispute_title: string;
  claim_a_text: string;
  claim_a_stakeholder: string | null;
  claim_a_source_document_id: string | null;
  claim_b_text: string;
  claim_b_stakeholder: string | null;
  claim_b_source_document_id: string | null;
  common_ground: string | null;
  differences: string | null;
  unresolved_notes: string | null;
  method: string;
}

export interface IssueDetail {
  cluster: IssueClusterOut;
  members: IssueMemberDocument[];
  timeline: IssueTimelineEventOut[];
  analysis: IssueAnalysisOut | null;
  disputes: IssueDisputePointOut[];
}

export interface IssueFilters {
  field_code?: string;
  published_after?: string;
  published_before?: string;
}

export function listIssues(filters: IssueFilters = {}): Promise<IssueClusterOut[]> {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([k, v]) => {
    if (v) params.set(k, v);
  });
  const qs = params.toString();
  return apiFetch<IssueClusterOut[]>(`/issues${qs ? `?${qs}` : ""}`);
}

export function getIssueDetail(id: string): Promise<IssueDetail> {
  return apiFetch<IssueDetail>(`/issues/${id}`);
}

export function mergeIssueCluster(id: string, targetClusterId: string, reason?: string): Promise<IssueClusterOut> {
  return apiFetch<IssueClusterOut>(`/issues/${id}/merge`, {
    method: "PATCH",
    body: JSON.stringify({ target_cluster_id: targetClusterId, reason }),
  });
}

// --- 출처·수집 --------------------------------------------------------------

export interface SourceOut {
  id: string;
  name: string;
  org_name: string;
  field_code: string;
  country_code: string | null;
  url: string;
  source_type: string;
  api_provider: string | null;
  is_primary_source: boolean;
  reliability_tier: number;
  is_active: boolean;
  needs_review: boolean;
  consecutive_failures: number;
  last_attempted_at: string | null;
  last_successful_collection_at: string | null;
  created_at: string;
}

export interface CollectionRunOut {
  id: string;
  source_id: string;
  started_at: string;
  finished_at: string | null;
  status: string;
  items_found: number;
  items_new: number;
  items_duplicate: number;
  items_updated: number;
  error_message: string | null;
  error_type: string | null;
  retry_count: number;
}

export function listSources(filters: { field_code?: string; needs_review?: boolean } = {}): Promise<SourceOut[]> {
  const params = new URLSearchParams();
  if (filters.field_code) params.set("field_code", filters.field_code);
  if (filters.needs_review !== undefined) params.set("needs_review", String(filters.needs_review));
  const qs = params.toString();
  return apiFetch<SourceOut[]>(`/sources${qs ? `?${qs}` : ""}`);
}

export function listSourceRuns(sourceId: string): Promise<CollectionRunOut[]> {
  return apiFetch<CollectionRunOut[]>(`/sources/${sourceId}/runs`);
}

export function triggerCollection(sourceId: string): Promise<CollectionRunOut> {
  return apiFetch<CollectionRunOut>(`/sources/${sourceId}/collect`, { method: "POST" });
}

// --- 대시보드 ---------------------------------------------------------------

export interface DashboardSummary {
  total_documents: number;
  matched_documents: number;
  low_relevance_documents: number;
  pending_review_documents: number;
  unclassified_documents: number;
  by_field: { field_code: string; document_count: number }[];
  extraction_success: number;
  extraction_summary_only: number;
  extraction_partial: number;
  extraction_failed: number;
  extraction_not_attempted: number;
  issue_cluster_total: number;
  issue_cluster_confirmed: number;
  issue_cluster_needs_review: number;
  issue_cluster_multi_document: number;
  candidate_total: number;
  candidate_by_status: Record<string, number>;
  domestic_relevance_assessed: number;
  domestic_relevance_pending: number;
  source_total: number;
  source_active: number;
  source_needs_review: number;
  recent_activity: { document_id: string; title: string; event: string; occurred_at: string }[];
  generated_at: string;
}

export function getDashboardSummary(): Promise<DashboardSummary> {
  return apiFetch<DashboardSummary>("/dashboard/summary");
}

export interface UserSummary {
  id: string;
  display_name: string;
  role: string;
  email: string;
}

export function listUsers(role?: string): Promise<UserSummary[]> {
  return apiFetch<UserSummary[]>(`/users${role ? `?role=${role}` : ""}`);
}

// --- 연구·집필 작업실(Phase 3-1) ---------------------------------------------

export interface EditionOut {
  id: string;
  publication_type: string;
  edition_label: string;
  target_date: string;
  status: string;
  fiscal_year: number | null;
  edition_number: number | null;
  is_special: boolean;
  theme_title: string | null;
  lead_researcher_user_id: string | null;
  reviewer_user_id: string | null;
  manuscript_count: number;
}

export function listEditions(): Promise<EditionOut[]> {
  return apiFetch<EditionOut[]>("/editions");
}

export interface NeedsReexamination {
  flagged: boolean;
  reason: string | null;
}

export interface ManuscriptListItem {
  id: string;
  edition_id: string | null;
  candidate_id: string | null;
  author_user_id: string;
  reviewer_user_id: string | null;
  title: string;
  title_en: string | null;
  manuscript_type: string;
  status: string;
  is_pilot: boolean;
  iitp_selection_status: string;
  lock_version: number;
  created_at: string;
  updated_at: string;
}

export interface ManuscriptDetail extends ManuscriptListItem {
  body: string | null;
  body_json: string | null;
  iitp_selection_note: string | null;
  iitp_confirmed_by_user_id: string | null;
  iitp_confirmed_at: string | null;
  needs_reexamination: NeedsReexamination;
  footnote_verification_total: number;
  footnote_verification_verified: number;
}

export function listManuscripts(filters: { edition_id?: string; status_filter?: string; candidate_id?: string } = {}): Promise<ManuscriptListItem[]> {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([k, v]) => { if (v) params.set(k, v); });
  const qs = params.toString();
  return apiFetch<ManuscriptListItem[]>(`/manuscripts${qs ? `?${qs}` : ""}`);
}

export function createManuscript(payload: { candidate_id?: string; edition_id?: string; manuscript_type: string; title: string; is_pilot?: boolean }): Promise<ManuscriptDetail> {
  return apiFetch<ManuscriptDetail>("/manuscripts", { method: "POST", body: JSON.stringify(payload) });
}

export function getManuscript(id: string): Promise<ManuscriptDetail> {
  return apiFetch<ManuscriptDetail>(`/manuscripts/${id}`);
}

export function getManuscriptContext(id: string): Promise<{ candidate: CandidateDetail | null; issue: IssueDetail | null }> {
  return apiFetch(`/manuscripts/${id}/context`);
}

export function updateManuscriptBody(
  id: string,
  payload: { title?: string; title_en?: string; body_json: string; body: string; lock_version: number; change_note?: string; is_milestone?: boolean },
): Promise<ManuscriptDetail> {
  return apiFetch<ManuscriptDetail>(`/manuscripts/${id}`, { method: "PATCH", body: JSON.stringify(payload) });
}

export interface ManuscriptVersionListItem {
  id: string;
  version_no: number;
  edited_by_user_id: string;
  change_note: string | null;
  is_milestone: boolean;
  created_at: string;
}

export interface ManuscriptVersionDetail extends ManuscriptVersionListItem {
  manuscript_id: string;
  body_snapshot: string;
  body_json_snapshot: string | null;
}

export function listManuscriptVersions(id: string): Promise<ManuscriptVersionListItem[]> {
  return apiFetch<ManuscriptVersionListItem[]>(`/manuscripts/${id}/versions`);
}

export function getManuscriptVersion(id: string, versionId: string): Promise<ManuscriptVersionDetail> {
  return apiFetch<ManuscriptVersionDetail>(`/manuscripts/${id}/versions/${versionId}`);
}

export function restoreManuscriptVersion(id: string, versionId: string): Promise<ManuscriptDetail> {
  return apiFetch<ManuscriptDetail>(`/manuscripts/${id}/versions/${versionId}/restore`, { method: "POST" });
}

export function requestManuscriptReview(id: string, reviewerUserId: string): Promise<ManuscriptDetail> {
  return apiFetch<ManuscriptDetail>(`/manuscripts/${id}/review-request`, { method: "POST", body: JSON.stringify({ reviewer_user_id: reviewerUserId }) });
}

export function requestManuscriptChanges(id: string, commentText: string): Promise<ManuscriptDetail> {
  return apiFetch<ManuscriptDetail>(`/manuscripts/${id}/request-changes`, { method: "POST", body: JSON.stringify({ comment_text: commentText }) });
}

export function approveManuscript(id: string, comment?: string): Promise<ManuscriptDetail> {
  return apiFetch<ManuscriptDetail>(`/manuscripts/${id}/approve`, { method: "POST", body: JSON.stringify({ comment }) });
}

export function reopenManuscript(id: string): Promise<ManuscriptDetail> {
  return apiFetch<ManuscriptDetail>(`/manuscripts/${id}/reopen`, { method: "POST" });
}

export function updateIitpSelection(id: string, payload: { iitp_selection_status: string; iitp_selection_note?: string }): Promise<ManuscriptDetail> {
  return apiFetch<ManuscriptDetail>(`/manuscripts/${id}/iitp-selection`, { method: "PATCH", body: JSON.stringify(payload) });
}

export interface FootnoteOut {
  id: string;
  manuscript_id: string;
  mark_id: string;
  anchor_text: string;
  source_document_id: string | null;
  source_url: string;
  source_org: string | null;
  excerpt: string | null;
  location_label: string | null;
  published_at: string | null;
  accessed_at: string | null;
  verification_status: string;
  verified_by_user_id: string | null;
  verified_at: string | null;
  created_by_user_id: string;
  updated_at: string;
}

export function listFootnotes(manuscriptId: string): Promise<FootnoteOut[]> {
  return apiFetch<FootnoteOut[]>(`/manuscripts/${manuscriptId}/footnotes`);
}

export function createFootnote(manuscriptId: string, payload: {
  mark_id: string; anchor_text: string; source_url: string; source_document_id?: string;
  source_org?: string; excerpt?: string; location_label?: string;
}): Promise<FootnoteOut> {
  return apiFetch<FootnoteOut>(`/manuscripts/${manuscriptId}/footnotes`, { method: "POST", body: JSON.stringify(payload) });
}

export function updateFootnote(manuscriptId: string, footnoteId: string, payload: Partial<FootnoteOut>): Promise<FootnoteOut> {
  return apiFetch<FootnoteOut>(`/manuscripts/${manuscriptId}/footnotes/${footnoteId}`, { method: "PATCH", body: JSON.stringify(payload) });
}

export function verifyFootnote(manuscriptId: string, footnoteId: string, matched: boolean): Promise<FootnoteOut> {
  return apiFetch<FootnoteOut>(`/manuscripts/${manuscriptId}/footnotes/${footnoteId}/verify?matched=${matched}`, { method: "POST" });
}

export function deleteFootnote(manuscriptId: string, footnoteId: string): Promise<void> {
  return apiFetch<void>(`/manuscripts/${manuscriptId}/footnotes/${footnoteId}`, { method: "DELETE" });
}

export interface ManuscriptCommentOut {
  id: string;
  manuscript_id: string;
  author_user_id: string;
  parent_comment_id: string | null;
  anchor_text: string | null;
  comment_text: string;
  status: string;
  resolved_by_user_id: string | null;
  resolved_at: string | null;
  created_at: string;
}

export function listManuscriptComments(manuscriptId: string): Promise<ManuscriptCommentOut[]> {
  return apiFetch<ManuscriptCommentOut[]>(`/manuscripts/${manuscriptId}/comments`);
}

export function createManuscriptComment(manuscriptId: string, payload: { comment_text: string; anchor_text?: string; parent_comment_id?: string }): Promise<ManuscriptCommentOut> {
  return apiFetch<ManuscriptCommentOut>(`/manuscripts/${manuscriptId}/comments`, { method: "POST", body: JSON.stringify(payload) });
}

export function resolveManuscriptComment(manuscriptId: string, commentId: string): Promise<ManuscriptCommentOut> {
  return apiFetch<ManuscriptCommentOut>(`/manuscripts/${manuscriptId}/comments/${commentId}/resolve`, { method: "POST" });
}

// ---- Phase 3-2: 보고서·요약본 제작 ------------------------------------------
export interface ReportListItem {
  id: string; report_type: "general" | "special" | "summary"; title: string; status: string;
  edition_id: string | null; created_by_user_id: string; created_at: string; updated_at: string;
}
export interface ReportItemOut {
  id: string; position: number; part_key: string | null; heading: string | null; manuscript_id: string | null;
  manuscript_title: string | null; manuscript_status: string | null; summary_text: string | null;
  source_sentence: string | null; needs_review: boolean;
}
export interface PreflightIssue { level: "error" | "warn" | "info"; code: string; message: string; part: string | null }
export interface ReportDetail extends ReportListItem {
  title_en: string | null; publish_date: string | null; template_id: string | null; iitp_confirmed: boolean;
  layout: "standard" | "compact"; finalize_exception_reason: string | null; finalized_at: string | null;
  items: ReportItemOut[]; preflight: PreflightIssue[]; blocking: PreflightIssue[];
}
export interface ReportExportOut {
  id: string; report_id: string; file_format: "docx" | "pdf"; status: "running" | "success" | "failed";
  error_message: string | null; template_version: number | null; file_name: string | null;
  file_sha256: string | null; file_size: number | null; page_count: number | null;
  footnote_count: number | null; table_count: number | null; is_final: boolean;
  created_by_user_id: string; created_at: string; finished_at: string | null;
  manuscript_versions_json: string | null; validation_json: string | null;
}

export const listReports = () => apiFetch<ReportListItem[]>("/reports");
export const createReport = (payload: { report_type: string; title: string; title_en?: string; layout?: "standard" | "compact" }) =>
  apiFetch<ReportDetail>("/reports", { method: "POST", body: JSON.stringify(payload) });
export const getReport = (id: string) => apiFetch<ReportDetail>(`/reports/${id}`);
export const updateReport = (id: string, payload: Partial<{ title: string; title_en: string }>) =>
  apiFetch<ReportDetail>(`/reports/${id}`, { method: "PATCH", body: JSON.stringify(payload) });
export const addReportItem = (id: string, payload: { part_key?: string; heading?: string; manuscript_id: string }) =>
  apiFetch<ReportDetail>(`/reports/${id}/items`, { method: "POST", body: JSON.stringify(payload) });
export const addSummaryItem = (id: string, payload: { part_key: string; manuscript_id: string; source_sentence: string }) =>
  apiFetch<ReportDetail>(`/reports/${id}/summary-items`, { method: "POST", body: JSON.stringify(payload) });
export const updateReportItem = (id: string, itemId: string, payload: Partial<{ heading: string; summary_text: string }>) =>
  apiFetch<ReportDetail>(`/reports/${id}/items/${itemId}`, { method: "PATCH", body: JSON.stringify(payload) });
export const deleteReportItem = (id: string, itemId: string) =>
  apiFetch<ReportDetail>(`/reports/${id}/items/${itemId}`, { method: "DELETE" });
export const reorderReportItems = (id: string, itemIds: string[]) =>
  apiFetch<ReportDetail>(`/reports/${id}/items/reorder`, { method: "POST", body: JSON.stringify({ item_ids: itemIds }) });
export const getSourceSentences = (manuscriptId: string) =>
  apiFetch<{ manuscript_id: string; title: string; sentences: string[] }>(`/reports/source-sentences/${manuscriptId}`);
export const listReportExports = (id: string) => apiFetch<ReportExportOut[]>(`/reports/${id}/exports`);
export const createReportExport = (id: string, fileFormat: "docx" | "pdf") =>
  apiFetch<ReportExportOut>(`/reports/${id}/exports`, { method: "POST", body: JSON.stringify({ file_format: fileFormat }) });
export const finalizeReport = (id: string, exceptionReason?: string) =>
  apiFetch<ReportDetail>(`/reports/${id}/finalize`, { method: "POST", body: JSON.stringify({ exception_reason: exceptionReason || null }) });
export const reopenReport = (id: string) => apiFetch<ReportDetail>(`/reports/${id}/reopen`, { method: "POST" });

/** 인증 쿠키로 출력 파일을 받아 Blob으로 돌려준다(브라우저 다운로드·PDF 미리보기에 사용). */
export async function fetchReportExportBlob(reportId: string, exportId: string): Promise<Blob> {
  const res = await fetch(`${API_BASE}/reports/${reportId}/exports/${exportId}/download`, { credentials: "include" });
  if (res.status === 401) throw new UnauthorizedError("로그인이 필요합니다");
  if (!res.ok) throw new Error("파일을 내려받을 수 없습니다");
  return res.blob();
}
