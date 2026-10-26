"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import AppShell from "@/components/AppShell";
import { downloadFile, pConflict, pReviewComment, pReviewComplete, pReviewDetail, pReviewResolve, type PReviewDetail } from "@/lib/journalApi";

const inp: React.CSSProperties = { padding: 8, borderRadius: 8, border: "1px solid var(--border)", fontSize: 13, minWidth: 0 };

export default function PortalReviewPage() {
  const { id } = useParams<{ id: string }>();
  const [d, setD] = useState<PReviewDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [cmt, setCmt] = useState({ scope: "doc", anchor: "", text: "" });
  const [fin, setFin] = useState({ rec: "", opinion: "" });
  const [cNote, setCNote] = useState("");

  const load = useCallback(() => { pReviewDetail(id).then(setD).catch((e) => setError(e instanceof Error ? e.message : "불러오기 실패")); }, [id]);
  useEffect(() => { load(); }, [load]);

  async function run(fn: () => Promise<unknown>, ok: string) {
    setError(null); setMessage(null); setBusy(true);
    try { await fn(); setMessage(ok); load(); } catch (e) { setError(e instanceof Error ? e.message : "처리 실패"); } finally { setBusy(false); }
  }
  if (!d) return <AppShell>{error ? <p role="alert" style={{ color: "#b42318" }}>{error}</p> : <p>불러오는 중...</p>}</AppShell>;
  const a = d.assignment;
  const done = a.status === "completed";

  return (
    <AppShell>
      <div style={{ marginBottom: 8 }}><Link href="/portal" style={{ fontSize: 13 }}>← 원고 검토 포털</Link></div>
      <h1 style={{ fontSize: 19, fontWeight: 700, marginBottom: 4 }}>{d.manuscript.title}</h1>
      <div style={{ fontSize: 13, marginBottom: 6 }}>{d.manuscript.issue_label} · {a.round}차 검토 · 기한 {a.due_date ?? "-"} · <span className="pill hold">{{ assigned: "배정됨", in_progress: "검토 중", completed: "검토 완료" }[a.status]}</span></div>
      <p style={{ fontSize: 12, color: "var(--ink-muted)" }}>{d.notice}</p>
      {error && <p role="alert" style={{ color: "#b42318", fontSize: 13 }}>{error}</p>}
      {message && <p role="status" style={{ color: "var(--ok)", fontSize: 13 }}>{message}</p>}

      <section className="panel" style={{ marginBottom: 12, fontSize: 13 }}>
        <b>원고 정보</b>
        <div>저자: {d.manuscript.authors.map((x) => `${x.name}(${x.affiliation})`).join(", ")}</div>
        {d.manuscript.summary && <div>요약: {d.manuscript.summary}</div>}
        {d.versions.map((v) => (
          <div key={v.id} style={{ marginTop: 4 }}>v{v.version_no} · {v.file_name} · {v.words ?? "-"}단어{v.note ? ` · ${v.note}` : ""}
            <button className="tbtn" style={{ marginLeft: 6 }} onClick={() => downloadFile(`/journal/portal/reviews/${id}/versions/${v.id}/download`, v.file_name).catch((e) => setError(e.message))}>원고 다운로드</button></div>
        ))}
      </section>

      <section className="panel" style={{ marginBottom: 12, fontSize: 13 }}>
        <b>이해상충 확인</b>
        <p style={{ fontSize: 12, color: "var(--ink-muted)", margin: "2px 0 6px" }}>검토 전에 저자와의 이해상충(공동연구·소속·친족·경쟁 관계 등) 여부를 확인해야 검토를 완료할 수 있습니다.</p>
        {a.conflict_checked ? <div>확인함 — 이해상충 {a.conflict_declared ? "있음" : "없음"}{a.conflict_note ? ` (${a.conflict_note})` : ""}</div> : (
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            <input aria-label="이해상충 메모" placeholder="메모(선택)" value={cNote} onChange={(e) => setCNote(e.target.value)} style={inp} />
            <button className="tbtn primary" disabled={busy} onClick={() => run(() => pConflict(id, false, cNote || undefined), "이해상충이 없음을 확인했습니다")}>이해상충 없음 확인</button>
            <button className="tbtn" disabled={busy} onClick={() => run(() => pConflict(id, true, cNote || undefined), "이해상충을 신고했습니다 — 편집 담당자가 확인합니다")}>이해상충 있음 신고</button>
          </div>
        )}
      </section>

      <section className="panel" style={{ marginBottom: 12 }}>
        <b>내 검토 의견</b>
        {d.comments.map((c) => (
          <div key={c.id} style={{ borderTop: "1px solid var(--border)", padding: "6px 0", fontSize: 13 }}>
            <span className={`pill ${c.status === "resolved" ? "rec" : c.status === "answered" ? "hold" : "review"}`}>{{ open: "미해결", answered: "저자 답변", resolved: "해결" }[c.status]}</span>{" "}
            [{{ doc: "문서 전체", paragraph: "문단", table: "표", figure: "그림" }[c.scope]}] {c.text}
            {c.anchor_text && <div style={{ fontSize: 12, color: "var(--ink-muted)" }}>대상: {c.anchor_text.slice(0, 80)}</div>}
            {c.author_reply && <div style={{ fontSize: 12.5, background: "var(--panel-2)", padding: 4, borderRadius: 6 }}>저자 답변: {c.author_reply}</div>}
            {c.status === "answered" && <button className="tbtn" style={{ marginTop: 4 }} onClick={() => run(() => pReviewResolve(id, c.id), "의견을 해결 처리했습니다")}>수정 확인 후 해결 처리</button>}
          </div>
        ))}
        {!done && (
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 8 }}>
            <select aria-label="의견 대상" value={cmt.scope} onChange={(e) => { const v = e.target.value; setCmt((c) => ({ ...c, scope: v })); }} style={inp}>
              <option value="doc">문서 전체</option><option value="paragraph">문단</option><option value="table">표</option><option value="figure">그림</option>
            </select>
            <input aria-label="의견 대상 문구" placeholder="대상 문단·표·그림 문구(선택)" value={cmt.anchor} onChange={(e) => setCmt({ ...cmt, anchor: e.target.value })} style={{ ...inp, minWidth: 220 }} />
            <input aria-label="검토 의견" placeholder="검토 의견" value={cmt.text} onChange={(e) => setCmt({ ...cmt, text: e.target.value })} style={{ ...inp, flex: 1, minWidth: 240 }} />
            <button className="tbtn" disabled={busy || !cmt.text.trim()} onClick={() => run(() => pReviewComment(id, { scope: cmt.scope, anchor_text: cmt.anchor || null, text: cmt.text }), "의견을 저장했습니다").then(() => setCmt({ scope: "doc", anchor: "", text: "" }))}>의견 저장</button>
          </div>
        )}
      </section>

      <section className="panel">
        <b>검토 완료</b>
        {done ? <div style={{ fontSize: 13 }}>검토를 완료했습니다 — 추천 의견: {d.outcomes.find((o) => o.key === a.recommendation)?.label}. {a.summary_opinion}</div> : (
          <div style={{ display: "grid", gap: 6, marginTop: 6 }}>
            <select aria-label="추천 의견" value={fin.rec} onChange={(e) => { const v = e.target.value; setFin((f) => ({ ...f, rec: v })); }} style={inp}>
              <option value="">추천 의견 선택(참고용)</option>{d.outcomes.map((o) => <option key={o.key} value={o.key}>{o.label}</option>)}
            </select>
            <textarea aria-label="종합 의견" placeholder="종합 의견" rows={3} value={fin.opinion} onChange={(e) => setFin({ ...fin, opinion: e.target.value })} style={inp} />
            <div><button className="tbtn primary" disabled={busy || !fin.rec || !fin.opinion.trim()} onClick={() => run(() => pReviewComplete(id, fin.rec, fin.opinion), "검토를 완료했습니다")}>검토 완료 제출</button></div>
          </div>
        )}
      </section>
    </AppShell>
  );
}
