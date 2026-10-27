import { apiFetch } from "@/lib/api";

export type AiKind = "document" | "issue" | "candidate" | "outline" | "draft";

export type AiStatus = {
  configured: boolean; provider: string | null; model: string | null; is_mock: boolean;
  daily_limit_per_user: number; message: string | null;
  connection: "not_configured" | "unverified" | "mock"; connection_note: string; config_gaps: string[];
  require_approval: boolean; max_cost_per_request_usd: number | null;
};

export type AiEstimate = {
  kind: AiKind; documents: { id: string; title: string; org: string | null; country: string | null; published: string | null; chars: number; truncated: boolean }[];
  skipped: string[]; input_chars: number; est_input_tokens: number; est_output_tokens: number; est_cost_usd: number | null; max_cost_usd: number | null; max_output_tokens: number; pricing_version: string | null; price_known: boolean;
  provider: string; model: string | null; configured: boolean; is_mock: boolean; blockers: string[]; existing_candidate_ids: string[]; price_note: string;
  approval_required: boolean; approval: AiApproval | null; max_cost_per_request_usd: number | null;
};

export type AiEvidence = { document_id: string | null; url: string; title: string | null; quote: string; found: boolean; location: string | null; note: string };

export type AiClaim = {
  id: string; section_key: string; seq: number; text: string; claim_type: "fact" | "interpretation" | "gap";
  evidence: AiEvidence[]; evidence_status: "found" | "not_found" | "value_mismatch" | "semantic_risk" | "no_evidence" | "interpretation" | "gap";
  check_note: string | null; researcher_status: "unverified" | "verified" | "rejected"; researcher_note: string | null;
  verified_at: string | null; inserted_manuscript_id: string | null;
};

export type AiAnalysis = {
  id: string; kind: AiKind; target_id: string; status: "running" | "completed" | "failed" | "cancelled" | "insufficient_evidence";
  verification_status: "ai_unverified" | "insufficient" | "mismatch" | "researcher_verified";
  provider: string | null; model: string | null; is_mock: boolean; prompt_version: string; input_documents: { id: string; title: string; url: string; content_hash: string; published: string | null; truncated: boolean }[];
  input_tokens: number; output_tokens: number; est_cost_usd: number; actual_cost_usd: number | null; error_message: string | null; notes: string[];
  error_code: string | null; provider_request_sent: boolean; pricing_version: string | null; cancel_note: string | null; source_changed_during_run: boolean;
  started_at: string; finished_at: string | null; reused: boolean; hold_reason: string | null; linked_candidate_id: string | null; public_approved_at: string | null;
  stats: { total: number; semantic_risk: number; facts: number; facts_without_valid_evidence: number; ratio_without_valid_evidence: number; researcher_verified: number };
  notice: string; sections?: { key: string; title: string; claims: AiClaim[]; suppressed?: string }[]; model_notes?: string[];
};

export const aiStatus = () => apiFetch<AiStatus>("/ai/status");
export const aiEstimate = (kind: AiKind, target_id: string, document_ids?: string[]) =>
  apiFetch<AiEstimate>("/ai/estimate", { method: "POST", body: JSON.stringify({ kind, target_id, document_ids }) });
export const aiRun = (kind: AiKind, target_id: string, opts: { document_ids?: string[]; force?: boolean } = {}, signal?: AbortSignal) =>
  apiFetch<AiAnalysis>("/ai/analyses", { method: "POST", signal, body: JSON.stringify({ kind, target_id, confirm_cost: true, ...opts }) });
export const aiList = (target_id: string, kind?: AiKind) =>
  apiFetch<AiAnalysis[]>(`/ai/analyses?target_id=${target_id}${kind ? `&kind=${kind}` : ""}`);
export const aiGet = (id: string) => apiFetch<AiAnalysis>(`/ai/analyses/${id}`);
export const aiCancel = (id: string) => apiFetch<AiAnalysis>(`/ai/analyses/${id}/cancel`, { method: "POST" });
export const aiReviewClaim = (id: string, action: "verify" | "reject" | "reset", note?: string) =>
  apiFetch<{ claim: AiClaim; verification_status: AiAnalysis["verification_status"] }>(`/ai/claims/${id}/review`, { method: "POST", body: JSON.stringify({ action, note }) });
export const aiCandidate = (id: string, body: { title: string; summary?: string; recommended_reason?: string; attach_to_candidate_id?: string }) =>
  apiFetch<{ candidate_id: string; created: boolean }>(`/ai/analyses/${id}/candidate`, { method: "POST", body: JSON.stringify(body) });
export type InsertPosition = { mode: "end" } | { mode: "after_index"; index: number } | { mode: "after_heading"; heading_text: string };
export const aiInsert = (id: string, body: { manuscript_id: string; claim_ids: string[]; lock_version: number; edited_texts: Record<string, string>; position?: InsertPosition }) =>
  apiFetch<{ lock_version: number; inserted: number; footnotes_created: number; note: string; insertion_ids: string[] }>(`/ai/analyses/${id}/insert`, { method: "POST", body: JSON.stringify(body) });
export const aiPublicApprove = (id: string) => apiFetch<AiAnalysis>(`/ai/analyses/${id}/public-approval`, { method: "POST" });

export type InsertionChange = {
  current_hash: string; baseline_hash: string | null; old_quote: string; old_quote_still_in_source: boolean; new_sentence: string | null; similarity: number;
  removed_facts: string[]; added_facts: string[]; stale_in_sentence: string[];
  last_review: { resolution: string; note: string; reviewed_at: string | null } | null;
};
export type AiInsertionRow = {
  id: string; analysis_id: string; claim_id: string; footnote_mark_id: string | null; document_id: string | null; ai_text: string; final_text: string;
  edited_by_researcher: boolean; quote_at_insert: string | null; source_hash_at_insert: string | null; status: "active" | "undone" | "removed"; inserted_at: string;
  needs_review: boolean; change: InsertionChange | null;
  history: { resolution: string; label: string; note: string; reviewer_id: string; reviewed_at: string; reviewed_source_hash: string | null }[];
};
export const aiListInsertions = (manuscriptId: string) => apiFetch<AiInsertionRow[]>(`/ai/manuscripts/${manuscriptId}/insertions`);
export const aiReviewInsertion = (id: string, resolution: "updated" | "no_impact" | "needs_check" | "removed", note: string) =>
  apiFetch<AiInsertionRow>(`/ai/insertions/${id}/review`, { method: "POST", body: JSON.stringify({ resolution, note }) });
export const aiUndoInsertion = (id: string, lock_version: number) =>
  apiFetch<{ undone: boolean; lock_version: number }>(`/ai/insertions/${id}/undo`, { method: "POST", body: JSON.stringify({ lock_version }) });

export type AiUsage = {
  days: number; requests: number; by_status: Record<string, number>; provider_requests_sent: number; input_tokens: number; output_tokens: number;
  est_cost_usd: number; calculated_cost_usd: number; mock_requests: number; failed_or_cancelled: number; cost_note: string; daily_limit_per_user: number;
};
export const aiUsage = (scope: "me" | "all" = "me", days = 1) => apiFetch<AiUsage>(`/ai/usage?scope=${scope}&days=${days}`);
export type AiPrice = { id: string; provider: string; model: string; input_per_mtok: number; output_per_mtok: number; effective_date: string; source_note: string | null; version: number; is_active: boolean };
export const aiPricing = () => apiFetch<AiPrice[]>("/ai/pricing");
export const aiSetPricing = (body: { provider: string; model: string; input_per_mtok: number; output_per_mtok: number; effective_date: string; source_note?: string }) =>
  apiFetch<{ id: string; version: number }>("/ai/pricing", { method: "PUT", body: JSON.stringify(body) });
export type AiDiagnostics = { connection: string; verified: boolean; message: string; model?: string; error_code?: string; available_models?: string[] };
export const aiDiagnostics = () => apiFetch<AiDiagnostics>("/ai/diagnostics", { method: "POST" });

export type AiApproval = { id: string; kind: AiKind; target_id: string; model: string; max_cost_usd: number; note: string | null; expires_at: string; used_at: string | null; used_analysis_id: string | null; revoked: boolean };
export const aiCreateApproval = (body: { kind: AiKind; target_id: string; max_cost_usd: number; valid_minutes: number; note?: string }) =>
  apiFetch<AiApproval>("/ai/approvals", { method: "POST", body: JSON.stringify(body) });
export const aiApprovals = () => apiFetch<AiApproval[]>("/ai/approvals");
export const aiRevokeApproval = (id: string) => apiFetch<AiApproval>(`/ai/approvals/${id}`, { method: "DELETE" });

export const EVAL_CRITERIA: Record<string, string> = {
  c1_summary: "① 원문의 핵심 내용이 정확하게 요약되었는가", c2_values: "② 날짜·수치·단위·적용대상이 정확한가", c3_followup: "③ 기존 정책과 후속 변경사항을 구분하는가",
  c4_evidence: "④ 모든 핵심 사실에 실제 원문 근거가 있는가", c5_no_invention: "⑤ 원문에 없는 논쟁·국가별 입장을 만들지 않는가",
  c6_domestic: "⑥ 국내 산업 영향과 추가 검토 필요 사항을 구분하는가", c7_usable: "⑦ 작성된 문장을 실제 보고서 원고에 활용할 수 있는가",
};
export const aiSaveEvaluation = (id: string, body: { scores: Record<string, string>; semantic_mismatch_cases: number; insufficient_evidence_cases: number; wrong_source_cases: number; notes?: string }) =>
  apiFetch<{ id: string; is_mock: boolean }>(`/ai/analyses/${id}/evaluation`, { method: "POST", body: JSON.stringify(body) });
export type EvalGroup = { evaluations: number; criteria: Record<string, Record<string, number>>; facts: number; facts_without_valid_evidence: number; ratio_without_valid_evidence: number | null;
  semantic_mismatch_cases: number; insufficient_evidence_cases: number; wrong_source_cases: number };
export const aiEvaluationSummary = () => apiFetch<{ real: EvalGroup; mock: EvalGroup; note: string }>("/ai/evaluation-summary");

export type AiPreflight = {
  provider: string; model: string; api_version: string | null; documents: { id: string; alias: string; title: string; url: string; published: string | null; content_hash: string; sent_chars: number; full_chars: number; truncated: boolean }[];
  prompt_sha256: string; request_top_level_keys: string[]; not_sent: string[]; max_tokens: number; input_tokens: number; input_tokens_measured: boolean; input_tokens_note: string;
  expected_cost_usd: number | null; max_cost_usd: number | null; recommended_approval_cap_usd: number | null; pricing_version: string | null; approval_required: boolean; connection: string; cost_note: string;
};
export const aiPreflight = (kind: AiKind, target_id: string, document_ids?: string[]) =>
  apiFetch<AiPreflight>("/ai/preflight", { method: "POST", body: JSON.stringify({ kind, target_id, document_ids }) });
