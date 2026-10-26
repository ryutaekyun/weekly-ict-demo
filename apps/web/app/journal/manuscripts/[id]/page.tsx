"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import AppShell from "@/components/AppShell";
import { apiFetch, getCurrentUser, type CurrentUser } from "@/lib/api";
import {
  downloadFile, jAddComment, jAssign, jCompare, jConfirmPlagiarism, jConfirmProof, jDecide, jDeliberate, jFormatReview, jManuscript, jRequestRevision,
  jResolve, jReviewerCandidates, uploadForm, type JCompare, type JManuscript,
} from "@/lib/journalApi";

const inp: React.CSSProperties = { padding: 7, borderRadius: 8, border: "1px solid var(--border)", fontSize: 13, minWidth: 0 };
const ITEM_CLS: Record<string, string> = { pass: "rec", fail: "review", warn: "hold", info: "hold" };
const ITEM_LABEL: Record<string, string> = { pass: "통과", fail: "보완 필요", warn: "확인", info: "기준 미설정·안내" };
const PROOF_ITEMS: [string, string][] = [["source", "원문 출처"], ["figure_table_numbers", "그림·표 번호"], ["references", "참고문헌"], ["abbreviations", "약어"], ["language", "문장 오류"]];
const COMMENT_STATUS: Record<string, string> = { open: "미해결", answered: "저자 답변", resolved: "해결" };

export default function JournalManuscriptPage() {
  const { id } = useParams<{ id: string }>();
  const [me, setMe] = useState<CurrentUser | null>(null);
  const [ms, setMs] = useState<JManuscript | null>(null);
  const [reviewers, setReviewers] = useState<{ id: string; display_name: string; role: string; external: boolean }[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [asg, setAsg] = useState({ reviewer: "", round: 1, due: "", conflict: false, confirm: false });
  const [cmt, setCmt] = useState({ scope: "doc", anchor: "", text: "" });
  const [note, setNote] = useState("");
  const [decision, setDecision] = useState({ outcome: "", note: "" });
  const [cmp, setCmp] = useState<JCompare | null>(null);
  const [cmpPair, setCmpPair] = useState({ from: 1, to: 2 });
  const [proof, setProof] = useState<Record<string, boolean>>({});

  const load = useCallback(() => { jManuscript(id).then(setMs).catch((e) => setError(e instanceof Error ? e.message : "불러오기 실패")); }, [id]);
  useEffect(() => { getCurrentUser().then(setMe).catch(() => undefined); jReviewerCandidates().then(setReviewers).catch(() => undefined); }, []);
  useEffect(() => { load(); }, [load]);

  async function act<T>(fn: () => Promise<T>, ok?: string) {
    setError(null); setMessage(null); setBusy(true);
    try { await fn(); if (ok) setMessage(ok); load(); } catch (e) {
      setError(e instanceof Error ? e.message : "처리 실패");
    } finally { setBusy(false); }
  }

  if (!ms) return <AppShell>{error ? <p role="alert" style={{ color: "#b42318" }}>{error}</p> : <p>불러오는 중...</p>}</AppShell>;
  const canDecide = me?.role === "admin" || me?.role === "approver";
  const last = ms.versions[ms.versions.length - 1];
  const checks = last?.format_check.items ?? [];
  const reviewable = ["review_pending", "in_review", "revision_received", "deliberated"].includes(ms.status);

  return (
    <AppShell>
      <div style={{ marginBottom: 8 }}><Link href={`/journal/issues/${ms.issue_id}`} style={{ fontSize: 13 }}>← {ms.issue_label} 회차</Link></div>
      <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", marginBottom: 6 }}>
        <h1 style={{ fontSize: 19, fontWeight: 700, margin: 0 }}>{ms.title}</h1>
        <span className="pill review" data-testid="ms-status">{ms.status_label}</span>
        {ms.is_synthetic && <span className="pill hold">합성 테스트 원고</span>}
        <span className="pill hold">형식 검토: {{ not_checked: "미확정", ok: "이상 없음", needs_fix: "보완 필요" }[ms.format_status]}</span>
        <span className="pill hold">내용 검토: {{ pending: "대기", in_review: "진행 중", done: "완료" }[ms.content_status]}</span>
      </div>
      <div style={{ fontSize: 13, color: "var(--ink-muted)", marginBottom: 6 }}>
        저자 {ms.authors.map((a) => `${a.name}(${a.affiliation})`).join(", ") || ms.expert_name} · 제출 버전 {ms.version_count}건 · 저작권·이용 동의 {ms.copyright_confirmed ? "확인됨" : "확인 안 됨"}
      </div>
      {error && <p role="alert" style={{ color: "#b42318", fontSize: 13 }}>{error}</p>}
      {message && <p role="status" style={{ color: "var(--ok)", fontSize: 13 }}>{message}</p>}
      {ms.review_validity?.needs_rereview && <p role="alert" style={{ fontSize: 13, color: "#9a4b00" }}>⚠ {ms.review_validity.message} (변경 비율 {Math.round(ms.review_validity.change_ratio * 100)}%)</p>}

      <section className="panel" style={{ marginBottom: 12 }}>
        <b>형식 점검(최신 버전)</b>
        <p style={{ fontSize: 12, color: "var(--ink-muted)", margin: "2px 0 6px" }}>형식 검토는 내용의 학술·기술 타당성 검토와 별개입니다. 분량·제출서류는 관리자가 설정한 기준만 적용합니다.</p>
        {checks.map((c) => <div key={c.key} style={{ fontSize: 13 }}><span className={`pill ${ITEM_CLS[c.status]}`}>{ITEM_LABEL[c.status]}</span> {c.label}: {c.detail}</div>)}
        {last?.scan.warnings?.map((w) => <div key={w} style={{ fontSize: 12.5, color: "#9a4b00" }}>보안 검사 안내: {w}</div>)}
        {["received", "format_fix_needed"].includes(ms.status) && (
          <div style={{ display: "flex", gap: 8, marginTop: 8, flexWrap: "wrap" }}>
            <button className="tbtn primary" disabled={busy} onClick={() => act(() => jFormatReview(id, "ok"), "형식 검토를 확정했습니다 — 내용 검토 대기")}>형식 이상 없음 확정</button>
            <input aria-label="형식 보완 사유" placeholder="형식 보완 요청 사유" value={note} onChange={(e) => setNote(e.target.value)} style={{ ...inp, minWidth: 260 }} />
            <button className="tbtn" disabled={busy || !note.trim()} onClick={() => act(() => jFormatReview(id, "needs_fix", note), "형식 보완을 요청했습니다").then(() => setNote(""))}>형식 보완 요청</button>
          </div>
        )}
      </section>

      <section className="panel" style={{ marginBottom: 12 }}>
        <b>제출·수정·교정 버전(원본 파일 보존)</b>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12.5, marginTop: 6 }}>
          <thead><tr style={{ textAlign: "left" }}>{["버전", "구분", "파일", "크기·SHA-256", "단어/표/그림", "제출", ""].map((h) => <th key={h} style={{ padding: "4px 6px" }}>{h}</th>)}</tr></thead>
          <tbody>
            {ms.versions.map((v) => (
              <tr key={v.id} style={{ borderTop: "1px solid var(--border)" }}>
                <td style={{ padding: "4px 6px" }}>v{v.version_no}</td><td style={{ padding: "4px 6px" }}>{v.kind_label}</td><td style={{ padding: "4px 6px" }}>{v.file_name}</td>
                <td style={{ padding: "4px 6px" }}>{Math.round(v.file_size / 1024)}KB · {v.sha256.slice(0, 10)}…</td>
                <td style={{ padding: "4px 6px" }}>{String(v.extract.words ?? "-")}/{String(v.extract.tables ?? "?")}/{String(v.extract.figures ?? "?")}</td>
                <td style={{ padding: "4px 6px" }}>{v.uploaded_by} {v.uploaded_at.slice(0, 10)}</td>
                <td style={{ padding: "4px 6px" }}><button className="tbtn" aria-label={`v${v.version_no} 다운로드`} onClick={() => downloadFile(`/journal/manuscripts/${id}/versions/${v.id}/download`, v.file_name).catch((e) => setError(e.message))}>다운로드</button></td>
              </tr>
            ))}
          </tbody>
        </table>
        {ms.versions.length >= 2 && (
          <div style={{ marginTop: 8, display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
            비교: v<input aria-label="비교 기준 버전" type="number" min={1} value={cmpPair.from} onChange={(e) => setCmpPair({ ...cmpPair, from: Number(e.target.value) })} style={{ ...inp, width: 60 }} />
            → v<input aria-label="비교 대상 버전" type="number" min={1} value={cmpPair.to} onChange={(e) => setCmpPair({ ...cmpPair, to: Number(e.target.value) })} style={{ ...inp, width: 60 }} />
            <button className="tbtn" onClick={() => jCompare(id, cmpPair.from, cmpPair.to).then(setCmp).catch((e) => setError(e.message))}>버전 비교</button>
          </div>
        )}
        {cmp && (
          <div style={{ marginTop: 8, fontSize: 13 }} aria-label="버전 비교 결과">
            <div>v{cmp.from_version} → v{cmp.to_version}: 수정 {cmp.counts.modified} · 추가 {cmp.counts.added} · 삭제 {cmp.counts.deleted} 문단{cmp.identical_text ? " (본문 텍스트 동일)" : ""}</div>
            {cmp.needs_original_compare && <div style={{ color: "#9a4b00" }}>원본 파일 비교 필요: {cmp.original_compare_reasons.join(" / ")}</div>}
            {cmp.changes.slice(0, 12).map((c, i) => (
              <div key={i} style={{ borderLeft: `3px solid ${c.type === "added" ? "#2f7d62" : c.type === "deleted" ? "#b42318" : "#9a4b00"}`, paddingLeft: 8, margin: "4px 0" }}>
                <b>{{ added: "추가", deleted: "삭제", modified: "수정" }[c.type]}</b>{c.similarity != null ? ` (유사도 ${c.similarity})` : ""}
                {c.old && <div style={{ color: "#b42318" }}>− {c.old}</div>}{c.new && <div style={{ color: "#2f7d62" }}>+ {c.new}</div>}
              </div>
            ))}
            <b>검토 의견 ↔ 수정 대응(수정 완료 여부를 자동 확정하지 않음)</b>
            {cmp.comment_mapping.map((m) => <div key={m.id} style={{ fontSize: 12.5 }}>· {m.text.slice(0, 40)} → {m.note}</div>)}
            <div style={{ color: "var(--ink-muted)", fontSize: 12 }}>{cmp.notice}</div>
          </div>
        )}
      </section>

      <section className="panel" style={{ marginBottom: 12 }}>
        <b>검토자·심의위원 배정</b>
        {(ms.assignments ?? []).map((a) => (
          <div key={a.id} style={{ fontSize: 13, borderTop: "1px solid var(--border)", padding: "4px 0" }}>
            {a.round}차 · {a.reviewer_name} · 기한 {a.due_date ?? "-"}{a.overdue ? " (지연)" : ""} · {{ assigned: "배정", in_progress: "검토 중", completed: "검토 완료" }[a.status]}
            {a.conflict_declared && <span className="pill review" style={{ marginLeft: 4 }}>이해상충 신고</span>}
            {a.recommendation && <span> · 추천 의견: {ms.outcomes.find((o) => o.key === a.recommendation)?.label} — {a.summary_opinion}</span>}
          </div>
        ))}
        {reviewable && (
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 8, alignItems: "center" }}>
            <select aria-label="검토자 선택" value={asg.reviewer} onChange={(e) => { const v = e.target.value; setAsg((a) => ({ ...a, reviewer: v })); }} style={inp}>
              <option value="">검토자 선택</option>
              {reviewers.map((r) => <option key={r.id} value={r.id}>{r.display_name}{r.external ? " (외부)" : ""}</option>)}
            </select>
            <select aria-label="검토 차수" value={asg.round} onChange={(e) => { const v = Number(e.target.value); setAsg((a) => ({ ...a, round: v })); }} style={inp}>
              <option value={1}>1차</option><option value={2}>2차</option>
            </select>
            <input aria-label="검토 기한" type="date" value={asg.due} onChange={(e) => setAsg({ ...asg, due: e.target.value })} style={inp} />
            <label style={{ fontSize: 12.5 }}><input type="checkbox" checked={asg.conflict} onChange={(e) => setAsg({ ...asg, conflict: e.target.checked })} /> 이해상충 확인됨</label>
            <label style={{ fontSize: 12.5 }}><input type="checkbox" checked={asg.confirm} onChange={(e) => setAsg({ ...asg, confirm: e.target.checked })} /> 경고를 확인하고 배정</label>
            <button className="tbtn primary" disabled={busy || !asg.reviewer} onClick={() => act(() => jAssign(id, { reviewer_user_id: asg.reviewer, round: asg.round, due_date: asg.due || null, conflict_declared: asg.conflict, confirm_conflict: asg.confirm }), "검토자를 배정했습니다")}>검토자 배정</button>
          </div>
        )}
      </section>

      <section className="panel" style={{ marginBottom: 12 }}>
        <b>검토 의견·수정 요청</b>
        {ms.comments.map((c) => (
          <div key={c.id} style={{ borderTop: "1px solid var(--border)", padding: "6px 0", fontSize: 13 }}>
            <span className={`pill ${c.status === "resolved" ? "rec" : c.status === "answered" ? "hold" : "review"}`}>{COMMENT_STATUS[c.status]}</span>{" "}
            [{{ doc: "문서 전체", paragraph: "문단", table: "표", figure: "그림" }[c.scope]}{c.version_no ? ` · v${c.version_no}` : ""}] {c.author_name}: {c.text}
            {c.anchor_text && <div style={{ fontSize: 12, color: "var(--ink-muted)" }}>대상: {c.anchor_text.slice(0, 80)}</div>}
            {c.author_reply && <div style={{ fontSize: 12.5, background: "var(--panel-2)", padding: 4, borderRadius: 6 }}>저자 답변: {c.author_reply}</div>}
            {c.status !== "resolved" && <button className="tbtn" style={{ marginTop: 4 }} onClick={() => act(() => jResolve(id, c.id), "의견을 해결 처리했습니다")}>해결 처리</button>}
          </div>
        ))}
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 8 }}>
          <select aria-label="의견 대상" value={cmt.scope} onChange={(e) => { const v = e.target.value; setCmt((c) => ({ ...c, scope: v })); }} style={inp}>
            <option value="doc">문서 전체</option><option value="paragraph">문단</option><option value="table">표</option><option value="figure">그림</option>
          </select>
          <input aria-label="의견 대상 문구" placeholder="대상 문단·표·그림 문구(선택)" value={cmt.anchor} onChange={(e) => setCmt({ ...cmt, anchor: e.target.value })} style={{ ...inp, minWidth: 220 }} />
          <input aria-label="의견 내용" placeholder="의견 내용" value={cmt.text} onChange={(e) => setCmt({ ...cmt, text: e.target.value })} style={{ ...inp, flex: 1, minWidth: 240 }} />
          <button className="tbtn" disabled={busy || !cmt.text.trim()} onClick={() => act(() => jAddComment(id, { scope: cmt.scope, anchor_text: cmt.anchor || null, text: cmt.text }), "의견을 저장했습니다").then(() => setCmt({ scope: "doc", anchor: "", text: "" }))}>의견 저장</button>
        </div>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 8 }}>
          {["in_review", "revision_received"].includes(ms.status) && <button className="tbtn" disabled={busy} onClick={() => act(() => jRequestRevision(id), "저자에게 수정을 요청했습니다")}>저자에게 수정 요청</button>}
          {["in_review", "revision_received"].includes(ms.status) && <button className="tbtn" disabled={busy} onClick={() => act(() => jDeliberate(id), "심의 대기로 전환했습니다")}>검토 완료 → 심의</button>}
        </div>
      </section>

      {ms.status === "deliberated" && (
        <section className="panel" style={{ marginBottom: 12 }}>
          <b>심의 결과 확정</b>
          <p style={{ fontSize: 12, color: "var(--ink-muted)", margin: "2px 0 6px" }}>검토자 추천과 형식 점검은 참고 자료입니다. 게재 여부는 승인권자·관리자가 직접 확정하며 자동 점수로 정하지 않습니다.</p>
          {canDecide ? (
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              <select aria-label="심의 결과" value={decision.outcome} onChange={(e) => { const v = e.target.value; setDecision((d) => ({ ...d, outcome: v })); }} style={inp}>
                <option value="">결과 선택</option>{ms.outcomes.map((o) => <option key={o.key} value={o.key}>{o.label}</option>)}
              </select>
              <input aria-label="심의 의견" placeholder="심의 의견" value={decision.note} onChange={(e) => setDecision({ ...decision, note: e.target.value })} style={{ ...inp, flex: 1, minWidth: 220 }} />
              <button className="tbtn primary" disabled={busy || !decision.outcome} onClick={() => act(() => jDecide(id, decision.outcome, decision.note), "심의 결과를 확정했습니다")}>결과 확정</button>
            </div>
          ) : <p style={{ fontSize: 13 }}>승인권자·관리자만 확정할 수 있습니다.</p>}
        </section>
      )}
      {(ms.decisions ?? []).length > 0 && (
        <section className="panel" style={{ marginBottom: 12, fontSize: 13 }}>
          <b>심의 이력</b>
          {(ms.decisions ?? []).map((d) => <div key={d.id}>{d.round}차 · {ms.outcomes.find((o) => o.key === d.outcome)?.label} · {d.is_final ? "최종" : "수정 요청"} · {d.decided_by} {d.decided_at.slice(0, 10)}{d.note ? ` — ${d.note}` : ""}</div>)}
        </section>
      )}

      {ms.status === "accepted" && (
        <section className="panel" style={{ marginBottom: 12 }}>
          <b>교정·최종 교정 확인</b>
          <p style={{ fontSize: 12, color: "var(--ink-muted)", margin: "2px 0 6px" }}>교정본은 게재 확정 원고에 새 버전으로 올립니다(원본·수정본은 그대로 보존). 저자의 기술적 주장·결론은 편집자가 임의로 바꾸지 않습니다.</p>
          <form onSubmit={(e) => { e.preventDefault(); const f = (e.currentTarget.elements.namedItem("proof") as HTMLInputElement).files?.[0]; if (!f) { setError("교정본 DOCX 파일을 선택하세요"); return; }
            const fd = new FormData(); fd.append("file", f); fd.append("kind", "proofread"); act(() => uploadForm(`/journal/manuscripts/${id}/versions`, fd), "교정본을 올렸습니다 — 최종 교정 확인을 다시 받아야 합니다"); }}>
            <input aria-label="교정본 파일" name="proof" type="file" accept=".docx,.pdf" /> <button className="tbtn" type="submit" disabled={busy}>교정본 올리기</button>
          </form>
          <div style={{ marginTop: 6, fontSize: 13 }}>
            {PROOF_ITEMS.map(([k, l]) => <label key={k} style={{ marginRight: 12 }}><input type="checkbox" aria-label={`교정 점검 ${l}`} checked={!!proof[k]} onChange={(e) => setProof({ ...proof, [k]: e.target.checked })} /> {l}</label>)}
            <button className="tbtn primary" disabled={busy} onClick={() => act(() => jConfirmProof(id, proof), "최종 교정을 확인했습니다")}>최종 교정 확인</button>
            {ms.proof_confirmed && <span className="pill rec" style={{ marginLeft: 6 }}>최종 교정 확인됨</span>}
          </div>
        </section>
      )}

      <section className="panel" style={{ marginBottom: 12 }}>
        <b>표절검사 결과·제출서류·저작권</b>
        <p style={{ fontSize: 12, color: "#9a4b00", margin: "2px 0 6px" }}>{ms.plagiarism_notice}</p>
        {(ms.plagiarism ?? []).map((p) => (
          <div key={p.id} style={{ fontSize: 13 }}>{p.service_name ?? "결과 파일"} · {p.file_name} · 유사도(담당자 입력) {p.similarity_pct ?? "-"}% · {p.status === "confirmed" ? "담당자 확인함" : "업로드됨(미확인)"}
            {p.status !== "confirmed" && <button className="tbtn" style={{ marginLeft: 6 }} onClick={() => act(() => jConfirmPlagiarism(id, p.id), "결과 확인을 기록했습니다")}>확인 기록</button>}</div>
        ))}
        <form onSubmit={(e) => { e.preventDefault(); const el = e.currentTarget.elements; const f = (el.namedItem("plag") as HTMLInputElement).files?.[0]; if (!f) { setError("결과 파일을 선택하세요"); return; }
          const fd = new FormData(); fd.append("file", f); fd.append("service_name", (el.namedItem("svc") as HTMLInputElement).value); const pct = (el.namedItem("pct") as HTMLInputElement).value; if (pct) fd.append("similarity_pct", pct);
          act(() => uploadForm(`/journal/manuscripts/${id}/plagiarism`, fd), "표절검사 결과 파일을 올렸습니다(확인 기록 전까지 '미확인')"); }} style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 6 }}>
          <input aria-label="표절검사 결과 파일" name="plag" type="file" accept=".pdf,.docx,.png,.jpg,.xlsx,.txt" />
          <input aria-label="검사 서비스명" name="svc" placeholder="검사 서비스명" style={inp} />
          <input aria-label="유사도(%)" name="pct" placeholder="유사도(%)" style={{ ...inp, width: 90 }} />
          <button className="tbtn" type="submit" disabled={busy}>결과 파일 올리기</button>
        </form>
        <div style={{ fontSize: 13, marginTop: 8 }}>
          제출서류: {ms.attachments.length ? ms.attachments.map((a) => (
            <button key={a.id} className="tbtn" style={{ marginRight: 4 }} onClick={() => downloadFile(`/journal/manuscripts/${id}/attachments/${a.id}/download`, a.file_name).catch((e) => setError(e.message))}>{a.doc_type}: {a.file_name}</button>
          )) : "없음"}
        </div>
        <label style={{ fontSize: 13, display: "block", marginTop: 6 }}>
          <input type="checkbox" aria-label="저작권·이용 동의 확인" checked={ms.copyright_confirmed} onChange={(e) => { const v = e.target.checked; act(() => apiFetch(`/journal/manuscripts/${id}`, { method: "PATCH", body: JSON.stringify({ lock_version: ms.lock_version, copyright_confirmed: v }) }), "저작권·이용 동의 확인 여부를 저장했습니다"); }} /> 저자의 저작권·이용 동의를 확인함
        </label>
        {ms.third_party_note && <div style={{ fontSize: 12.5, color: "var(--ink-muted)" }}>제3자 자료 사용 기록: {ms.third_party_note}</div>}
      </section>
    </AppShell>
  );
}
