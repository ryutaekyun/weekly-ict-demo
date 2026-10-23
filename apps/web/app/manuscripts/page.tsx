"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import AppShell from "@/components/AppShell";
import { listManuscripts, type ManuscriptListItem } from "@/lib/api";
import { fmtDate } from "@/lib/labels";

const STATUS_LABELS: Record<string, string> = {
  draft: "초안", review_requested: "검토 요청됨", changes_requested: "수정 요청됨", approved: "내부 확정", final: "최종",
};

export default function ManuscriptsListPage() {
  const [items, setItems] = useState<ManuscriptListItem[]>([]);
  const [statusFilter, setStatusFilter] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    listManuscripts({ status_filter: statusFilter || undefined })
      .then(setItems)
      .finally(() => setLoading(false));
  }, [statusFilter]);

  return (
    <AppShell>
      <h1 style={{ fontSize: 20, fontWeight: 700, marginBottom: 4 }}>연구·집필 작업실</h1>
      <p style={{ color: "var(--ink-muted)", fontSize: 13, marginTop: 0 }}>
        후보주제 상세화면의 &ldquo;원고 작성 시작&rdquo; 버튼으로 새 원고를 만들 수 있습니다.
      </p>
      <div className="panel" style={{ display: "flex", gap: 10, marginBottom: 14, alignItems: "center" }}>
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} style={{ padding: 7, borderRadius: 8, border: "1px solid var(--border)" }}>
          <option value="">전체 상태</option>
          {Object.entries(STATUS_LABELS).map(([c, l]) => <option key={c} value={c}>{l}</option>)}
        </select>
        <span style={{ marginLeft: "auto", fontSize: 13, color: "var(--ink-muted)" }}>총 {items.length}건</span>
      </div>
      {loading && <p style={{ color: "var(--ink-muted)" }}>불러오는 중...</p>}
      <div className="panel" style={{ padding: 0, overflow: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
          <thead>
            <tr style={{ textAlign: "left", background: "var(--panel-2)" }}>
              <th style={{ padding: "9px 12px" }}>제목</th>
              <th style={{ padding: "9px 12px" }}>유형</th>
              <th style={{ padding: "9px 12px" }}>상태</th>
              <th style={{ padding: "9px 12px" }}>IITP</th>
              <th style={{ padding: "9px 12px" }}>수정일</th>
            </tr>
          </thead>
          <tbody>
            {items.map((m) => (
              <tr key={m.id} style={{ borderTop: "1px solid var(--border)" }}>
                <td style={{ padding: "9px 12px" }}>
                  <Link href={`/manuscripts/${m.id}`}>{m.title}</Link>
                  {m.is_pilot && <span className="pill hold" style={{ marginLeft: 6 }}>시범</span>}
                </td>
                <td style={{ padding: "9px 12px" }}>{m.manuscript_type}</td>
                <td style={{ padding: "9px 12px" }}>{STATUS_LABELS[m.status] ?? m.status}</td>
                <td style={{ padding: "9px 12px" }}>{m.iitp_selection_status}</td>
                <td style={{ padding: "9px 12px" }}>{fmtDate(m.updated_at)}</td>
              </tr>
            ))}
            {!loading && items.length === 0 && (
              <tr><td colSpan={5} style={{ padding: 20, textAlign: "center", color: "var(--ink-muted)" }}>작성 중인 원고가 없습니다</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </AppShell>
  );
}
