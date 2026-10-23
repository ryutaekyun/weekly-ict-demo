"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import AppShell from "@/components/AppShell";
import { getIssueDetail, UnauthorizedError, type IssueDetail } from "@/lib/api";
import {
  CLUSTER_REVIEW_LABELS,
  DISPUTE_STATUS_LABELS,
  FIELD_LABELS,
  MEMBERSHIP_TYPE_LABELS,
  METHOD_LABELS,
  TIMELINE_EVENT_LABELS,
  fmtDate,
} from "@/lib/labels";

function parseJsonList(raw: string | null): string[] {
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.map((v) => {
      if (typeof v === "string") return v;
      if (v && typeof v === "object") {
        const country = "country_or_org" in v ? v.country_or_org : null;
        const summary = "position_summary" in v ? v.position_summary : null;
        if (summary) return country ? `[${country}] ${summary}` : String(summary);
      }
      return JSON.stringify(v);
    });
  } catch {
    return [raw];
  }
}

export default function IssueDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const [detail, setDetail] = useState<IssueDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getIssueDetail(params.id)
      .then(setDetail)
      .catch((err) => {
        if (err instanceof UnauthorizedError) { router.push("/login"); return; }
        setError(err instanceof Error ? err.message : "불러오기 실패");
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params.id]);

  if (error) return <AppShell><p style={{ color: "var(--bad)" }}>{error}</p></AppShell>;
  if (!detail) return <AppShell><p>불러오는 중...</p></AppShell>;

  const { cluster, members, timeline, analysis, disputes } = detail;
  const countryPositions = analysis ? parseJsonList(analysis.country_positions_json) : [];
  const technicalIssues = analysis ? parseJsonList(analysis.technical_issues_json) : [];
  const policyIssues = analysis ? parseJsonList(analysis.policy_issues_json) : [];
  const industryConcerns = analysis ? parseJsonList(analysis.industry_concerns_json) : [];
  const unconfirmed = analysis ? parseJsonList(analysis.unconfirmed_points_json) : [];

  return (
    <AppShell>
      <div style={{ marginBottom: 10 }}>
        <Link href="/issues" style={{ fontSize: 13 }}>← 이슈 목록으로</Link>
      </div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12 }}>
        <h1 style={{ fontSize: 19, fontWeight: 700, margin: 0 }}>{cluster.title}</h1>
        <span className={`pill ${cluster.review_status === "confirmed" ? "rec" : "hold"}`}>
          {CLUSTER_REVIEW_LABELS[cluster.review_status] ?? cluster.review_status}
        </span>
      </div>
      <div style={{ display: "flex", gap: 14, flexWrap: "wrap", fontSize: 13, color: "var(--ink-muted)", margin: "8px 0 16px" }}>
        <span>{FIELD_LABELS[cluster.field_code] ?? cluster.field_code}</span>
        <span>관련 문서 {members.length}건</span>
        <span>최초 발표 {fmtDate(cluster.first_seen_at)}</span>
        {cluster.created_by_method && <span>생성 방식: {METHOD_LABELS[cluster.created_by_method] ?? cluster.created_by_method}</span>}
      </div>

      {cluster.review_status === "needs_review" && cluster.summary && (
        <div className="panel" style={{ marginBottom: 16, background: "var(--warn-soft)", color: "var(--warn)", fontSize: 13 }}>
          검토 필요 사유: {cluster.summary}
        </div>
      )}

      {analysis ? (
        <>
          <section className="panel" style={{ marginBottom: 16 }}>
            <h2 style={sectionTitle}>① 핵심 내용 및 배경</h2>
            <span className="pill review" style={{ marginBottom: 8 }}>{METHOD_LABELS[analysis.generated_by] ?? analysis.generated_by}</span>
            {analysis.key_summary && <p style={p}>{analysis.key_summary}</p>}
            {analysis.background_purpose && <p style={p}><b>배경·목적: </b>{analysis.background_purpose}</p>}
            {analysis.policy_tech_change && <p style={p}><b>정책·기술 내용: </b>{analysis.policy_tech_change}</p>}
            {!analysis.key_summary && !analysis.background_purpose && <p style={{ color: "var(--ink-muted)", fontSize: 13 }}>분석 결과가 아직 없습니다</p>}
          </section>

          <section className="panel" style={{ marginBottom: 16 }}>
            <h2 style={sectionTitle}>③ 핵심 쟁점</h2>
            <JsonListBlock title="기술적 쟁점" items={technicalIssues} />
            <JsonListBlock title="정책·규제적 쟁점" items={policyIssues} />
            <JsonListBlock title="산업계 우려·기대" items={industryConcerns} />
            <JsonListBlock title="아직 확인되지 않은 사항" items={unconfirmed} />
            {[technicalIssues, policyIssues, industryConcerns, unconfirmed].every((l) => l.length === 0) && (
              <p style={{ color: "var(--ink-muted)", fontSize: 13 }}>확인된 핵심 쟁점이 없습니다</p>
            )}
          </section>

          <section className="panel" style={{ marginBottom: 16 }}>
            <h2 style={sectionTitle}>④ 국가별·기관별 비교</h2>
            {countryPositions.length > 0 ? (
              <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13 }}>
                {countryPositions.map((c, idx) => <li key={idx}>{c}</li>)}
              </ul>
            ) : (
              <p style={{ color: "var(--ink-muted)", fontSize: 13 }}>국가별 비교 근거 자료가 없어 임의로 작성하지 않았습니다(자료 부족)</p>
            )}
          </section>

          <section className="panel" style={{ marginBottom: 16 }}>
            <h2 style={sectionTitle}>⑤ 국내 ICT 산업 연관성</h2>
            {analysis.domestic_has_sufficient_basis ? (
              <>
                {analysis.domestic_industry_relevance && <p style={p}><b>산업 연관성: </b>{analysis.domestic_industry_relevance}</p>}
                {analysis.domestic_rnd_impact && <p style={p}><b>R&D 영향: </b>{analysis.domestic_rnd_impact}</p>}
                {analysis.domestic_policy_considerations && <p style={p}><b>정책 검토사항: </b>{analysis.domestic_policy_considerations}</p>}
                {analysis.domestic_monitoring_points && <p style={p}><b>모니터링 필요사항: </b>{analysis.domestic_monitoring_points}</p>}
              </>
            ) : (
              <p style={{ color: "var(--warn)", fontSize: 13, fontWeight: 700 }}>평가 보류 — 원문에 국내 산업 연관성을 판단할 직접 근거가 없어 추정하지 않았습니다</p>
            )}
          </section>

          <section className="panel" style={{ marginBottom: 16 }}>
            <h2 style={sectionTitle}>⑥ 논쟁·쟁점 탐지 결과</h2>
            <span className={`pill ${analysis.dispute_status === "disputes_found" ? "hold" : "rec"}`}>
              {DISPUTE_STATUS_LABELS[analysis.dispute_status] ?? analysis.dispute_status}
            </span>
            {disputes.length > 0 && (
              <div style={{ display: "flex", flexDirection: "column", gap: 10, marginTop: 10 }}>
                {disputes.map((d) => (
                  <div key={d.id} className="panel" style={{ background: "var(--panel-2)" }}>
                    <div style={{ fontWeight: 700, fontSize: 13.5, marginBottom: 6 }}>{d.dispute_title}</div>
                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, fontSize: 13 }}>
                      <div>
                        <div style={{ fontWeight: 700 }}>{d.claim_a_stakeholder ?? "주장 A"}</div>
                        <div>{d.claim_a_text}</div>
                      </div>
                      <div>
                        <div style={{ fontWeight: 700 }}>{d.claim_b_stakeholder ?? "주장 B"}</div>
                        <div>{d.claim_b_text}</div>
                      </div>
                    </div>
                    {d.common_ground && <p style={{ fontSize: 12.5, marginTop: 6 }}><b>공통점: </b>{d.common_ground}</p>}
                    {d.differences && <p style={{ fontSize: 12.5, margin: "2px 0" }}><b>차이점: </b>{d.differences}</p>}
                    {d.unresolved_notes && <p style={{ fontSize: 12.5, margin: "2px 0", color: "var(--ink-muted)" }}><b>미해결: </b>{d.unresolved_notes}</p>}
                  </div>
                ))}
              </div>
            )}
          </section>
        </>
      ) : (
        <section className="panel" style={{ marginBottom: 16 }}>
          <p style={{ color: "var(--ink-muted)", fontSize: 13 }}>아직 이슈 분석이 실행되지 않았습니다</p>
        </section>
      )}

      <section className="panel" style={{ marginBottom: 16 }}>
        <h2 style={sectionTitle}>② 타임라인(최초 발표 → 후속 변화)</h2>
        {timeline.length === 0 && <p style={{ color: "var(--ink-muted)", fontSize: 13 }}>타임라인 이벤트가 없습니다</p>}
        <ul style={{ margin: 0, paddingLeft: 0, listStyle: "none", fontSize: 13 }}>
          {timeline.map((t) => (
            <li key={t.id} style={{ padding: "8px 0", borderTop: "1px solid var(--border)" }}>
              <span className="pill review" style={{ marginRight: 8 }}>{TIMELINE_EVENT_LABELS[t.event_type] ?? t.event_type}</span>
              {t.event_date_label && <b style={{ marginRight: 6 }}>{t.event_date_label}</b>}
              {fmtDate(t.event_date)}
              {t.description && <div style={{ marginTop: 4 }}>{t.description}</div>}
            </li>
          ))}
        </ul>
      </section>

      <section className="panel">
        <h2 style={sectionTitle}>관련 원문 전체 목록</h2>
        <ul style={{ margin: 0, paddingLeft: 0, listStyle: "none", fontSize: 13 }}>
          {members.map((m) => (
            <li key={m.document_id} style={{ padding: "8px 0", borderTop: "1px solid var(--border)" }}>
              <span className="pill review" style={{ marginRight: 8 }}>{MEMBERSHIP_TYPE_LABELS[m.membership_type] ?? m.membership_type}</span>
              <Link href={`/documents/${m.document_id}`}>{m.title}</Link>
              <span style={{ color: "var(--ink-muted)", marginLeft: 8 }}>{fmtDate(m.published_at)}</span>
              {m.judgment_reasoning && <div style={{ fontSize: 12, color: "var(--ink-muted)", marginTop: 2 }}>통합 근거: {m.judgment_reasoning}</div>}
            </li>
          ))}
        </ul>
      </section>
    </AppShell>
  );
}

function JsonListBlock({ title, items }: { title: string; items: string[] }) {
  if (items.length === 0) return null;
  return (
    <div style={{ marginBottom: 10 }}>
      <div style={{ fontWeight: 700, fontSize: 13 }}>{title}</div>
      <ul style={{ margin: "4px 0 0", paddingLeft: 18, fontSize: 13 }}>
        {items.map((it, idx) => <li key={idx}>{it}</li>)}
      </ul>
    </div>
  );
}

const sectionTitle: React.CSSProperties = { fontSize: 14, margin: "0 0 10px" };
const p: React.CSSProperties = { fontSize: 13.5, margin: "4px 0" };
