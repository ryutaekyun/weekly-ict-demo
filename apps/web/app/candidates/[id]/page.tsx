"use client";

import { changeCandidateEvidence, listDocuments } from "@/lib/api";
import AiPanel from "@/components/AiPanel";
import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import AppShell from "@/components/AppShell";
import OriginalLink from "@/components/OriginalLink";
import { apiFetch, createManuscript, listUsers, UnauthorizedError, updateCandidate, type CandidateDetail, type UserSummary } from "@/lib/api";
import { CANDIDATE_STATUS_LABELS, FIELD_LABELS, METHOD_LABELS, fmtDate, fmtDateOnly } from "@/lib/labels";

type ScoreNumericKey = "policy_impact_score" | "timeliness_score" | "domestic_relevance_score" | "novelty_score" | "analysis_depth_score";

const SCORE_CRITERIA: { key: ScoreNumericKey; label: string; weightKey: string }[] = [
  { key: "policy_impact_score", label: "정책·산업 파급력(30%)", weightKey: "policy_impact" },
  { key: "timeliness_score", label: "시의성·긴급성(20%)", weightKey: "timeliness" },
  { key: "domestic_relevance_score", label: "국내 산업 연관성(20%)", weightKey: "domestic_relevance" },
  { key: "novelty_score", label: "신규성(15%)", weightKey: "novelty" },
  { key: "analysis_depth_score", label: "분석 확장성(15%)", weightKey: "analysis_depth" },
];

function safeParseReasoning(raw: string): Record<string, unknown> {
  try {
    return JSON.parse(raw);
  } catch {
    return {};
  }
}

export default function CandidateDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const [candidate, setCandidate] = useState<CandidateDetail | null>(null);
  const [comment, setComment] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [editTitle, setEditTitle] = useState("");
  const [editReason, setEditReason] = useState("");
  const [editSummary, setEditSummary] = useState("");
  const [editAssignee, setEditAssignee] = useState("");
  const [editField, setEditField] = useState("");
  const [evSearch, setEvSearch] = useState("");
  const [evResults, setEvResults] = useState<{ id: string; title: string; source_org_name: string | null; published_at: string | null }[]>([]);
  const [users, setUsers] = useState<UserSummary[]>([]);
  const [saveMsg, setSaveMsg] = useState<string | null>(null);
  const [startingManuscript, setStartingManuscript] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);

  function load() {
    apiFetch<CandidateDetail>(`/candidates/${params.id}`)
      .then((c) => {
        setCandidate(c);
        setEditTitle(c.title);
        setEditReason(c.recommended_reason ?? "");
        setEditSummary(c.summary ?? "");
        setEditAssignee(c.assignee_user_id ?? "");
        setEditField(c.field_code);
      })
      .catch((err) => {
        if (err instanceof UnauthorizedError) { router.push("/login"); return; }
        setError(err instanceof Error ? err.message : "불러오기 실패");
      });
  }

  useEffect(() => { listUsers().then(setUsers).catch(() => undefined); }, []);

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params.id, router]);

  async function submitComment(e: React.FormEvent) {
    e.preventDefault();
    if (!comment.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      await apiFetch(`/candidates/${params.id}/reviews`, {
        method: "POST",
        body: JSON.stringify({ comment_text: comment }),
      });
      setComment("");
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "의견 등록 실패");
    } finally {
      setSubmitting(false);
    }
  }

  async function saveEdits(e: React.FormEvent) {
    e.preventDefault();
    setSaveMsg(null);
    try {
      await updateCandidate(params.id, { field_code: editField, title: editTitle, summary: editSummary, recommended_reason: editReason, assignee_user_id: editAssignee || null });
      setSaveMsg("저장되었습니다");
      load();
    } catch (err) {
      setSaveMsg(err instanceof Error ? `저장 실패: ${err.message}` : "저장 실패");
    }
  }

  async function evidence(documentId: string, action: "add" | "exclude" | "restore") {
    setSaveMsg(null);
    try {
      await changeCandidateEvidence(params.id, documentId, action);
      setSaveMsg(action === "add" ? "근거 원문을 추가했습니다" : action === "exclude" ? "근거에서 제외했습니다(복원할 수 있습니다)" : "근거 원문을 복원했습니다");
      setEvResults([]);
      load();
    } catch (err) {
      setSaveMsg(err instanceof Error ? `근거 변경 실패: ${err.message}` : "근거 변경 실패");
    }
  }

  async function searchEvidence() {
    if (!evSearch.trim()) return;
    try {
      const r = await listDocuments({ q: evSearch.trim(), page: 1, page_size: 8 });
      setEvResults(r.items.map((d) => ({ id: d.id, title: d.title, source_org_name: d.source_org_name, published_at: d.published_at })));
    } catch (err) {
      setSaveMsg(err instanceof Error ? `검색 실패: ${err.message}` : "검색 실패");
    }
  }

  async function changeStatus(status: string) {
    setSaveMsg(null);
    try {
      await updateCandidate(params.id, { status: status as CandidateDetail["status"] });
      load();
    } catch (err) {
      setSaveMsg(err instanceof Error ? `상태 변경 실패: ${err.message}` : "상태 변경 실패");
    }
  }

  if (error) return <AppShell><p style={{ color: "var(--bad)" }}>{error}</p></AppShell>;
  if (!candidate) return <AppShell><p>불러오는 중...</p></AppShell>;

  const score = candidate.recommendation_score;
  const reasoning = score ? safeParseReasoning(score.reasoning_json) : {};
  const skipped: string[] = Array.isArray(reasoning.skipped_criteria) ? (reasoning.skipped_criteria as string[]) : [];
  const scoredCriteriaCount = score ? SCORE_CRITERIA.filter((c) => score[c.key] !== null).length : 0;
  const isPartialScore = score ? scoredCriteriaCount < SCORE_CRITERIA.length : false;

  async function handleStartManuscript() {
    setStartingManuscript(true);
    try {
      const manuscript = await createManuscript({
        candidate_id: candidate!.id, manuscript_type: "key_issue", title: candidate!.title,
      });
      router.push(`/manuscripts/${manuscript.id}`);
    } catch (err) {
      setStartError(err instanceof Error ? err.message : "원고 생성 실패");
      setStartingManuscript(false);
    }
  }

  return (
    <AppShell>
      <div style={{ marginBottom: 10 }}>
        <Link href="/candidates" style={{ fontSize: 13 }}>← 후보주제 목록으로</Link>
      </div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12 }}>
        <h1 style={{ fontSize: 19, fontWeight: 700, margin: 0 }}>{candidate.title}</h1>
        <span className={`pill ${candidate.status}`}>{CANDIDATE_STATUS_LABELS[candidate.status] ?? candidate.status}</span>
      </div>
      <div style={{ display: "flex", gap: 14, flexWrap: "wrap", fontSize: 13, color: "var(--ink-muted)", margin: "8px 0 16px" }}>
        <span>{FIELD_LABELS[candidate.field_code] ?? candidate.field_code}</span>
        <span>발표 {fmtDateOnly(candidate.announced_date)}</span>
        <span>{candidate.source_org ?? ""}</span>
        {candidate.issue_cluster_id && <Link href={`/issues/${candidate.issue_cluster_id}`}>관련 이슈 분석 보기 →</Link>}
      </div>

      <div style={{ marginBottom: 16 }}>
        <button className="tbtn primary" disabled={startingManuscript} onClick={handleStartManuscript}>
          {startingManuscript ? "원고 생성 중..." : "원고 작성 시작"}
        </button>
        {startError && <span role="alert" style={{ marginLeft: 8, color: "var(--danger, #b42318)", fontSize: 12.5 }}>{startError}</span>}
        {candidate.status !== "final" && (
          <span style={{ fontSize: 11.5, color: "var(--ink-muted)", marginLeft: 8 }}>
            아직 내부 확정 전 후보입니다 — 사전 검토용 원고로 작성됩니다(IITP 공식 선정 아님)
          </span>
        )}
      </div>

      {candidate.summary && <p style={{ fontSize: 13.5 }}>{candidate.summary}</p>}
      <p style={{ fontSize: 12.5, color: "var(--ink-muted)" }}>검토 담당자: {candidate.assignee_name ?? "미지정"}</p>

      <section className="panel" style={{ marginBottom: 16 }}>
        <h2 style={{ fontSize: 14, margin: "0 0 10px" }}>근거 원문·관련 뉴스 ({candidate.related_documents.length}건)</h2>
        {candidate.related_documents.length === 0 && <p style={{ color: "var(--ink-muted)", fontSize: 13 }}>연결된 근거 원문이 없습니다. 근거 문서가 있는 이슈에서 후보주제를 만들면 자동으로 연결됩니다.</p>}
        <div style={{ display: "flex", gap: 6, margin: "0 0 8px", flexWrap: "wrap" }}>
          <input aria-label="근거로 추가할 원문 검색" placeholder="근거로 추가할 원문 제목·키워드 검색" value={evSearch} onChange={(e) => setEvSearch(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); searchEvidence(); } }} style={{ ...inp, minWidth: 260 }} />
          <button className="tbtn" type="button" data-testid="evidence-search" onClick={searchEvidence}>원문 검색</button>
        </div>
        {evResults.length > 0 && (
          <ul data-testid="evidence-results" style={{ margin: "0 0 8px", paddingLeft: 0, listStyle: "none", fontSize: 12.5 }}>
            {evResults.map((r) => (
              <li key={r.id} style={{ padding: "4px 0", borderTop: "1px solid var(--border)" }}>{r.title} <span style={{ color: "var(--ink-muted)" }}>· {r.source_org_name ?? ""} · {fmtDate(r.published_at)}</span>
                <button className="tbtn" style={{ marginLeft: 6 }} onClick={() => evidence(r.id, "add")}>근거에 추가</button></li>
            ))}
          </ul>
        )}
        <ul style={{ margin: 0, paddingLeft: 0, listStyle: "none", fontSize: 13 }}>
          {candidate.related_documents.map((d) => (
            <li key={d.document_id} style={{ padding: "8px 0", borderTop: "1px solid var(--border)" }}>
              {d.is_primary && <span className="pill rec" style={{ marginRight: 6 }}>대표 근거</span>}
              <OriginalLink url={d.origin_url} state={d.link_state} blocked={d.link_blocked} note={d.link_note} isPdf={d.is_pdf} testId="related-link">{d.title}</OriginalLink>
              <span style={{ color: "var(--ink-muted)", marginLeft: 8 }}>{d.org ?? ""} {d.country_code ? `· ${d.country_code}` : ""} · {fmtDate(d.published_at)}</span>
              <Link className="tbtn" style={{ marginLeft: 8 }} href={`/documents/${d.document_id}`} aria-label={`상세 분석: ${d.title}`}>상세 분석</Link>
              {d.added_by_researcher && <span className="pill navy" style={{ marginLeft: 6 }}>연구원이 추가</span>}
              {!d.is_primary && <button className="tbtn" style={{ marginLeft: 6 }} data-testid="evidence-exclude" onClick={() => evidence(d.document_id, "exclude")}>근거에서 제외</button>}
            </li>
          ))}
        </ul>
        {candidate.excluded_documents.length > 0 && (
          <div data-testid="excluded-docs" style={{ marginTop: 8, fontSize: 12.5, color: "var(--ink-muted)" }}>
            제외한 원문: {candidate.excluded_documents.map((d) => (
              <span key={d.document_id} style={{ marginRight: 8 }}>{d.title.slice(0, 40)} <button className="tbtn" onClick={() => evidence(d.document_id, "restore")}>복원</button></span>
            ))}
          </div>
        )}
      </section>

      {score ? (
        <section className="panel" style={{ marginBottom: 16 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <h2 style={{ fontSize: 14, margin: 0 }}>규칙 기반 추천 평가 ({METHOD_LABELS[score.method] ?? score.method}) — 연구원 검토 필요</h2>
            <div style={{ fontSize: 22, fontWeight: 700 }}>
              {score.total_score !== null ? score.total_score.toFixed(1) : "-"}점
              {isPartialScore && <span style={{ fontSize: 11, color: "var(--warn)", marginLeft: 6, fontWeight: 400 }}>부분 평가점수</span>}
            </div>
          </div>
          <table style={{ width: "100%", fontSize: 13, borderCollapse: "collapse", marginTop: 10 }}>
            <tbody>
              {SCORE_CRITERIA.map((c) => {
                const value = score[c.key];
                const isSkipped = skipped.includes(c.weightKey) || value === null;
                const note = typeof reasoning[c.weightKey] === "string" ? (reasoning[c.weightKey] as string) : null;
                return (
                  <tr key={c.key} style={{ borderTop: "1px solid var(--border)" }}>
                    <td style={{ padding: "6px 4px", width: 200 }}>{c.label}</td>
                    <td style={{ padding: "6px 4px", width: 70, fontWeight: 700, color: isSkipped ? "var(--warn)" : "var(--ink)" }}>
                      {value !== null && value !== undefined ? value.toFixed(0) : "평가보류"}
                    </td>
                    <td style={{ padding: "6px 4px", color: "var(--ink-muted)" }}>{note ?? ""}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </section>
      ) : (
        <section className="panel" style={{ marginBottom: 16 }}>
          <p style={{ color: "var(--ink-muted)", fontSize: 13 }}>아직 자동 추천 점수가 산출되지 않았습니다</p>
        </section>
      )}

      {candidate.domestic_relevance_note && <p data-testid="domestic-note" style={{ fontSize: 12.5, color: "var(--warn)", margin: "-8px 0 16px" }}>{candidate.domestic_relevance_note}</p>}

      {candidate.issue_summary && (
        <section className="panel" style={{ marginBottom: 16 }} data-testid="issue-summary">
          <h2 style={{ fontSize: 14, margin: "0 0 8px" }}>핵심 이슈·발표 시점·후속 동향 (규칙 기반 분석)</h2>
          <p style={{ fontSize: 13, margin: "0 0 6px" }}>
            <Link href={`/issues/${candidate.issue_summary.issue_id}`}>{candidate.issue_summary.title}</Link> · 묶인 원문 {candidate.issue_summary.document_count}건 ·
            최초 {candidate.issue_summary.first_published ?? "-"} · 최근 {candidate.issue_summary.latest_activity ?? "-"} · 후속 동향 {candidate.issue_summary.followup_count}건
            {candidate.issue_summary.needs_cluster_review && <span className="pill hold" style={{ marginLeft: 6 }}>이슈 묶음 검토 대기</span>}
          </p>
          {candidate.issue_summary.key_summary && <p style={{ fontSize: 13, margin: "0 0 6px" }}>{candidate.issue_summary.key_summary}</p>}
          <p style={{ fontSize: 13, margin: "0 0 6px" }} data-testid="dispute-label"><b>논쟁 가능성</b>: <span className={`pill ${candidate.issue_summary.dispute_status === "disputes_found" ? "review" : "hold"}`}>{candidate.issue_summary.dispute_label}</span>
            {candidate.issue_summary.dispute_count > 0 && ` (쟁점 ${candidate.issue_summary.dispute_count}건)`}
            <span style={{ display: "block", fontSize: 12, color: "var(--ink-muted)" }}>{candidate.issue_summary.dispute_note}</span></p>
          {candidate.issue_summary.timeline.length > 0 && (
            <ul style={{ margin: 0, paddingLeft: 18, fontSize: 12.5 }}>
              {candidate.issue_summary.timeline.map((e, i) => (
                <li key={i}>{e.date ?? "날짜 미상"} · {({ new_issue: "신규", additional_announcement: "추가 발표", substantive_change: "실질 변경", follow_up_action: "후속 조치", no_substantive_change: "변화 없음", insufficient_comparison_data: "비교 자료 부족" } as Record<string, string>)[e.type] ?? e.type}
                  {e.label ? `(${e.label})` : ""} · <Link href={`/documents/${e.document_id}`}>{e.title ?? "문서"}</Link></li>
              ))}
            </ul>
          )}
        </section>
      )}

      {candidate.issue_cluster_id && (
        <AiPanel kind="candidate" targetId={candidate.issue_cluster_id} title="AI 후보주제 제안 — 기존 규칙 기반 추천 근거와 비교" buttonLabel="AI 후보주제 제안" testId="ai-panel-candidate"
          existingCandidates={[{ id: candidate.id, title: candidate.title }]} />
      )}

      <section className="panel" style={{ marginBottom: 16 }}>
        <h2 style={{ fontSize: 14, margin: "0 0 10px" }}>제목·설명·담당자·추천 근거 수정</h2>
        <form onSubmit={saveEdits} style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <select aria-label="후보주제 관련 분야" value={editField} onChange={(e) => setEditField(e.target.value)} style={inp}>
            {Object.entries(FIELD_LABELS).map(([c, l]) => <option key={c} value={c}>{l}</option>)}
          </select>
          <input aria-label="후보주제 제목" value={editTitle} onChange={(e) => setEditTitle(e.target.value)} style={inp} placeholder="제목" />
          <textarea aria-label="후보주제 설명" value={editSummary} onChange={(e) => setEditSummary(e.target.value)} style={{ ...inp, minHeight: 60 }} placeholder="설명" />
          <select aria-label="검토 담당자" value={editAssignee} onChange={(e) => setEditAssignee(e.target.value)} style={inp}>
            <option value="">담당자 미지정</option>
            {users.map((u) => <option key={u.id} value={u.id}>{u.display_name}</option>)}
          </select>
          <textarea value={editReason} onChange={(e) => setEditReason(e.target.value)} style={{ ...inp, minHeight: 70 }} placeholder="추천 근거" />
          <button className="tbtn primary" type="submit" style={{ alignSelf: "flex-start" }}>저장</button>
          {saveMsg && <span style={{ fontSize: 12.5, color: saveMsg.includes("실패") ? "var(--bad)" : "var(--ok)" }}>{saveMsg}</span>}
        </form>
      </section>

      <section className="panel" style={{ marginBottom: 16 }}>
        <h2 style={{ fontSize: 14, margin: "0 0 10px" }}>검토 상태 변경</h2>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          {Object.entries(CANDIDATE_STATUS_LABELS).map(([code, label]) => (
            <button key={code} className="tbtn" disabled={candidate.status === code} onClick={() => changeStatus(code)}>
              {label}로 변경
            </button>
          ))}
        </div>
        <p style={{ fontSize: 11.5, color: "var(--ink-muted)", marginTop: 8 }}>
          확정·반려는 최종 승인자 권한이 필요합니다. IITP 공식 선정 결과는 담당자가 별도로 기록하며, 내부 승인을 자동으로 IITP 승인으로 간주하지 않습니다.
        </p>
      </section>

      <section className="panel" style={{ marginBottom: 16 }}>
        <h2 style={{ fontSize: 14, margin: "0 0 10px" }}>수정 이력</h2>
        {candidate.history.length === 0 && <p style={{ color: "var(--ink-muted)", fontSize: 13 }}>기록된 이력이 없습니다.</p>}
        <ul style={{ margin: 0, paddingLeft: 0, listStyle: "none", fontSize: 12.5 }}>
          {candidate.history.map((h, i) => (
            <li key={i} style={{ padding: "6px 0", borderTop: "1px solid var(--border)" }}>
              {fmtDate(h.at)} · {h.actor ?? "시스템"} · {({ "candidate.create": "등록", "candidate.update": "수정", "candidate.review.add": "검토의견", "candidate.approve": "최종 승인" } as Record<string, string>)[h.action] ?? h.action}
              {h.detail?.changes && Object.entries(h.detail.changes).map(([k, v]) => (
                <div key={k} style={{ color: "var(--ink-muted)" }}>· {k}: {String(v.from ?? "-")} → {String(v.to ?? "-")}</div>
              ))}
            </li>
          ))}
        </ul>
      </section>

      <section className="panel">
        <h2 style={{ fontSize: 14, margin: "0 0 16px" }}>검토의견</h2>
        <div style={{ display: "flex", flexDirection: "column", gap: 8, marginBottom: 16 }}>
          {candidate.reviews.map((r) => (
            <div key={r.id} className="panel" style={{ padding: 10, background: r.is_final_approval ? "var(--navy-soft)" : "var(--panel-2)" }}>
              <div style={{ fontSize: 12, color: "var(--ink-muted)" }}>
                {r.is_final_approval ? "[최종승인] " : ""}
                {fmtDate(r.created_at)}
              </div>
              <div>{r.comment_text}</div>
            </div>
          ))}
          {candidate.reviews.length === 0 && <p style={{ color: "var(--ink-muted)" }}>아직 검토의견이 없습니다</p>}
        </div>

        <form onSubmit={submitComment} style={{ display: "flex", gap: 8 }}>
          <input
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            placeholder="검토 의견을 입력하세요"
            style={{ flex: 1, padding: 9, borderRadius: 8, border: "1px solid var(--border)" }}
          />
          <button className="tbtn primary" type="submit" disabled={submitting}>등록</button>
        </form>
      </section>
    </AppShell>
  );
}

const inp: React.CSSProperties = { padding: 9, borderRadius: 8, border: "1px solid var(--border)", fontSize: 13, fontFamily: "inherit" };
