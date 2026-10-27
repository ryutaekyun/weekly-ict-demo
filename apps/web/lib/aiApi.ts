import { apiFetch } from "@/lib/api";

export type AiKind = "document" | "issue" | "candidate" | "outline" | "draft";

export type AiStatus = {
  configured: boolean; provider: string | null; model: string | null; is_mock: boolean;
  daily_limit_per_user: number; message: string | null;
  connection: "not_configured" | "unverified" | "mock"; connection_note: string; config_gaps: string[];
};

export type AiEstimate = {
  kind: AiKind; documents: { id: string; title: string; org: string | null; country: string | null; published: string | null; chars: number; truncated: boolean }[];
  skipped: string[]; input_chars: number; est_input_tokens: number; est_output_tokens: number; est_cost_usd: number | null; pricing_version: string | null; price_known: boolean;
  provider: string; model: string | null; configured: boolean; is_mock: boolean; blockers: string[]; existing_candidate_ids: string[]; price_note: string;
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
