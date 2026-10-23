"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import AppShell from "@/components/AppShell";
import { apiFetch, UnauthorizedError, updateCandidate, type CandidateDetail } from "@/lib/api";
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
  const [saveMsg, setSaveMsg] = useState<string | null>(null);

  function load() {
    apiFetch<CandidateDetail>(`/candidates/${params.id}`)
      .then((c) => {
        setCandidate(c);
        setEditTitle(c.title);
        setEditReason(c.recommended_reason ?? "");
      })
      .catch((err) => {
        if (err instanceof UnauthorizedError) { router.push("/login"); return; }
        setError(err instanceof Error ? err.message : "불러오기 실패");
      });
  }

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
      await updateCandidate(params.id, { title: editTitle, recommended_reason: editReason });
      setSaveMsg("저장되었습니다");
      load();
    } catch (err) {
      setSaveMsg(err instanceof Error ? `저장 실패: ${err.message}` : "저장 실패");
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

      {candidate.summary && <p style={{ fontSize: 13.5 }}>{candidate.summary}</p>}

      {score ? (
        <section className="panel" style={{ marginBottom: 16 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <h2 style={{ fontSize: 14, margin: 0 }}>AI 추천 평가 ({METHOD_LABELS[score.method] ?? score.method})</h2>
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

      <section className="panel" style={{ marginBottom: 16 }}>
        <h2 style={{ fontSize: 14, margin: "0 0 10px" }}>제목·추천 근거 수정</h2>
        <form onSubmit={saveEdits} style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <input value={editTitle} onChange={(e) => setEditTitle(e.target.value)} style={inp} placeholder="제목" />
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
