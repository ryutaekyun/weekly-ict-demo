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
    throw new Error(body.detail ?? `요청 실패 (${res.status})`);
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
