"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { apiFetch, getToken, type Candidate } from "@/lib/api";

const FIELD_LABELS: Record<string, string> = {
  soc: "디지털사회혁신",
  net: "통신·네트워크",
  bcast: "방송·전파·위성",
  sw: "SW·자율주행",
  ai: "인공지능·데이터",
  content: "콘텐츠·미디어",
  sec: "보안·블록체인",
  semi: "반도체·양자",
  conv: "ICT 융합기술",
};

const STATUS_LABELS: Record<string, string> = {
  rec: "추천",
  review: "검토중",
  hold: "보류",
  final: "확정",
  rejected: "반려",
};

export default function CandidatesPage() {
  const router = useRouter();
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!getToken()) {
      router.push("/login");
      return;
    }
    apiFetch<Candidate[]>("/candidates")
      .then(setCandidates)
      .catch((err) => setError(err instanceof Error ? err.message : "불러오기 실패"))
      .finally(() => setLoading(false));
  }, [router]);

  return (
    <div style={{ maxWidth: 960, margin: "0 auto", padding: 32 }}>
      <h1 style={{ fontSize: 20, fontWeight: 700 }}>주간 후보주제 목록</h1>
      <p style={{ color: "var(--ink-muted)", fontSize: 13.5 }}>
        실제 PostgreSQL에 저장된 후보주제 — 새로고침해도 사라지지 않습니다.
      </p>
      {loading && <p>불러오는 중...</p>}
      {error && <p style={{ color: "var(--bad)" }}>{error}</p>}
      <div className="panel" style={{ padding: 0, overflow: "hidden" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13.5 }}>
          <thead>
            <tr style={{ textAlign: "left", background: "var(--panel-2)" }}>
              <th style={{ padding: "10px 14px" }}>분야</th>
              <th style={{ padding: "10px 14px" }}>제목</th>
              <th style={{ padding: "10px 14px" }}>상태</th>
            </tr>
          </thead>
          <tbody>
            {candidates.map((c) => (
              <tr key={c.id} style={{ borderTop: "1px solid var(--border)" }}>
                <td style={{ padding: "10px 14px" }}>{FIELD_LABELS[c.field_code] ?? c.field_code}</td>
                <td style={{ padding: "10px 14px" }}>
                  <Link href={`/candidates/${c.id}`}>{c.title}</Link>
                </td>
                <td style={{ padding: "10px 14px" }}>
                  <span className={`pill ${c.status}`}>{STATUS_LABELS[c.status] ?? c.status}</span>
                </td>
              </tr>
            ))}
            {!loading && candidates.length === 0 && (
              <tr>
                <td colSpan={3} style={{ padding: 20, textAlign: "center", color: "var(--ink-muted)" }}>
                  등록된 후보주제가 없습니다
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
