const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const TOKEN_KEY = "tnp_access_token";

export function saveToken(token: string) {
  if (typeof window !== "undefined") localStorage.setItem(TOKEN_KEY, token);
}

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function clearToken() {
  if (typeof window !== "undefined") localStorage.removeItem(TOKEN_KEY);
}

export async function apiFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers = new Headers(options.headers);
  headers.set("Content-Type", "application/json");
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(body.detail ?? `요청 실패 (${res.status})`);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export type CandidateStatus = "rec" | "review" | "hold" | "final" | "rejected";

export interface Candidate {
  id: string;
  field_code: string;
  title: string;
  summary: string | null;
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

export interface CandidateDetail extends Candidate {
  reviews: CandidateReview[];
}

export interface CurrentUser {
  id: string;
  email: string;
  display_name: string;
  role: "researcher" | "reviewer" | "approver" | "admin";
  job_title: string | null;
  is_active: boolean;
}
