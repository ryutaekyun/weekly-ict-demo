"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import AppShell from "@/components/AppShell";
import { createReport, listReports, type ReportListItem } from "@/lib/api";
import { fmtDate, REPORT_STATUS_LABELS, REPORT_TYPE_LABELS } from "@/lib/labels";

export default function ReportsPage() {
  const router = useRouter();
  const [items, setItems] = useState<ReportListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [reportType, setReportType] = useState("general");
  const [title, setTitle] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    listReports().then(setItems).finally(() => setLoading(false));
  }, []);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!title.trim()) { setError("보고서 제목을 입력하세요"); return; }
    setCreating(true);
    setError(null);
    try {
      const created = await createReport({ report_type: reportType, title: title.trim() });
      router.push(`/reports/${created.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "보고서 생성 실패");
      setCreating(false);
    }
  }

  return (
    <AppShell>
      <h1 style={{ fontSize: 20, fontWeight: 700, marginBottom: 4 }}>보고서·요약본 제작</h1>
      <p style={{ color: "var(--ink-muted)", fontSize: 13, marginTop: 0 }}>
        연구·집필 작업실에서 작성한 원고를 일반호·특집호 보고서와 요약본으로 구성하고, 편집 가능한 DOCX와 배포용 PDF로 출력합니다.
        출력본은 <b>내부 검토용 초안</b>이며 IITP 공식 확인과는 별개입니다.
      </p>

      <form className="panel" onSubmit={handleCreate} style={{ display: "flex", gap: 10, alignItems: "center", marginBottom: 14, flexWrap: "wrap" }}>
        <select aria-label="보고서 유형" value={reportType} onChange={(e) => setReportType(e.target.value)} style={{ padding: 7, borderRadius: 8, border: "1px solid var(--border)" }}>
          {Object.entries(REPORT_TYPE_LABELS).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
        </select>
        <input aria-label="보고서 제목" placeholder="보고서 제목" value={title} onChange={(e) => setTitle(e.target.value)} style={{ flex: 1, minWidth: 240, padding: 8, borderRadius: 8, border: "1px solid var(--border)" }} />
        <button className="tbtn primary" type="submit" disabled={creating}>{creating ? "생성 중..." : "새 보고서 만들기"}</button>
        {error && <span role="alert" style={{ color: "var(--danger, #b42318)", fontSize: 12.5 }}>{error}</span>}
      </form>

      {loading && <p style={{ color: "var(--ink-muted)" }}>불러오는 중...</p>}
      <div className="panel" style={{ padding: 0, overflow: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
          <thead>
            <tr style={{ textAlign: "left", background: "var(--panel-2)" }}>
              <th style={{ padding: "9px 12px" }}>제목</th>
              <th style={{ padding: "9px 12px" }}>유형</th>
              <th style={{ padding: "9px 12px" }}>상태</th>
              <th style={{ padding: "9px 12px" }}>수정일</th>
            </tr>
          </thead>
          <tbody>
            {items.map((r) => (
              <tr key={r.id} style={{ borderTop: "1px solid var(--border)" }}>
                <td style={{ padding: "9px 12px" }}><Link href={`/reports/${r.id}`}>{r.title}</Link></td>
                <td style={{ padding: "9px 12px" }}>{REPORT_TYPE_LABELS[r.report_type] ?? r.report_type}</td>
                <td style={{ padding: "9px 12px" }}>{REPORT_STATUS_LABELS[r.status] ?? r.status}</td>
                <td style={{ padding: "9px 12px" }}>{fmtDate(r.updated_at)}</td>
              </tr>
            ))}
            {!loading && items.length === 0 && (
              <tr><td colSpan={4} style={{ padding: 20, textAlign: "center", color: "var(--ink-muted)" }}>만든 보고서가 없습니다</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </AppShell>
  );
}
