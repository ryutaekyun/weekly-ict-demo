import { apiFetch } from "@/lib/api";

// ---- Phase 3-3.1: 후속 규정 알림 ------------------------------------------
export interface FollowupChange { item: string; old: string; new: string }
export interface FollowupNotice {
  id: string; title: string; original_doc_number: string; original_url: string | null;
  followup_doc_number: string | null; followup_url: string; followup_org: string | null;
  followup_published_at: string | null; followup_effective_on: string | null; change_summary: string;
  changes: FollowupChange[]; is_pilot: boolean; created_at: string;
}
export interface FollowupImpactRow { id: string; title: string | null; acked: boolean; resolution: string | null; note: string | null; acked_at: string | null }
export type FollowupImpact = Record<"manuscript" | "report" | "card_news", FollowupImpactRow[]>;
export type FollowupEntity = "manuscript" | "report" | "card_news";

export const listFollowups = () => apiFetch<(FollowupNotice & { open_count: number; affected_count: number })[]>("/followups");
export const getFollowup = (id: string) => apiFetch<FollowupNotice & { impact: FollowupImpact }>(`/followups/${id}`);
export const followupsFor = (type: FollowupEntity, id: string) => apiFetch<{ open: FollowupNotice[] }>(`/followups/for/${type}/${id}`);
export const createFollowup = (payload: {
  title: string; original_doc_number: string; followup_url: string; followup_doc_number?: string; followup_org?: string;
  followup_effective_on?: string; change_summary: string; changes: FollowupChange[];
}) => apiFetch<FollowupNotice & { impact: FollowupImpact }>("/followups", { method: "POST", body: JSON.stringify(payload) });
export const ackFollowup = (noticeId: string, payload: { entity_type: FollowupEntity; entity_id: string; resolution: "updated" | "no_change"; note: string }) =>
  apiFetch<FollowupNotice & { impact: FollowupImpact }>(`/followups/${noticeId}/ack`, { method: "POST", body: JSON.stringify(payload) });
export const detectFollowups = () => apiFetch<{ candidates: Record<string, string | null>[] }>("/followups/detect", { method: "POST" });
