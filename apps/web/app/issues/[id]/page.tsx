"use client";

import AiPanel from "@/components/AiPanel";
import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import AppShell from "@/components/AppShell";
import OriginalLink from "@/components/OriginalLink";
import { getIssueDetail, listIssues, mergeIssueCluster, splitIssueDocument, UnauthorizedError, type IssueClusterOut, type IssueDetail } from "@/lib/api";
import {
  CANDIDATE_STATUS_LABELS,
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
  const [others, setOthers] = useState<IssueClusterOut[]>([]);
  const [mergeTarget, setMergeTarget] = useState("");
  const [mergeReason, setMergeReason] = useState("");
  const [mergeConfirm, setMergeConfirm] = useState(false);
  const [opMessage, setOpMessage] = useState<string | null>(null);
  const [opError, setOpError] = useState<string | null>(null);

  function load() {
    getIssueDetail(params.id)
      .then((d) => { setDetail(d); listIssues({ field_code: d.cluster.field_code }).then((all) => setOthers(all.filter((c) => c.id !== d.cluster.id))).catch(() => undefined); })
      .catch((err) => {
        if (err instanceof UnauthorizedError) { router.push("/login"); return; }
        setError(err instanceof Error ? err.message : "불러오기 실패");
      });
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params.id]);

  async function doMerge() {
    setOpError(null); setOpMessage(null);
    try {
      const target = await mergeIssueCluster(params.id, mergeTarget, mergeReason || undefined);
      setOpMessage("이슈를 병합했습니다. 잘못 합쳤다면 병합된 문서를 '별도 이슈로 분리'해 되돌릴 수 있습니다.");
      router.push(`/issues/${target.id}`);
    } catch (err) { setOpError(err instanceof Error ? err.message : "병합 실패"); }
  }

  async function doSplit(documentId: string, title: string) {
    setOpError(null); setOpMessage(null);
    if (!window.confirm(`'${title}' 문서를 이 이슈에서 분리해 별도 이슈로 만듭니다. 계속할까요? (다시 병합해 되돌릴 수 있습니다)`)) return;
    try {
      const created = await splitIssueDocument(documentId, "연구원 수동 분리");
      setOpMessage("문서를 분리해 새 이슈를 만들었습니다.");
      router.push(`/issues/${created.id}`);
    } catch (err) { setOpError(err instanceof Error ? err.message : "분리 실패"); }
  }

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
              <OriginalLink url={m.origin_url} state={m.link_state} blocked={m.link_blocked} note={m.link_note} isPdf={m.is_pdf} testId="member-link">{m.title}</OriginalLink>
              <span style={{ color: "var(--ink-muted)", marginLeft: 8 }}>{m.source_org ?? ""} {m.country_code ? `· ${m.country_code}` : ""} · {fmtDate(m.published_at)}</span>
              <Link className="tbtn" style={{ marginLeft: 8 }} href={`/documents/${m.document_id}`} aria-label={`상세 분석: ${m.title}`}>상세 분석</Link>
              {members.length > 1 && <button className="tbtn" style={{ marginLeft: 6 }} onClick={() => doSplit(m.document_id, m.title)}>별도 이슈로 분리</button>}
              {m.judgment_reasoning && <div style={{ fontSize: 12, color: "var(--ink-muted)", marginTop: 2 }}>통합 근거: {m.judgment_reasoning}</div>}
            </li>
          ))}
        </ul>
      </section>

      <div style={{ marginTop: 16 }}>
        <AiPanel kind="issue" targetId={params.id} title="AI 심층분석 (여러 원문 종합 · 근거 검증)" buttonLabel="AI 심층분석" testId="ai-panel-issue" />
        <AiPanel kind="candidate" targetId={params.id} title="AI 후보주제 제안" buttonLabel="AI 후보주제 제안" testId="ai-panel-candidate"
          existingCandidates={detail.candidates.map((c) => ({ id: c.id, title: c.title }))} />
      </div>

      <section className="panel" style={{ marginTop: 16 }}>
        <h2 style={sectionTitle}>이 이슈의 후보주제</h2>
        {detail.candidates.length === 0 && <p style={{ color: "var(--ink-muted)", fontSize: 13 }}>이 이슈에서 만들어진 후보주제가 없습니다.</p>}
        <ul style={{ margin: 0, paddingLeft: 0, listStyle: "none", fontSize: 13 }}>
          {detail.candidates.map((c) => (
            <li key={c.id} style={{ padding: "6px 0", borderTop: "1px solid var(--border)" }}>
              <Link href={`/candidates/${c.id}`}>{c.title}</Link> <span className="pill review">{CANDIDATE_STATUS_LABELS[c.status] ?? c.status}</span>
            </li>
          ))}
        </ul>
      </section>

      <section className="panel" style={{ marginTop: 16 }}>
        <h2 style={sectionTitle}>이슈 병합(같은 분야의 다른 이슈에 합치기)</h2>
        <p style={{ fontSize: 12, color: "var(--ink-muted)", margin: "0 0 8px" }}>서로 다른 이슈를 잘못 합치지 않도록 확인이 필요합니다. 병합 후에도 문서를 &lsquo;별도 이슈로 분리&rsquo;하면 되돌릴 수 있고, 모든 변경은 이력으로 남습니다.</p>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
          <select aria-label="병합 대상 이슈" value={mergeTarget} onChange={(e) => setMergeTarget(e.target.value)} style={{ padding: 7, borderRadius: 8, border: "1px solid var(--border)", maxWidth: 420 }}>
            <option value="">병합할 대상 이슈 선택</option>
            {others.map((c) => <option key={c.id} value={c.id}>{c.title.slice(0, 60)} ({c.document_count}건)</option>)}
          </select>
          <input aria-label="병합 사유" placeholder="병합 사유" value={mergeReason} onChange={(e) => setMergeReason(e.target.value)} style={{ padding: 7, borderRadius: 8, border: "1px solid var(--border)", minWidth: 200 }} />
          <label style={{ fontSize: 12.5 }}><input type="checkbox" checked={mergeConfirm} onChange={(e) => setMergeConfirm(e.target.checked)} /> 두 이슈가 같은 사건임을 확인했습니다</label>
          <button className="tbtn" disabled={!mergeTarget || !mergeConfirm} onClick={doMerge}>이슈 병합</button>
        </div>
        {opMessage && <p role="status" style={{ color: "var(--ok)", fontSize: 13 }}>{opMessage}</p>}
        {opError && <p role="alert" style={{ color: "var(--bad)", fontSize: 13 }}>{opError}</p>}
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
