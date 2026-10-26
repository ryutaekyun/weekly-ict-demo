import { apiFetch, UnauthorizedError } from "@/lib/api";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// ---- Phase 3-4: 주간기술동향지 -------------------------------------------------
export interface JStep {
  id: string; step_key: string; label: string; offset_days: number; window_start_days: number | null; due_date: string | null;
  window_start_date: string | null; completed_at: string | null; state: "done" | "delayed" | "due_soon" | "upcoming" | "no_date"; impact: string | null; note: string | null;
}
export interface JIssue {
  id: string; year: number; issue_no: number; label: string; publish_date: string | null; status: string; status_label: string;
  tech_field: string | null; topic: string | null; editor_user_id: string | null; editor_name: string | null; iitp_confirmed: boolean;
  iitp_note: string | null; published_at: string | null; is_synthetic: boolean; note: string | null; steps: JStep[];
}
export interface JCommission {
  id: string; issue_id: string; issue_label: string; expert_id: string; expert_name: string | null; expert_code: string | null; topic: string;
  purpose: string | null; outline: string | null; length_spec: string | null; format_spec: string | null; due_date: string | null;
  delivery_method: string | null; contact_info: string | null; status: string; status_label: string; mail_subject: string | null;
  mail_body: string | null; mail_status: string; mail_notice: string; manuscript_id: string | null;
  events?: { event: string; from: string | null; to: string | null; note: string | null; at: string }[];
}
export interface JExpert {
  id: string; expert_code: string; name: string; affiliation: string; department: string | null; position_title: string | null; fields: string[];
  research_summary: string | null; email: string | null; phone: string | null; consent_status: string; consent_at: string | null; anonymized: boolean;
  user_id: string | null; is_synthetic: boolean; notes: string | null; commission_counts: Record<string, number>;
  history: { manuscript_id: string; title: string; issue: string | null; status: string; status_label: string }[]; accepted_before?: number; note?: string;
}
export interface JFormatItem { key: string; label: string; status: "pass" | "fail" | "warn" | "info"; detail: string }
export interface JVersion {
  id: string; version_no: number; kind: string; kind_label: string; file_name: string; file_size: number; sha256: string; uploaded_at: string;
  uploaded_by: string | null; note: string | null; scan: { warnings?: string[] }; extract: Record<string, unknown>;
  format_check: { items?: JFormatItem[]; needs_fix?: boolean }; proof_checklist: Record<string, boolean> | null;
}
export interface JComment {
  id: string; kind: string; scope: string; anchor_text: string | null; text: string; requires_revision: boolean; status: "open" | "answered" | "resolved";
  author_reply: string | null; author_name: string | null; created_at: string; version_no: number | null; assignment_id: string | null;
}
export interface JAssignment {
  id: string; reviewer_user_id: string; reviewer_name: string | null; round: number; role_kind: string; due_date: string | null; status: string;
  conflict_declared: boolean; conflict_checked: boolean; conflict_note: string | null; recommendation: string | null; summary_opinion: string | null; overdue: boolean;
}
export interface JManuscript {
  id: string; issue_id: string; issue_label: string; commission_id: string; expert_name: string | null; title: string; title_en: string | null;
  summary: string | null; authors: { name: string; affiliation: string; corresponding?: boolean }[]; references_text: string | null; status: string;
  status_label: string; format_status: string; content_status: string; copyright_confirmed: boolean; third_party_note: string | null;
  lock_version: number; version_count: number; is_synthetic: boolean; versions: JVersion[]; comments: JComment[];
  attachments: { id: string; doc_type: string; file_name: string; file_size: number; sha256: string; uploaded_at: string }[];
  required_docs: { key: string; label: string }[]; proof_confirmed: boolean; outcomes: { key: string; label: string; effect: string }[];
  open_comment_count: number; review_validity?: { change_ratio: number; threshold: number; needs_rereview: boolean; message: string | null };
  assignments?: JAssignment[];
  decisions?: { id: string; round: number; outcome: string; note: string | null; is_final: boolean; decided_by: string | null; decided_at: string }[];
  plagiarism?: { id: string; service_name: string | null; file_name: string; similarity_pct: number | null; status: string; note: string | null }[];
  plagiarism_notice?: string;
}
export interface JCompare {
  from_version: number; to_version: number; changes: { type: "added" | "deleted" | "modified"; old?: string; new?: string; similarity?: number }[];
  counts: { added: number; deleted: number; modified: number }; needs_original_compare: boolean; original_compare_reasons: string[];
  comment_mapping: (JComment & { match: string; note: string })[]; notice: string; identical_text: boolean;
}
export interface JDash {
  year: number | null; today: string;
  plan: { planned_issues: number; with_publish_date: number; published_records: number; iitp_confirmed: number; note: string };
  commission_status: Record<string, number>; manuscript_status: Record<string, number>; review: { assigned: number; completed: number };
  delayed: JAlert[]; upcoming: JAlert[];
  issues: { id: string; label: string; publish_date: string | null; status: string; status_label: string; topic: string | null; tech_field: string | null;
    editor_user_id: string | null; iitp_confirmed: boolean; commissions: number; accepted: number; manuscripts: number; accepted_manuscripts: number; delayed_steps: number }[];
}
export interface JAlert { kind: string; issue_id: string; issue_label: string; label: string; due_date: string; state: string; days: number }
export interface JExport {
  id: string; file_format: "docx" | "pdf"; status: string; error_message: string | null; file_name: string | null; file_sha256: string | null;
  file_size: number | null; page_count: number | null; is_final: boolean; created_at: string; template_version: number | null;
  items: { manuscript_id: string; version_no: number; sha256: string }[]; validation: { issues?: { level: string; code: string; message: string }[]; part_pages?: { heading: string; start_page?: number }[] | null; toc_verified?: boolean | null };
}
export interface JIssueDetail extends JIssue {
  commissions: JCommission[]; manuscripts: { id: string; title: string; expert_name: string; status: string; status_label: string; version_count: number; format_status: string; proof_confirmed: boolean }[];
  items: { manuscript_id: string; version_id: string; position: number; title: string; version_no: number }[];
  export_preflight: { level: string; code: string; message: string }[]; exports: JExport[];
}

export const jDashboard = (year?: number, mine = false) => apiFetch<JDash>(`/journal/dashboard?${year ? `year=${year}&` : ""}mine=${mine}`);
export const jPlanYear = (year: number, count = 25) => apiFetch<{ created: number; total: number }>("/journal/issues/plan-year", { method: "POST", body: JSON.stringify({ year, count }) });
export const jIssue = (id: string) => apiFetch<JIssueDetail>(`/journal/issues/${id}`);
export const jPatchIssue = (id: string, body: Record<string, unknown>) => apiFetch<JIssue>(`/journal/issues/${id}`, { method: "PATCH", body: JSON.stringify(body) });
export const jCompleteStep = (issueId: string, stepId: string, note?: string) => apiFetch<JIssue>(`/journal/issues/${issueId}/steps/${stepId}/complete`, { method: "POST", body: JSON.stringify({ note }) });
export const jReopenStep = (issueId: string, stepId: string) => apiFetch<JIssue>(`/journal/issues/${issueId}/steps/${stepId}/reopen`, { method: "POST" });
export const jIitp = (id: string, confirmed: boolean, note?: string) => apiFetch<JIssue>(`/journal/issues/${id}/iitp`, { method: "POST", body: JSON.stringify({ confirmed, note }) });
export const jPublish = (id: string) => apiFetch<JIssue>(`/journal/issues/${id}/publish`, { method: "POST" });
export const jSetItems = (id: string, manuscript_ids: string[]) => apiFetch<JIssueDetail>(`/journal/issues/${id}/items`, { method: "PUT", body: JSON.stringify({ manuscript_ids }) });
export const jCreateExport = (id: string, file_format: "docx" | "pdf", final: boolean) => apiFetch<JExport>(`/journal/issues/${id}/exports`, { method: "POST", body: JSON.stringify({ file_format, final }) });
export const jExperts = (q?: string, field?: string) => apiFetch<JExpert[]>(`/journal/experts?${new URLSearchParams({ ...(q ? { q } : {}), ...(field ? { field } : {}) })}`);
export const jExpert = (id: string) => apiFetch<JExpert>(`/journal/experts/${id}`);
export const jCreateExpert = (body: Record<string, unknown>) => apiFetch<JExpert>("/journal/experts", { method: "POST", body: JSON.stringify(body) });
export const jConsent = (id: string, consent_status: string) => apiFetch<JExpert>(`/journal/experts/${id}/consent`, { method: "POST", body: JSON.stringify({ consent_status }) });
export const jCreateCommission = (body: Record<string, unknown>) => apiFetch<JCommission>("/journal/commissions", { method: "POST", body: JSON.stringify(body) });
export const jCommissionStatus = (id: string, status: string, note?: string) => apiFetch<JCommission>(`/journal/commissions/${id}/status`, { method: "POST", body: JSON.stringify({ status, note }) });
export const jMailPreview = (id: string) => apiFetch<{ subject: string; body: string; notice: string }>(`/journal/commissions/${id}/mail-preview`);
export const jSaveMail = (id: string, subject: string, body: string, queue: boolean) => apiFetch<JCommission>(`/journal/commissions/${id}/mail`, { method: "PUT", body: JSON.stringify({ subject, body, queue }) });
export const jManuscript = (id: string) => apiFetch<JManuscript>(`/journal/manuscripts/${id}`);
export const jFormatReview = (id: string, result: "ok" | "needs_fix", note?: string) => apiFetch<JManuscript>(`/journal/manuscripts/${id}/format-review`, { method: "POST", body: JSON.stringify({ result, note }) });
export const jReviewerCandidates = () => apiFetch<{ id: string; display_name: string; role: string; external: boolean }[]>("/journal/reviewer-candidates");
export const jAssign = (id: string, body: Record<string, unknown>) => apiFetch<JAssignment & { warnings: string[] }>(`/journal/manuscripts/${id}/assignments`, { method: "POST", body: JSON.stringify(body) });
export const jAddComment = (id: string, body: Record<string, unknown>) => apiFetch<JComment>(`/journal/manuscripts/${id}/comments`, { method: "POST", body: JSON.stringify(body) });
export const jResolve = (id: string, cid: string) => apiFetch<JComment>(`/journal/manuscripts/${id}/comments/${cid}/resolve`, { method: "POST" });
export const jRequestRevision = (id: string, note?: string) => apiFetch<JManuscript>(`/journal/manuscripts/${id}/request-revision`, { method: "POST", body: JSON.stringify({ note }) });
export const jDeliberate = (id: string) => apiFetch<JManuscript>(`/journal/manuscripts/${id}/deliberate`, { method: "POST" });
export const jDecide = (id: string, outcome: string, note?: string) => apiFetch<JManuscript>(`/journal/manuscripts/${id}/decision`, { method: "POST", body: JSON.stringify({ outcome, note }) });
export const jCompare = (id: string, from: number, to: number) => apiFetch<JCompare>(`/journal/manuscripts/${id}/compare?from=${from}&to=${to}`);
export const jConfirmProof = (id: string, checklist: Record<string, boolean>) => apiFetch<JManuscript>(`/journal/manuscripts/${id}/proof/confirm`, { method: "POST", body: JSON.stringify({ checklist }) });
export const jConfirmPlagiarism = (id: string, pid: string) => apiFetch<unknown>(`/journal/manuscripts/${id}/plagiarism/${pid}/confirm`, { method: "POST" });
export const jSettings = () => apiFetch<Record<string, unknown>>("/journal/settings");
export const jPatchSettings = (body: Record<string, unknown>) => apiFetch<Record<string, unknown>>("/journal/settings", { method: "PATCH", body: JSON.stringify(body) });

// ---- 포털(외부 저자·검토자) ----
export interface PCommission {
  id: string; issue_label: string; topic: string; purpose: string | null; outline: string | null; length_spec: string | null; format_spec: string | null;
  due_date: string | null; delivery_method: string | null; contact_info: string | null; status: string; status_label: string; manuscript_id: string | null;
  manuscript_status: string | null; can_respond: boolean; can_submit: boolean;
}
export interface PReview extends JAssignment { title: string; manuscript_status: string; issue_label: string }
export const pCommissions = () => apiFetch<PCommission[]>("/journal/portal/author/commissions");
export const pRespond = (id: string, response: "accept" | "decline", note?: string) => apiFetch<PCommission>(`/journal/portal/author/commissions/${id}/respond`, { method: "POST", body: JSON.stringify({ response, note }) });
export const pManuscripts = () => apiFetch<{ id: string; title: string; issue_label: string; status: string; status_label: string; version_count: number }[]>("/journal/portal/author/manuscripts");
export const pManuscript = (id: string) => apiFetch<JManuscript>(`/journal/portal/author/manuscripts/${id}`);
export const pReply = (id: string, cid: string, text: string) => apiFetch<JComment>(`/journal/portal/author/manuscripts/${id}/comments/${cid}/reply`, { method: "POST", body: JSON.stringify({ text }) });
export const pReviews = () => apiFetch<PReview[]>("/journal/portal/reviews");
export interface PReviewDetail {
  assignment: JAssignment; manuscript: { id: string; title: string; title_en: string | null; summary: string | null; authors: { name: string; affiliation: string }[];
    status: string; status_label: string; references_text: string | null; issue_label: string };
  versions: { id: string; version_no: number; kind: string; file_name: string; uploaded_at: string; note: string | null; words: number | null }[];
  comments: JComment[]; outcomes: { key: string; label: string }[]; notice: string;
}
export const pReviewDetail = (aid: string) => apiFetch<PReviewDetail>(`/journal/portal/reviews/${aid}`);
export const pConflict = (aid: string, declared: boolean, note?: string) => apiFetch<PReviewDetail>(`/journal/portal/reviews/${aid}/conflict`, { method: "POST", body: JSON.stringify({ declared, note }) });
export const pReviewComment = (aid: string, body: Record<string, unknown>) => apiFetch<JComment>(`/journal/portal/reviews/${aid}/comments`, { method: "POST", body: JSON.stringify(body) });
export const pReviewResolve = (aid: string, cid: string) => apiFetch<JComment>(`/journal/portal/reviews/${aid}/comments/${cid}/resolve`, { method: "POST" });
export const pReviewComplete = (aid: string, recommendation: string, summary_opinion: string) => apiFetch<PReviewDetail>(`/journal/portal/reviews/${aid}/complete`, { method: "POST", body: JSON.stringify({ recommendation, summary_opinion }) });

// ---- 파일 업로드·다운로드(FormData/Blob) ----
function csrf(): string | null {
  const m = typeof document === "undefined" ? null : document.cookie.match(/(?:^|; )csrf_token=([^;]*)/);
  return m ? decodeURIComponent(m[1]) : null;
}

export async function uploadForm<T>(path: string, form: FormData, method = "POST"): Promise<T> {
  const headers = new Headers();
  const token = csrf();
  if (token) headers.set("x-csrf-token", token);
  const res = await fetch(`${API_BASE}${path}`, { method, body: form, headers, credentials: "include" });
  if (res.status === 401) throw new UnauthorizedError("로그인이 필요합니다");
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    const d = body.detail;
    throw new Error(typeof d === "string" ? d : d?.message ?? `요청 실패 (${res.status})`);
  }
  return res.json() as Promise<T>;
}

export async function downloadFile(path: string, fallbackName: string): Promise<void> {
  const res = await fetch(`${API_BASE}${path}`, { credentials: "include" });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(typeof body.detail === "string" ? body.detail : `다운로드 실패 (${res.status})`);
  }
  const blob = await res.blob();
  const cd = res.headers.get("content-disposition") ?? "";
  const m = cd.match(/filename\*=UTF-8''([^;]+)/);
  const name = m ? decodeURIComponent(m[1]) : fallbackName;
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 5000);
}

export const fileUrl = (path: string) => `${API_BASE}${path}`;

export const jCreateAuthorAccount = (body: { email: string; display_name: string; password: string; expert_id: string }) =>
  apiFetch<{ id: string; email: string }>("/journal/accounts/author", { method: "POST", body: JSON.stringify(body) });
export const jCreateReviewerAccount = (body: { email: string; display_name: string; password: string }) =>
  apiFetch<{ id: string; email: string }>("/journal/accounts/reviewer", { method: "POST", body: JSON.stringify(body) });
