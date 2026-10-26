"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import AppShell from "@/components/AppShell";
import { getDashboardSummary, type DashboardSummary } from "@/lib/api";
import { CANDIDATE_STATUS_LABELS, FIELD_LABELS, fmtDate } from "@/lib/labels";

function StatCard({ label, value, hint, tone }: { label: string; value: number | string; hint?: string; tone?: "warn" | "bad" }) {
  const color = tone === "bad" ? "var(--bad)" : tone === "warn" ? "var(--warn)" : "var(--ink)";
  return (
    <div className="panel" style={{ flex: "1 1 170px", minWidth: 150 }}>
      <div style={{ fontSize: 12.5, color: "var(--ink-muted)", fontWeight: 700 }}>{label}</div>
      <div style={{ fontSize: 26, fontWeight: 700, color, marginTop: 6 }}>{value}</div>
      {hint && <div style={{ fontSize: 11.5, color: "var(--ink-muted)", marginTop: 4 }}>{hint}</div>}
    </div>
  );
}

export default function DashboardPage() {
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getDashboardSummary()
      .then(setSummary)
      .catch((err) => setError(err instanceof Error ? err.message : "불러오기 실패"));
  }, []);

  return (
    <AppShell>
      <h1 style={{ fontSize: 20, fontWeight: 700, marginBottom: 4 }}>통합 대시보드</h1>
      <p style={{ color: "var(--ink-muted)", fontSize: 13, marginTop: 0 }}>
        아래 수치는 모두 실제 DB 조회 결과이며 고정값이 아닙니다 — 재처리·재분석 후 바로 바뀝니다.
        {summary && <> (조회 시각: {fmtDate(summary.generated_at)})</>}
      </p>
      {error && <p style={{ color: "var(--bad)" }}>{error}</p>}
      {!summary && !error && <p>불러오는 중...</p>}

      {summary && (
        <>
          <section style={{ display: "flex", flexWrap: "wrap", gap: 12, marginBottom: 20 }}>
            <StatCard label="전체 수집자료" value={summary.total_documents} />
            <StatCard label="ICT 분야 매칭(관련)" value={summary.matched_documents} />
            <StatCard label="관련성 낮음" value={summary.low_relevance_documents} tone="warn" />
            <StatCard label="분류 보류" value={summary.pending_review_documents} tone="warn" />
            <StatCard label="미처리(분류 전)" value={summary.unclassified_documents} />
          </section>

          <section style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginBottom: 20 }}>
            <div className="panel">
              <h2 style={{ fontSize: 14, margin: "0 0 10px" }}>ICT 9대 분야별 매칭 문서 수</h2>
              <table style={{ width: "100%", fontSize: 13, borderCollapse: "collapse" }}>
                <tbody>
                  {Object.entries(FIELD_LABELS).map(([code, label]) => {
                    const row = summary.by_field.find((f) => f.field_code === code);
                    const isConv = code === "conv";
                    return (
                      <tr key={code} style={{ borderTop: "1px solid var(--border)" }}>
                        <td style={{ padding: "6px 4px" }}><Link href={`/documents?field_code=${code}`} aria-label={`${label} 자료 보기`}>{label}</Link></td>
                        <td style={{ padding: "6px 4px", textAlign: "right", fontWeight: 700, color: isConv && (row?.document_count ?? 0) === 0 ? "var(--warn)" : "var(--ink)" }}>
                          <Link href={`/documents?field_code=${code}`} style={{ color: "inherit" }} data-testid={`field-count-${code}`}>{row?.document_count ?? 0}</Link>
                          {isConv && (row?.document_count ?? 0) === 0 && " (수집원 보강 필요)"}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            <div className="panel">
              <h2 style={{ fontSize: 14, margin: "0 0 10px" }}>원문 전문 확보 현황</h2>
              <table style={{ width: "100%", fontSize: 13, borderCollapse: "collapse" }}>
                <tbody>
                  <tr><td style={{ padding: "6px 4px" }}>전문 확보 성공</td><td style={{ padding: "6px 4px", textAlign: "right", fontWeight: 700 }}>{summary.extraction_success}</td></tr>
                  <tr style={{ borderTop: "1px solid var(--border)" }}><td style={{ padding: "6px 4px" }}>부분 추출</td><td style={{ padding: "6px 4px", textAlign: "right" }}>{summary.extraction_partial}</td></tr>
                  <tr style={{ borderTop: "1px solid var(--border)" }}><td style={{ padding: "6px 4px" }}>요약만 확보</td><td style={{ padding: "6px 4px", textAlign: "right" }}>{summary.extraction_summary_only}</td></tr>
                  <tr style={{ borderTop: "1px solid var(--border)" }}><td style={{ padding: "6px 4px" }}>추출 실패</td><td style={{ padding: "6px 4px", textAlign: "right", color: "var(--bad)" }}>{summary.extraction_failed}</td></tr>
                  <tr style={{ borderTop: "1px solid var(--border)" }}><td style={{ padding: "6px 4px" }}>시도 안 함</td><td style={{ padding: "6px 4px", textAlign: "right" }}>{summary.extraction_not_attempted}</td></tr>
                </tbody>
              </table>
            </div>
          </section>

          <section style={{ display: "flex", flexWrap: "wrap", gap: 12, marginBottom: 20 }}>
            <StatCard label="이슈 클러스터" value={summary.issue_cluster_total} hint={`복수문서 ${summary.issue_cluster_multi_document}건`} />
            <StatCard label="이슈 통합 확정" value={summary.issue_cluster_confirmed} />
            <StatCard label="이슈 통합 검토대기" value={summary.issue_cluster_needs_review} tone={summary.issue_cluster_needs_review > 0 ? "warn" : undefined} />
            <StatCard label="후보주제" value={summary.candidate_total} />
            <StatCard
              label="국내 산업연관성 평가보류"
              value={summary.domestic_relevance_pending}
              hint={`평가완료 ${summary.domestic_relevance_assessed}건 — 근거 없는 연관성은 추정하지 않음`}
              tone={summary.domestic_relevance_pending > 0 ? "warn" : undefined}
            />
          </section>

          <section style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
            <div className="panel">
              <h2 style={{ fontSize: 14, margin: "0 0 10px" }}>후보주제 검토 현황</h2>
              <table style={{ width: "100%", fontSize: 13, borderCollapse: "collapse" }}>
                <tbody>
                  {Object.entries(CANDIDATE_STATUS_LABELS).map(([code, label]) => (
                    <tr key={code} style={{ borderTop: "1px solid var(--border)" }}>
                      <td style={{ padding: "6px 4px" }}>{label}</td>
                      <td style={{ padding: "6px 4px", textAlign: "right", fontWeight: 700 }}>{summary.candidate_by_status[code] ?? 0}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <div style={{ marginTop: 10 }}>
                <Link href="/candidates" className="tbtn">후보주제 전체보기</Link>
              </div>
            </div>

            <div className="panel">
              <h2 style={{ fontSize: 14, margin: "0 0 10px" }}>출처 현황</h2>
              <table style={{ width: "100%", fontSize: 13, borderCollapse: "collapse" }}>
                <tbody>
                  <tr><td style={{ padding: "6px 4px" }}>등록된 출처</td><td style={{ padding: "6px 4px", textAlign: "right", fontWeight: 700 }}>{summary.source_total}</td></tr>
                  <tr style={{ borderTop: "1px solid var(--border)" }}><td style={{ padding: "6px 4px" }}>활성 출처</td><td style={{ padding: "6px 4px", textAlign: "right" }}>{summary.source_active}</td></tr>
                  <tr style={{ borderTop: "1px solid var(--border)" }}><td style={{ padding: "6px 4px" }}>관리자 확인 필요</td><td style={{ padding: "6px 4px", textAlign: "right", color: summary.source_needs_review > 0 ? "var(--bad)" : "var(--ink)" }}>{summary.source_needs_review}</td></tr>
                </tbody>
              </table>
              <div style={{ marginTop: 10 }}>
                <Link href="/sources" className="tbtn">출처·수집 관리로 이동</Link>
              </div>
            </div>
          </section>

          <section className="panel" style={{ marginTop: 20 }}>
            <h2 style={{ fontSize: 14, margin: "0 0 10px" }}>최근 수집 활동</h2>
            {summary.recent_activity.length === 0 && <p style={{ color: "var(--ink-muted)", fontSize: 13 }}>최근 수집 내역이 없습니다</p>}
            <ul style={{ listStyle: "none", padding: 0, margin: 0, fontSize: 13 }}>
              {summary.recent_activity.map((a) => (
                <li key={a.document_id} style={{ padding: "6px 0", borderTop: "1px solid var(--border)" }}>
                  <Link href={`/documents/${a.document_id}`}>{a.title}</Link>
                  <span style={{ color: "var(--ink-muted)", marginLeft: 8 }}>{fmtDate(a.occurred_at)}</span>
                </li>
              ))}
            </ul>
          </section>
        </>
      )}
    </AppShell>
  );
}
