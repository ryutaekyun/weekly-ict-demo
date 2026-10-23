"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import AppShell from "@/components/AppShell";
import { listCandidates, UnauthorizedError, type Candidate } from "@/lib/api";
import { CANDIDATE_STATUS_LABELS, FIELD_LABELS, fmtDateOnly } from "@/lib/labels";
import { useRouter } from "next/navigation";

export default function CandidatesPage() {
  const router = useRouter();
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [fieldCode, setFieldCode] = useState("");
  const [status, setStatus] = useState("");
  const [q, setQ] = useState("");

  useEffect(() => {
    setLoading(true);
    listCandidates({ field_code: fieldCode || undefined, status: status || undefined, q: q || undefined })
      .then(setCandidates)
      .catch((err) => {
        if (err instanceof UnauthorizedError) { router.push("/login"); return; }
        setError(err instanceof Error ? err.message : "불러오기 실패");
      })
      .finally(() => setLoading(false));
  }, [fieldCode, status, q, router]);

  return (
    <AppShell>
      <h1 style={{ fontSize: 20, fontWeight: 700, marginBottom: 4 }}>후보주제 선정·검토</h1>
      <p style={{ color: "var(--ink-muted)", fontSize: 13, marginTop: 0 }}>
        AI/규칙 기반 추천과 기존 후보주제 CRUD를 한 화면에서 다룹니다. 최종 주제 선정은 연구원·PM 승인을 거칩니다.
      </p>

      <div className="panel" style={{ display: "flex", flexWrap: "wrap", gap: 10, marginBottom: 14, alignItems: "center" }}>
        <select value={fieldCode} onChange={(e) => setFieldCode(e.target.value)} style={selectStyle}>
          <option value="">전체 분야</option>
          {Object.entries(FIELD_LABELS).map(([c, l]) => <option key={c} value={c}>{l}</option>)}
        </select>
        <select value={status} onChange={(e) => setStatus(e.target.value)} style={selectStyle}>
          <option value="">전체 검토상태</option>
          {Object.entries(CANDIDATE_STATUS_LABELS).map(([c, l]) => <option key={c} value={c}>{l}</option>)}
        </select>
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="제목 검색" style={{ ...selectStyle, minWidth: 200 }} />
        <span style={{ marginLeft: "auto", fontSize: 13, color: "var(--ink-muted)" }}>총 {candidates.length}건</span>
      </div>

      {error && <p style={{ color: "var(--bad)" }}>{error}</p>}
      {loading && <p style={{ color: "var(--ink-muted)" }}>불러오는 중...</p>}

      <div className="panel" style={{ padding: 0, overflow: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13.5 }}>
          <thead>
            <tr style={{ textAlign: "left", background: "var(--panel-2)" }}>
              <th style={th}>분야</th>
              <th style={th}>제목</th>
              <th style={th}>발표일</th>
              <th style={th}>출처</th>
              <th style={th}>상태</th>
            </tr>
          </thead>
          <tbody>
            {candidates.map((c) => (
              <tr key={c.id} style={{ borderTop: "1px solid var(--border)" }}>
                <td style={td}>{FIELD_LABELS[c.field_code] ?? c.field_code}</td>
                <td style={td}><Link href={`/candidates/${c.id}`}>{c.title}</Link></td>
                <td style={td}>{fmtDateOnly(c.announced_date)}</td>
                <td style={td}>{c.source_org ?? "-"}</td>
                <td style={td}>
                  <span className={`pill ${c.status}`}>{CANDIDATE_STATUS_LABELS[c.status] ?? c.status}</span>
                </td>
              </tr>
            ))}
            {!loading && candidates.length === 0 && (
              <tr><td colSpan={5} style={{ padding: 20, textAlign: "center", color: "var(--ink-muted)" }}>등록된 후보주제가 없습니다</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </AppShell>
  );
}

const selectStyle: React.CSSProperties = { padding: "7px 9px", borderRadius: 8, border: "1px solid var(--border)", fontSize: 13 };
const th: React.CSSProperties = { padding: "9px 14px" };
const td: React.CSSProperties = { padding: "9px 14px" };
