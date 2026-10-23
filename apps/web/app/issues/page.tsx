"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import AppShell from "@/components/AppShell";
import { listIssues, type IssueClusterOut } from "@/lib/api";
import { CLUSTER_REVIEW_LABELS, FIELD_LABELS, fmtDateOnly } from "@/lib/labels";

export default function IssuesPage() {
  const [issues, setIssues] = useState<IssueClusterOut[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [fieldCode, setFieldCode] = useState("");
  const [reviewStatus, setReviewStatus] = useState("");
  const [multiOnly, setMultiOnly] = useState(false);
  const [q, setQ] = useState("");

  useEffect(() => {
    setLoading(true);
    listIssues({ field_code: fieldCode || undefined })
      .then(setIssues)
      .catch((err) => setError(err instanceof Error ? err.message : "불러오기 실패"))
      .finally(() => setLoading(false));
  }, [fieldCode]);

  const filtered = useMemo(() => {
    return issues.filter((i) => {
      if (reviewStatus && i.review_status !== reviewStatus) return false;
      if (multiOnly && i.document_count < 2) return false;
      if (q && !i.title.toLowerCase().includes(q.toLowerCase())) return false;
      return true;
    });
  }, [issues, reviewStatus, multiOnly, q]);

  const needsReviewCount = issues.filter((i) => i.review_status === "needs_review").length;

  return (
    <AppShell>
      <h1 style={{ fontSize: 20, fontWeight: 700, marginBottom: 4 }}>핵심 이슈 분석</h1>
      <p style={{ color: "var(--ink-muted)", fontSize: 13, marginTop: 0 }}>
        동일 사건을 다룬 여러 원문을 하나의 이슈로 통합한 결과입니다. 통합 여부가 불확실한 건은 자동 확정하지 않고 검토대기로 남겨둡니다.
      </p>

      {needsReviewCount > 0 && (
        <div className="panel" style={{ marginBottom: 14, background: "var(--warn-soft)", color: "var(--warn)", fontSize: 13, fontWeight: 700 }}>
          이슈 통합 검토대기 {needsReviewCount}건 — <button className="tbtn" style={{ marginLeft: 8 }} onClick={() => setReviewStatus("needs_review")}>검토대기만 보기</button>
        </div>
      )}

      <div className="panel" style={{ display: "flex", flexWrap: "wrap", gap: 10, marginBottom: 14, alignItems: "center" }}>
        <select value={fieldCode} onChange={(e) => setFieldCode(e.target.value)} style={selectStyle}>
          <option value="">전체 분야</option>
          {Object.entries(FIELD_LABELS).map(([c, l]) => <option key={c} value={c}>{l}</option>)}
        </select>
        <select value={reviewStatus} onChange={(e) => setReviewStatus(e.target.value)} style={selectStyle}>
          <option value="">전체 통합상태</option>
          {Object.entries(CLUSTER_REVIEW_LABELS).map(([c, l]) => <option key={c} value={c}>{l}</option>)}
        </select>
        <label style={{ fontSize: 13, display: "flex", alignItems: "center", gap: 6 }}>
          <input type="checkbox" checked={multiOnly} onChange={(e) => setMultiOnly(e.target.checked)} />
          복수 문서 이슈만
        </label>
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="이슈 제목 검색" style={{ ...selectStyle, minWidth: 200 }} />
        <span style={{ marginLeft: "auto", fontSize: 13, color: "var(--ink-muted)" }}>총 {filtered.length}건</span>
      </div>

      {error && <p style={{ color: "var(--bad)" }}>{error}</p>}
      {loading && <p style={{ color: "var(--ink-muted)" }}>불러오는 중...</p>}

      <div className="panel" style={{ padding: 0, overflow: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
          <thead>
            <tr style={{ textAlign: "left", background: "var(--panel-2)" }}>
              <th style={th}>이슈 제목</th>
              <th style={th}>분야</th>
              <th style={th}>관련 문서수</th>
              <th style={th}>최초 발표일</th>
              <th style={th}>최근 활동</th>
              <th style={th}>통합 상태</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((i) => (
              <tr key={i.id} style={{ borderTop: "1px solid var(--border)" }}>
                <td style={td}><Link href={`/issues/${i.id}`}>{i.title}</Link></td>
                <td style={td}>{FIELD_LABELS[i.field_code] ?? i.field_code}</td>
                <td style={td}>{i.document_count}{i.document_count > 1 ? " (복수)" : ""}</td>
                <td style={td}>{fmtDateOnly(i.first_seen_at)}</td>
                <td style={td}>{fmtDateOnly(i.last_activity_at)}</td>
                <td style={td}>
                  <span className={`pill ${i.review_status === "confirmed" ? "rec" : "hold"}`}>
                    {CLUSTER_REVIEW_LABELS[i.review_status] ?? i.review_status}
                  </span>
                </td>
              </tr>
            ))}
            {!loading && filtered.length === 0 && (
              <tr><td colSpan={6} style={{ padding: 20, textAlign: "center", color: "var(--ink-muted)" }}>조건에 맞는 이슈가 없습니다</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </AppShell>
  );
}

const selectStyle: React.CSSProperties = { padding: "7px 9px", borderRadius: 8, border: "1px solid var(--border)", fontSize: 13 };
const th: React.CSSProperties = { padding: "9px 12px", whiteSpace: "nowrap" };
const td: React.CSSProperties = { padding: "9px 12px" };
