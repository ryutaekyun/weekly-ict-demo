"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import AppShell from "@/components/AppShell";
import { getDashboardSummary, getWorkDashboard, type DashboardSummary, type WorkDashboard, type WorkDoc } from "@/lib/api";
import { CANDIDATE_STATUS_LABELS, FIELD_LABELS, fmtDate, fmtDateOnly } from "@/lib/labels";

const ACTION_LABELS: Record<string, string> = {
  "user.register": "회원가입", "user.profile.update": "내 정보 수정", "user.approve": "가입 승인", "user.update": "사용자 변경",
};
const MS_STATUS: Record<string, string> = { draft: "작성 중", changes_requested: "수정 요청", review_requested: "검토 요청", approved: "승인", final: "확정", review: "검토" };

function Kpi({ href, label, value, tone, testId }: { href: string; label: string; value: number; tone?: "warn"; testId: string }) {
  return (
    <Link href={href} className="kpi" data-testid={testId}>
      <div className="l">{label}</div>
      <div className="v" style={tone === "warn" && value > 0 ? { color: "var(--warn)" } : undefined}>{value.toLocaleString("ko-KR")}</div>
    </Link>
  );
}

function DocRows({ docs, empty }: { docs: WorkDoc[]; empty: string }) {
  if (docs.length === 0) return <p style={{ color: "var(--ink-muted)", fontSize: 13, margin: 0 }}>{empty}</p>;
  return (
    <div>
      {docs.map((d) => (
        <div key={d.id} className="list-row" data-testid="dash-doc">
          <Link href={`/documents/${d.id}`} className="t" title={d.title}>{d.title}</Link>
          {d.field && <span className="badge">{FIELD_LABELS[d.field] ?? d.field}</span>}
          <span className="m">{d.org ?? ""}{d.published_at ? ` · ${fmtDateOnly(d.published_at)}` : ""}</span>
        </div>
      ))}
    </div>
  );
}

export default function DashboardPage() {
  const [work, setWork] = useState<WorkDashboard | null>(null);
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getWorkDashboard().then(setWork).catch((err) => setError(err instanceof Error ? err.message : "불러오기 실패"));
    getDashboardSummary().then(setSummary).catch(() => undefined);
  }, []);

  return (
    <AppShell>
      <h1 style={{ fontSize: 22, fontWeight: 700, margin: "0 0 4px" }}>통합 대시보드</h1>
      <p style={{ color: "var(--ink-muted)", fontSize: 13, margin: "0 0 22px" }}>
        {work ? `${work.greeting_name}님, 오늘 처리할 업무입니다.` : "업무 현황을 불러오는 중입니다."}
      </p>
      {error && <div role="alert" className="notice err">{error}</div>}
      {!work && !error && <p role="status">불러오는 중...</p>}

      {work && (
        <>
          <section style={{ display: "grid", gridTemplateColumns: "repeat(4, minmax(0, 1fr))", gap: 16, marginBottom: 24 }}>
            <Kpi href="/documents" label="오늘 신규 수집자료" value={work.kpi.new_today} testId="kpi-new" />
            <Kpi href="/candidates" label="검토 대기 후보주제" value={work.kpi.pending_candidates} testId="kpi-candidates" />
            <Kpi href="/manuscripts" label="내가 작성 중인 원고" value={work.kpi.my_manuscripts} testId="kpi-manuscripts" />
            <Kpi href="/sources" label="정보원 수집 오류" value={work.kpi.source_errors} tone="warn" testId="kpi-source-errors" />
          </section>

          <section style={{ display: "grid", gridTemplateColumns: "minmax(0, 3fr) minmax(0, 2fr)", gap: 20, marginBottom: 24 }}>
            <div className="panel" data-testid="recent-docs">
              <h2 className="section-title">최근 수집 뉴스 <Link href="/documents">전체 보기</Link></h2>
              <DocRows docs={work.recent_docs} empty="아직 수집된 자료가 없습니다. 출처·수집 관리에서 정보원을 등록하고 수집을 실행하세요." />
            </div>
            <div className="panel" data-testid="priority-box">
              <h2 className="section-title">우선 검토 후보주제 <Link href="/candidates">전체 보기</Link></h2>
              {work.priority.length === 0 && <p style={{ color: "var(--ink-muted)", fontSize: 13, margin: 0 }}>기준을 충족하는 후보가 없습니다.</p>}
              {work.priority.map((p) => (
                <div key={p.id} className="list-row">
                  <Link href={`/candidates/${p.id}`} className="t" title={p.title}>{p.title}</Link>
                  <span className="badge green">{p.score}</span>
                </div>
              ))}
            </div>
          </section>

          <section style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: 20, marginBottom: 24 }}>
            <div className="panel" data-testid="favorite-docs">
              <h2 className="section-title">관심 분야 최신 동향 <Link href="/account">관심 분야 설정</Link></h2>
              {work.favorite_fields.length === 0
                ? <p style={{ color: "var(--ink-muted)", fontSize: 13, margin: 0 }}>관심 ICT 분야를 지정하면 이곳에 해당 분야의 최신 자료가 표시됩니다.</p>
                : <DocRows docs={work.favorite_docs} empty="관심 분야에 해당하는 자료가 아직 없습니다." />}
            </div>
            <div className="panel">
              <h2 className="section-title">주요 이슈 <Link href="/issues">전체 보기</Link></h2>
              {work.issues.length === 0 && <p style={{ color: "var(--ink-muted)", fontSize: 13, margin: 0 }}>복수 자료가 묶인 이슈가 아직 없습니다.</p>}
              {work.issues.map((i) => (
                <div key={i.id} className="list-row">
                  <Link href={`/issues/${i.id}`} className="t" title={i.title}>{i.title}</Link>
                  <span className="badge">{i.document_count}건</span>
                </div>
              ))}
            </div>
          </section>

          <section style={{ display: "grid", gridTemplateColumns: "repeat(3, minmax(0, 1fr))", gap: 20, marginBottom: 24 }}>
            <div className="panel" data-testid="my-tasks">
              <h2 className="section-title">나의 할 일</h2>
              {work.my_tasks.length === 0 && <p style={{ color: "var(--ink-muted)", fontSize: 13, margin: 0 }}>담당 후보주제·작성 중 원고가 없습니다.</p>}
              {work.my_tasks.map((t) => (
                <div key={`${t.kind}-${t.id}`} className="list-row">
                  <Link href={t.kind === "candidate" ? `/candidates/${t.id}` : `/manuscripts/${t.id}`} className="t" title={t.title}>{t.title}</Link>
                  <span className="badge warn">{t.kind === "candidate" ? (CANDIDATE_STATUS_LABELS[t.status] ?? t.status) : (MS_STATUS[t.status] ?? t.status)}</span>
                </div>
              ))}
            </div>
            <div className="panel">
              <h2 className="section-title">검토 요청</h2>
              {work.review_requests.length === 0 && <p style={{ color: "var(--ink-muted)", fontSize: 13, margin: 0 }}>나에게 요청된 검토가 없습니다.</p>}
              {work.review_requests.map((r) => (
                <div key={r.id} className="list-row"><Link href={`/manuscripts/${r.id}`} className="t" title={r.title}>{r.title}</Link><span className="badge">검토 요청</span></div>
              ))}
            </div>
            <div className="panel">
              <h2 className="section-title">최근 작업 이력</h2>
              {work.history.length === 0 && <p style={{ color: "var(--ink-muted)", fontSize: 13, margin: 0 }}>기록된 작업이 없습니다.</p>}
              {work.history.map((h, i) => (
                <div key={i} className="list-row"><span className="t">{ACTION_LABELS[h.action] ?? h.action}</span><span className="m">{fmtDate(h.at)}</span></div>
              ))}
            </div>
          </section>

          {work.source_errors.length > 0 && (
            <section className="panel" style={{ marginBottom: 24 }} data-testid="source-errors">
              <h2 className="section-title">수집 오류가 있는 정보원 <Link href="/sources">출처·수집 관리</Link></h2>
              {work.source_errors.map((s) => (
                <div key={s.id} className="list-row"><span className="t">{s.name}</span><span className="badge bad">연속 실패 {s.failures}회</span>{s.needs_review && <span className="badge warn">확인 필요</span>}</div>
              ))}
            </section>
          )}

          {summary && (
            <section className="panel" data-testid="field-status">
              <h2 className="section-title">ICT 9대 분야별 수집 현황 <span style={{ fontSize: 12, fontWeight: 400, color: "var(--ink-muted)" }}>전체 {summary.total_documents}건 · 분야 분류 완료 {summary.matched_documents}건</span></h2>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(3, minmax(0, 1fr))", gap: "4px 28px" }}>
                {Object.entries(FIELD_LABELS).map(([code, label]) => {
                  const n = summary.by_field.find((f) => f.field_code === code)?.document_count ?? 0;
                  return (
                    <div key={code} className="list-row">
                      <Link href={`/documents?field_code=${code}`} className="t" aria-label={`${label} 자료 보기`}>{label}</Link>
                      <Link href={`/documents?field_code=${code}`} data-testid={`field-count-${code}`} style={{ fontWeight: 700, color: "var(--navy)" }}>{n}</Link>
                    </div>
                  );
                })}
              </div>
            </section>
          )}
        </>
      )}
    </AppShell>
  );
}
