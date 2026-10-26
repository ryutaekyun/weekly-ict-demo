// Phase 3-3: 카드뉴스 API 클라이언트
import { apiFetch, UnauthorizedError } from "@/lib/api";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface CnEvidence {
  id: string; card_id: string; element_key: string; source_url: string; source_org: string | null; excerpt: string | null;
  original_footnote_status: string | null; verification_status: "not_verified" | "verified" | "stale";
  verified_at: string | null; source_manuscript_id: string | null;
}
export interface CnElement {
  key: string; label: string; type: "text" | "choice" | "chart"; max_chars: number; evidence_required: boolean; required: boolean;
  hint: string; options: Record<string, string>; multiline: boolean; text: string; data: Record<string, any> | null;
  style: { size?: number; color?: string; bold?: boolean; align?: string }; box: Record<string, number>; hidden: boolean;
  source_sentence: string | null; source_manuscript_id: string | null; source_stale: boolean;
  evidence_state: "n/a" | "none" | "not_verified" | "verified" | "stale";
  evidence_items: CnEvidence[];
}
export interface CnCard { id: string; position: number; kind: "cover" | "body" | "closing"; bg_color: string | null; elements: CnElement[] }
export interface CnIssue { level: "error" | "warn" | "info"; code: string; message: string; card_index: number | null; element_key: string | null }
export interface CardNewsDetail {
  id: string; title: string; template_key: "A" | "B" | "C" | "D"; template_name: string; width_cm: number; height_cm: number;
  status: string; lock_version: number; source_type: string; source_report_id: string | null; source_changed: boolean; needs_review: boolean;
  iitp_confirmed: boolean; iitp_note: string | null; is_pilot: boolean; is_synthetic: boolean; approve_exception_reason: string | null;
  reviewer_user_id: string | null; created_by_user_id: string; updated_at: string; cards: CnCard[]; preflight: CnIssue[]; blocking: CnIssue[];
  size_note: string;
}
export interface CardNewsListItem {
  id: string; title: string; template_key: string; status: string; is_pilot: boolean; is_synthetic: boolean; source_type: string; updated_at: string;
}
export interface CnScene { width: number; height: number; background: string; kind: string; layout: string; card_id: string; items: any[]; notes: string[] }
export interface CnTemplateInfo { key: string; name: string; purpose: string; version: number; config: Record<string, any> }
export interface CnExport {
  id: string; file_format: "pptx" | "png"; status: string; error_message: string | null; content_version: number;
  template_version: number | null; file_name: string | null; file_sha256: string | null; file_size: number | null;
  card_count: number | null; png_width_px: number | null; png_height_px: number | null; approval_state: string | null;
  validation_json: string | null; created_at: string;
}
export interface CnSentence {
  manuscript_id: string; manuscript_title: string; sentence: string; shown: string;
  footnotes: { id: string; source_org: string | null; source_url: string; status: string }[];
}
export interface CnVersion { id: string; version_no: number; change_note: string | null; is_milestone: boolean; created_at: string }
export interface CnReview { id: string; card_id: string | null; author_user_id: string; comment_text: string; status: string }

const json = (body: unknown) => JSON.stringify(body);
const P = (id: string) => `/card-news/${id}`;

// evidence 필드(백엔드) → evidence_items(프런트) 이름 정리
function normalize(d: any): CardNewsDetail {
  for (const card of d.cards ?? []) {
    for (const el of card.elements) el.evidence_items = el.evidence ?? [];
  }
  return d as CardNewsDetail;
}
const n = async (p: Promise<any>) => normalize(await p);

export const listCardNews = () => apiFetch<CardNewsListItem[]>("/card-news");
export const listCnTemplates = () => apiFetch<CnTemplateInfo[]>("/card-news/templates");
export const getCnReportSentences = (reportId: string) =>
  apiFetch<{ report_id: string; title: string; report_type: string; sentences: CnSentence[] }>(`/card-news/report-sentences/${reportId}`);
export const createCardNews = (payload: Record<string, unknown>) => n(apiFetch("/card-news", { method: "POST", body: json(payload) }));
export const getCardNews = (id: string) => n(apiFetch(P(id)));
export const getCnScenes = (id: string) => apiFetch<{ scenes: CnScene[] }>(`${P(id)}/scenes`);
export const patchCardNews = (id: string, body: Record<string, unknown>) => n(apiFetch(P(id), { method: "PATCH", body: json(body) }));
export const addCnCard = (id: string, body: Record<string, unknown>) => n(apiFetch(`${P(id)}/cards`, { method: "POST", body: json(body) }));
export const deleteCnCard = (id: string, cardId: string, lock: number) => n(apiFetch(`${P(id)}/cards/${cardId}?lock_version=${lock}`, { method: "DELETE" }));
export const duplicateCnCard = (id: string, cardId: string, lock: number) =>
  n(apiFetch(`${P(id)}/cards/${cardId}/duplicate`, { method: "POST", body: json({ lock_version: lock }) }));
export const reorderCnCards = (id: string, cardIds: string[], lock: number) =>
  n(apiFetch(`${P(id)}/cards/reorder`, { method: "POST", body: json({ card_ids: cardIds, lock_version: lock }) }));
export const patchCnCard = (id: string, cardId: string, body: Record<string, unknown>) =>
  n(apiFetch(`${P(id)}/cards/${cardId}`, { method: "PATCH", body: json(body) }));
export const patchCnElement = (id: string, cardId: string, key: string, body: Record<string, unknown>) =>
  n(apiFetch(`${P(id)}/cards/${cardId}/elements/${key}`, { method: "PATCH", body: json(body) }));
export const addCnEvidence = (id: string, cardId: string, body: Record<string, unknown>) =>
  n(apiFetch(`${P(id)}/cards/${cardId}/evidence`, { method: "POST", body: json(body) }));
export const verifyCnEvidence = (id: string, evidenceId: string, verified: boolean) =>
  n(apiFetch(`${P(id)}/evidence/${evidenceId}/verify`, { method: "POST", body: json({ verified }) }));
export const deleteCnEvidence = (id: string, evidenceId: string) => n(apiFetch(`${P(id)}/evidence/${evidenceId}`, { method: "DELETE" }));
export const listCnVersions = (id: string) => apiFetch<CnVersion[]>(`${P(id)}/versions`);
export const saveCnMilestone = (id: string, note?: string) => apiFetch<CnVersion[]>(`${P(id)}/versions`, { method: "POST", body: json({ change_note: note }) });
export const restoreCnVersion = (id: string, versionId: string, lock: number) =>
  n(apiFetch(`${P(id)}/versions/${versionId}/restore`, { method: "POST", body: json({ lock_version: lock }) }));
export const listCnReviews = (id: string) => apiFetch<CnReview[]>(`${P(id)}/reviews`);
export const addCnReview = (id: string, body: { comment_text: string; card_id?: string }) =>
  apiFetch<CnReview[]>(`${P(id)}/reviews`, { method: "POST", body: json(body) });
export const resolveCnReview = (id: string, rid: string) => apiFetch<CnReview[]>(`${P(id)}/reviews/${rid}/resolve`, { method: "POST" });
export const requestCnReview = (id: string, reviewerId?: string) =>
  n(apiFetch(`${P(id)}/request-review`, { method: "POST", body: json({ reviewer_user_id: reviewerId || null }) }));
export const requestCnChanges = (id: string, text: string) => n(apiFetch(`${P(id)}/request-changes`, { method: "POST", body: json({ comment_text: text }) }));
export const approveCn = (id: string, reason?: string) => n(apiFetch(`${P(id)}/approve`, { method: "POST", body: json({ exception_reason: reason || null }) }));
export const reopenCn = (id: string) => n(apiFetch(`${P(id)}/reopen`, { method: "POST" }));
export const duplicateCn = (id: string) => n(apiFetch(`${P(id)}/duplicate`, { method: "POST" }));
export const setCnIitp = (id: string, confirmed: boolean, note?: string) => n(apiFetch(`${P(id)}/iitp`, { method: "PATCH", body: json({ confirmed, note }) }));
export const listCnExports = (id: string) => apiFetch<CnExport[]>(`${P(id)}/exports`);
export const createCnExport = (id: string, fileFormat: "pptx" | "png", shortPx = 1000) =>
  apiFetch<CnExport>(`${P(id)}/exports`, { method: "POST", body: json({ file_format: fileFormat, short_px: shortPx }) });

/** 인증 쿠키로 출력 파일(PPTX·ZIP·카드별 PNG)을 받아 Blob으로 돌려준다. */
export async function fetchCnBlob(path: string): Promise<Blob> {
  const res = await fetch(`${API_BASE}${path}`, { credentials: "include" });
  if (res.status === 401) throw new UnauthorizedError("로그인이 필요합니다");
  if (!res.ok) throw new Error("파일을 내려받을 수 없습니다");
  return res.blob();
}
