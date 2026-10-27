"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  aiCancel, aiCandidate, aiEstimate, aiInsert, aiList, aiGet, aiReviewClaim, aiRun, aiStatus,
  type AiAnalysis, type AiClaim, type AiEstimate, type AiKind, type AiStatus,
} from "@/lib/aiApi";

const VERIFY_LABEL: Record<string, string> = {
  ai_unverified: "AI 생성·연구원 미검증", insufficient: "근거 부족", mismatch: "근거 불일치", researcher_verified: "연구원 검증 완료",
};
const VERIFY_CLASS: Record<string, string> = { ai_unverified: "hold", insufficient: "review", mismatch: "review", researcher_verified: "rec" };
const EVID_LABEL: Record<string, string> = {
  found: "원문 근거 확인", not_found: "검증 실패(원문에 없음)", value_mismatch: "근거 불일치(날짜·수치)", no_evidence: "근거 없음·확인 필요",
  interpretation: "AI 해석(원문 사실 아님)", gap: "확인 필요 사항",
};
const EVID_CLASS: Record<string, string> = { found: "rec", not_found: "review", value_mismatch: "review", no_evidence: "review", interpretation: "hold", gap: "hold" };
const STATE_LABEL: Record<string, string> = { idle: "분석 대기", running: "분석 중", done: "분석 완료·미검증", failed: "분석 실패", config: "AI 설정 필요", hold: "분석 보류(근거 부족)" };
const box: React.CSSProperties = { border: "1px solid var(--border)", borderRadius: 10, padding: 10, marginBottom: 8, background: "var(--panel)" };
const inp: React.CSSProperties = { padding: 7, borderRadius: 8, border: "1px solid var(--border)", fontSize: 13, width: "100%" };

type Props = {
  kind: AiKind; targetId: string; title: string; buttonLabel: string; documentIds?: string[]; testId?: string;
  existingCandidates?: { id: string; title: string }[];
  manuscript?: { id: string; getLockVersion: () => Promise<number>; onInserted: () => void };
  onCandidateLinked?: (candidateId: string, created: boolean) => void;
};

export default function AiPanel({ kind, targetId, title, buttonLabel, documentIds, testId = "ai-panel", existingCandidates = [], manuscript, onCandidateLinked }: Props) {
  const [status, setStatus] = useState<AiStatus | null>(null);
  const [estimate, setEstimate] = useState<AiEstimate | null>(null);
  const [analysis, setAnalysis] = useState<AiAnalysis | null>(null);
  const [state, setState] = useState<"idle" | "running" | "failed">("idle");
  const [error, setError] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [selected, setSelected] = useState<Record<string, boolean>>({});
  const [edits, setEdits] = useState<Record<string, string>>({});
  const [openEv, setOpenEv] = useState<Record<string, boolean>>({});
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [candForm, setCandForm] = useState({ title: "", summary: "", attach: "" });
  const [forceNext, setForceNext] = useState(false);
  const [savedCandidate, setSavedCandidate] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const loadLatest = useCallback(async () => {
    try {
      const list = await aiList(targetId, kind);
      const latest = list.find((a) => a.status === "completed" || a.status === "insufficient_evidence");
      if (latest) setAnalysis(await aiGet(latest.id));
    } catch { /* 이력이 없으면 비워 둔다 */ }
  }, [targetId, kind]);

  useEffect(() => { aiStatus().then(setStatus).catch(() => setStatus(null)); loadLatest(); }, [loadLatest]);

  useEffect(() => {
    if (analysis?.kind === "candidate" && analysis.sections) {
      const t = analysis.sections.find((s) => s.key === "title")?.claims[0]?.text ?? "";
      setCandForm((f) => (f.title ? f : { ...f, title: t.replace(/^\[모의\]\s*/, "") }));
    }
  }, [analysis]);

  async function openEstimate(force = false) {
    setError(null); setMsg(null); setForceNext(force);
    try { setEstimate(await aiEstimate(kind, targetId, documentIds)); } catch (e) { setError(e instanceof Error ? e.message : "예상 비용 계산 실패"); }
  }

  async function execute(force = false) {
    setError(null); setMsg(null); setState("running"); setEstimate(null);
    const ac = new AbortController();
    abortRef.current = ac;
    try {
      const res = await aiRun(kind, targetId, { document_ids: documentIds, force }, ac.signal);
      setAnalysis(await aiGet(res.id).catch(() => res));
      setSelected({}); setEdits({});
      setState("idle");
      if (res.reused) setMsg("같은 원문 버전의 이전 분석 결과를 다시 보여줍니다(AI 호출·비용 없음). 새로 분석하려면 '다시 분석'을 누르세요.");
    } catch (e) {
      setState(ac.signal.aborted ? "idle" : "failed");
      setError(ac.signal.aborted ? "요청을 취소했습니다." : e instanceof Error ? e.message : "분석 실패");
    }
  }

  async function cancel() {
    abortRef.current?.abort();
    try {
      const running = (await aiList(targetId, kind)).find((a) => a.status === "running");
      if (running) await aiCancel(running.id);
    } catch { /* 이미 끝난 요청이면 무시 */ }
  }

  async function review(c: AiClaim, action: "verify" | "reject" | "reset") {
    setError(null);
    try {
      const needNote = action === "verify" && c.claim_type === "fact" && c.evidence_status !== "found";
      const r = await aiReviewClaim(c.id, action, notes[c.id]);
      setAnalysis((a) => a && {
        ...a, verification_status: r.verification_status,
        sections: a.sections?.map((s) => ({ ...s, claims: s.claims.map((x) => (x.id === c.id ? r.claim : x)) })),
      });
      if (needNote) setMsg("원문 대조 사유와 함께 검증 완료로 표시했습니다.");
    } catch (e) { setError(e instanceof Error ? e.message : "검토 저장 실패"); }
  }

  async function insert() {
    if (!manuscript || !analysis) return;
    const ids = Object.keys(selected).filter((k) => selected[k]);
    if (!ids.length) { setError("원고에 넣을 문장을 먼저 선택하세요."); return; }
    setError(null);
    try {
      const lock = await manuscript.getLockVersion(); // 저장 대기 중인 연구원 수정을 먼저 저장해 최신 버전을 기준으로 삼는다
      const r = await aiInsert(analysis.id, { manuscript_id: manuscript.id, claim_ids: ids, lock_version: lock, edited_texts: Object.fromEntries(ids.filter((i) => edits[i]).map((i) => [i, edits[i]])) });
      manuscript.onInserted();
      setSelected({});
      setMsg(`${r.inserted}문장을 원고 끝에 삽입했습니다(각주 ${r.footnotes_created}건, 모두 미검증). ${r.note}`);
      setAnalysis(await aiGet(analysis.id));
    } catch (e) { setError(e instanceof Error ? e.message : "삽입 실패"); }
  }

  async function saveCandidate() {
    if (!analysis) return;
    setError(null);
    try {
      const r = await aiCandidate(analysis.id, { title: candForm.title, summary: candForm.summary || undefined, attach_to_candidate_id: candForm.attach || undefined });
      setMsg(r.created ? "연구원이 수정한 내용으로 후보주제를 등록했습니다(상태는 AI가 정하지 않음)." : "기존 후보주제에 이 분석을 연결했습니다.");
      setSavedCandidate(r.candidate_id);
      onCandidateLinked?.(r.candidate_id, r.created);
    } catch (e) { setError(e instanceof Error ? e.message : "후보 등록 실패"); }
  }

  const stateKey = !status?.configured ? "config" : state === "running" ? "running" : state === "failed" ? "failed" : analysis?.status === "insufficient_evidence" ? "hold" : analysis ? "done" : "idle";
  const isDraft = kind === "draft" || kind === "outline";

  return (
    <section className="panel" style={{ marginBottom: 16 }} data-testid={testId}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
        <h2 style={{ fontSize: 14, margin: 0 }}>{title}</h2>
        <span className="pill hold" data-testid="ai-state">{STATE_LABEL[stateKey]}</span>
        {status?.is_mock && <span className="pill review" title="개발·테스트 전용">모의 응답(테스트용)</span>}
        <button className="tbtn primary" data-testid="ai-run" disabled={!status?.configured || state === "running"} onClick={() => openEstimate(false)}>{buttonLabel}</button>
        {state === "running" && <button className="tbtn" onClick={cancel}>취소</button>}
        {analysis && <button className="tbtn" disabled={!status?.configured || state === "running"} onClick={() => openEstimate(true)}>다시 분석</button>}
      </div>
      {!status?.configured && (
        <p data-testid="ai-config-needed" style={{ fontSize: 12.5, color: "var(--ink-muted)", margin: "8px 0 0" }}>
          {status?.message ?? "AI 설정 필요 — 서버에 AI 공급자·키가 설정되지 않았습니다."} 기존 규칙 기반 분석 결과는 이 화면에서 그대로 확인할 수 있습니다.
        </p>
      )}
      {error && <p role="alert" data-testid="ai-error" style={{ color: "var(--bad)", fontSize: 13 }}>{error}</p>}
      {msg && <p role="status" style={{ color: "var(--ok)", fontSize: 13 }}>{msg}</p>}

      {estimate && (
        <div style={{ ...box, marginTop: 10 }} data-testid="ai-estimate">
          <b style={{ fontSize: 13 }}>실행 전 확인</b>
          <ul style={{ fontSize: 12.5, margin: "6px 0" }}>
            {estimate.documents.map((d) => <li key={d.id}>{d.title} · {d.org ?? "-"} · {d.published ?? "발표일 미상"} · {d.chars.toLocaleString()}자{d.truncated ? "(앞부분만)" : ""}</li>)}
          </ul>
          {estimate.skipped.map((s, i) => <p key={i} style={{ fontSize: 12, color: "var(--ink-muted)", margin: "2px 0" }}>제외: {s}</p>)}
          <p style={{ fontSize: 12.5, margin: "6px 0" }}>
            공급자 {estimate.provider}{estimate.model ? ` / ${estimate.model}` : ""} · 예상 입력 {estimate.est_input_tokens.toLocaleString()}토큰 · 예상 출력 최대 {estimate.est_output_tokens.toLocaleString()}토큰 ·
            예상 비용 약 <b>${estimate.est_cost_usd}</b>{estimate.is_mock ? " (모의 응답 — 비용 없음)" : ""}
          </p>
          <p style={{ fontSize: 11.5, color: "var(--ink-muted)", margin: "0 0 6px" }}>{estimate.price_note} 원문 공개자료만 외부 AI 서비스로 전송됩니다.</p>
          {estimate.existing_candidate_ids.length > 0 && <p style={{ fontSize: 12, color: "var(--warn)" }}>이 이슈에는 이미 후보주제 {estimate.existing_candidate_ids.length}건이 있습니다. 결과는 기존 후보에 연결할 수 있습니다.</p>}
          {estimate.blockers.map((b, i) => <p key={i} role="alert" style={{ color: "var(--bad)", fontSize: 12.5 }}>{b}</p>)}
          <button className="tbtn primary" data-testid="ai-confirm" disabled={estimate.blockers.length > 0} onClick={() => execute(forceNext)}>예상 비용 확인 후 실행</button>{" "}
          <button className="tbtn" onClick={() => setEstimate(null)}>닫기</button>
        </div>
      )}
      {state === "running" && <p data-testid="ai-running" style={{ fontSize: 13, marginTop: 10 }}>AI가 원문을 분석 중입니다... (최대 1~2분)</p>}

      {analysis && (
        <div style={{ marginTop: 12 }} data-testid="ai-result">
          <div style={{ ...box, background: "var(--panel-2)" }}>
            <span className={`pill ${VERIFY_CLASS[analysis.verification_status]}`} data-testid="ai-verification">{VERIFY_LABEL[analysis.verification_status]}</span>{" "}
            <span style={{ fontSize: 12 }}>모델 {analysis.provider}/{analysis.model} · 처리 {analysis.finished_at?.slice(0, 16).replace("T", " ") ?? "-"} · 프롬프트 {analysis.prompt_version} · 토큰 {analysis.input_tokens}/{analysis.output_tokens}
              {analysis.actual_cost_usd != null ? ` · 비용 $${analysis.actual_cost_usd}` : ""}</span>
            <div style={{ fontSize: 12, marginTop: 4 }}>사용한 원문 {analysis.input_documents.length}건: {analysis.input_documents.map((d) => `${d.title.slice(0, 40)}(해시 ${d.content_hash.slice(0, 8)})`).join(" · ") || "없음"}</div>
            <div style={{ fontSize: 12, marginTop: 4 }} data-testid="ai-stats">사실 문장 {analysis.stats.facts}건 중 근거 없음·불일치·검증 실패 {analysis.stats.facts_without_valid_evidence}건 · 연구원 검증 {analysis.stats.researcher_verified}건</div>
            <div style={{ fontSize: 12, color: "var(--ink-muted)", marginTop: 4 }}>{analysis.notice}</div>
            {analysis.notes.map((n, i) => <div key={i} style={{ fontSize: 12, color: "var(--warn)" }}>⚠ {n}</div>)}
          </div>
          {analysis.hold_reason && <p role="status" data-testid="ai-hold" style={{ color: "var(--warn)", fontSize: 13 }}>{analysis.hold_reason}</p>}
          {analysis.sections?.map((s) => (
            <div key={s.key} style={{ marginBottom: 10 }}>
              <h3 style={{ fontSize: 13, margin: "8px 0 4px" }}>{s.title}</h3>
              {s.suppressed && <p style={{ fontSize: 12.5, color: "var(--ink-muted)" }}>{s.suppressed}</p>}
              {!s.suppressed && s.claims.length === 0 && <p style={{ fontSize: 12.5, color: "var(--ink-muted)" }}>근거 부족 — 생성된 내용이 없습니다.</p>}
              {s.claims.map((c) => (
                <div key={c.id} style={box} data-testid="ai-claim" data-evidence-status={c.evidence_status} data-researcher-status={c.researcher_status}>
                  <div style={{ display: "flex", gap: 6, alignItems: "flex-start" }}>
                    {isDraft && manuscript && <input type="checkbox" aria-label="원고에 삽입할 문장 선택" checked={!!selected[c.id]} onChange={(e) => setSelected({ ...selected, [c.id]: e.target.checked })} />}
                    <div style={{ flex: 1 }}>
                      <div style={{ fontSize: 13 }}>{c.text}</div>
                      <div style={{ marginTop: 4 }}>
                        <span className={`pill ${EVID_CLASS[c.evidence_status]}`}>{EVID_LABEL[c.evidence_status]}</span>
                        {c.researcher_status !== "unverified" && <span className={`pill ${c.researcher_status === "verified" ? "rec" : "review"}`}>{c.researcher_status === "verified" ? "연구원 검증" : "연구원 반려"}</span>}
                        <span className="pill">AI 생성</span>
                      </div>
                      {c.check_note && <div style={{ fontSize: 12, color: "var(--warn)" }}>{c.check_note}</div>}
                    </div>
                  </div>
                  {c.evidence.length > 0 && (
                    <div style={{ marginTop: 6 }}>
                      <button className="tbtn" onClick={() => setOpenEv({ ...openEv, [c.id]: !openEv[c.id] })}>{openEv[c.id] ? "원문 근거 닫기" : "원문 근거 보기"}</button>
                      {openEv[c.id] && c.evidence.map((e, i) => (
                        <blockquote key={i} data-testid="ai-evidence" style={{ margin: "6px 0", padding: "4px 10px", borderLeft: `3px solid ${e.found ? "var(--ok)" : "var(--bad)"}`, fontSize: 12.5 }}>
                          “{e.quote}”
                          <div style={{ fontSize: 11.5, color: "var(--ink-muted)" }}>
                            {e.title ?? "분석 입력에 없는 문서"}{e.location ? ` · ${e.location}` : " · 위치 미확인"} · {e.found ? "원문에서 확인됨" : "원문에서 찾지 못함"}
                            {e.document_id && <> · <Link href={`/documents/${e.document_id}`}>플랫폼 원문 보기</Link></>}
                            {e.url && <> · <a href={e.url} target="_blank" rel="noopener noreferrer">공식 원문 ↗</a></>}
                          </div>
                        </blockquote>
                      ))}
                    </div>
                  )}
                  {isDraft && manuscript && selected[c.id] && (
                    <textarea aria-label="삽입 전 문장 수정" style={{ ...inp, marginTop: 6 }} defaultValue={c.text} onChange={(e) => setEdits({ ...edits, [c.id]: e.target.value })} />
                  )}
                  <div style={{ display: "flex", gap: 6, marginTop: 6, flexWrap: "wrap", alignItems: "center" }}>
                    {c.researcher_status === "unverified" && c.claim_type === "fact" && c.evidence_status !== "found" && (
                      <input aria-label="원문 대조 사유" placeholder="원문과 직접 대조한 사유" value={notes[c.id] ?? ""} onChange={(e) => setNotes({ ...notes, [c.id]: e.target.value })} style={{ ...inp, width: 240 }} />
                    )}
                    {c.researcher_status !== "verified" && <button className="tbtn" onClick={() => review(c, "verify")}>검증 완료</button>}
                    {c.researcher_status !== "rejected" && <button className="tbtn" onClick={() => review(c, "reject")}>반려</button>}
                    {c.researcher_status !== "unverified" && <button className="tbtn" onClick={() => review(c, "reset")}>되돌리기</button>}
                  </div>
                </div>
              ))}
            </div>
          ))}
          {isDraft && manuscript && (
            <div style={{ ...box, background: "var(--panel-2)" }}>
              <p style={{ fontSize: 12.5, margin: "0 0 6px" }}>선택한 문장만 원고 <b>끝</b>에 덧붙입니다. 기존 본문·승인·각주는 바뀌지 않고, 삽입 각주는 미검증으로 시작합니다. AI 초안은 연구원 검토용 초안입니다.</p>
              <button className="tbtn primary" data-testid="ai-insert" onClick={insert}>선택한 문장 원고에 삽입</button>{" "}
              <button className="tbtn" onClick={() => { setSelected({}); setAnalysis(null); setMsg("제안을 폐기했습니다(저장된 분석 기록은 남습니다)."); }}>전체 제안 폐기</button>
            </div>
          )}
          {kind === "candidate" && analysis.status === "completed" && (
            <div style={{ ...box, background: "var(--panel-2)" }} data-testid="ai-candidate-form">
              <b style={{ fontSize: 13 }}>후보로 등록·수정</b>
              <input aria-label="AI 제안 제목(수정)" style={{ ...inp, margin: "6px 0" }} value={candForm.title} onChange={(e) => setCandForm({ ...candForm, title: e.target.value })} />
              <textarea aria-label="AI 제안 설명(수정)" style={{ ...inp, minHeight: 56 }} value={candForm.summary} onChange={(e) => setCandForm({ ...candForm, summary: e.target.value })} placeholder="연구원이 정리한 설명(선택)" />
              {existingCandidates.length > 0 && (
                <select aria-label="기존 후보주제에 연결" style={{ ...inp, margin: "6px 0" }} value={candForm.attach} onChange={(e) => setCandForm({ ...candForm, attach: e.target.value })}>
                  <option value="">새 후보로 등록</option>
                  {existingCandidates.map((c) => <option key={c.id} value={c.id}>기존 후보에 연결: {c.title}</option>)}
                </select>
              )}
              <button className="tbtn primary" data-testid="ai-save-candidate" disabled={candForm.title.trim().length < 2} onClick={saveCandidate}>{candForm.attach ? "기존 후보에 연결" : "이 제안으로 후보 생성"}</button>
              <span style={{ fontSize: 11.5, color: "var(--ink-muted)", marginLeft: 8 }}>선정·확정 상태는 AI가 바꾸지 않습니다.</span>
              {savedCandidate && <div style={{ marginTop: 6 }}><Link href={`/candidates/${savedCandidate}`} data-testid="ai-candidate-link">등록·연결된 후보주제 보기 →</Link></div>}
            </div>
          )}
        </div>
      )}
    </section>
  );
}
