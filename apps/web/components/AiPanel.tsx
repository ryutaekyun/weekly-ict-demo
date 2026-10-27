"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { getCurrentUser, type CurrentUser } from "@/lib/api";
import {
  aiCancel, aiCandidate, aiCreateApproval, aiEstimate, aiInsert, aiList, aiGet, aiReviewClaim, aiPreflight, aiRun, aiSaveEvaluation, aiStatus, EVAL_CRITERIA, type AiPreflight,
  type AiAnalysis, type AiClaim, type AiEstimate, type AiKind, type AiStatus, type InsertPosition,
} from "@/lib/aiApi";

const VERIFY_LABEL: Record<string, string> = {
  ai_unverified: "AI 생성·연구원 미검증", insufficient: "근거 부족", mismatch: "근거 불일치", researcher_verified: "연구원 검증 완료",
};
const VERIFY_CLASS: Record<string, string> = { ai_unverified: "hold", insufficient: "review", mismatch: "review", researcher_verified: "rec" };
const EVID_LABEL: Record<string, string> = {
  found: "원문 근거 확인", semantic_risk: "의미 불일치 가능성(검토 필요)", not_found: "검증 실패(원문에 없음)", value_mismatch: "근거 불일치(날짜·수치)", no_evidence: "근거 없음·확인 필요",
  interpretation: "AI 해석(원문 사실 아님)", gap: "확인 필요 사항",
};
const EVID_CLASS: Record<string, string> = { found: "rec", semantic_risk: "review", not_found: "review", value_mismatch: "review", no_evidence: "review", interpretation: "hold", gap: "hold" };
const ERROR_TITLE: Record<string, string> = {
  auth_error: "인증·권한 오류", model_error: "모델 오류", rate_limited: "요청 한도 초과", context_too_large: "입력 한도 초과", timeout: "응답 시간 초과",
  provider_5xx: "제공자 서버 오류", bad_response: "잘못된 응답 형식", truncated: "응답 잘림", interrupted: "분석 중단됨",
};
const STATE_LABEL: Record<string, string> = { idle: "분석 대기", running: "분석 중", done: "분석 완료·미검증", failed: "분석 실패", config: "AI 설정 필요", hold: "분석 보류(근거 부족)" };
const box: React.CSSProperties = { border: "1px solid var(--border)", borderRadius: 10, padding: 10, marginBottom: 8, background: "var(--panel)" };
const inp: React.CSSProperties = { padding: 7, borderRadius: 8, border: "1px solid var(--border)", fontSize: 13, width: "100%" };

type Props = {
  kind: AiKind; targetId: string; title: string; buttonLabel: string; documentIds?: string[]; testId?: string;
  existingCandidates?: { id: string; title: string }[];
  manuscript?: { id: string; getLockVersion: () => Promise<number>; onInserted: () => void; getCursorIndex?: () => number | null; getHeadings?: () => string[] };
  ruleBased?: { label: string; text: string }[]; // 기존 규칙 기반 분석 결과 — AI 결과와 나란히 비교한다
  onCandidateLinked?: (candidateId: string, created: boolean) => void;
};

export default function AiPanel({ kind, targetId, title, buttonLabel, documentIds, testId = "ai-panel", existingCandidates = [], manuscript, onCandidateLinked, ruleBased }: Props) {
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
  const [posMode, setPosMode] = useState<"end" | "cursor" | "heading">("end");
  const [posHeading, setPosHeading] = useState("");
  const [me, setMe] = useState<CurrentUser | null>(null);
  const [evalOpen, setEvalOpen] = useState(false);
  const [evalScores, setEvalScores] = useState<Record<string, string>>({});
  const [evalCounts, setEvalCounts] = useState({ semantic: 0, insufficient: 0, wrongSource: 0 });
  const [evalNotes, setEvalNotes] = useState("");
  const [approveCost, setApproveCost] = useState("");
  const [preflight, setPreflight] = useState<AiPreflight | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const loadLatest = useCallback(async () => {
    try {
      const list = await aiList(targetId, kind);
      const latest = list.find((a) => a.status === "completed" || a.status === "insufficient_evidence");
      if (latest) setAnalysis(await aiGet(latest.id));
    } catch { /* 이력이 없으면 비워 둔다 */ }
  }, [targetId, kind]);

  useEffect(() => { aiStatus().then(setStatus).catch(() => setStatus(null)); getCurrentUser().then(setMe).catch(() => undefined); loadLatest(); }, [loadLatest]);

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
      const watchdog = setTimeout(() => ac.abort(), 170_000); // 응답이 없으면 '분석 중'이 무한히 유지되지 않게 한다
      const res = await aiRun(kind, targetId, { document_ids: documentIds, force }, ac.signal).finally(() => clearTimeout(watchdog));
      if (res.status === "failed" || res.status === "cancelled") {
        setAnalysis(null);
        setState("failed");
        const title = ERROR_TITLE[res.error_code ?? ""] ?? (res.status === "cancelled" ? "취소됨" : "분석 실패");
        setError(`${title}: ${res.error_message ?? res.cancel_note ?? "사유 없음"}${res.provider_request_sent ? " (외부 제공자에 요청이 전달되어 비용이 발생했을 수 있습니다)" : ""}`);
        return;
      }
      setAnalysis(await aiGet(res.id).catch(() => res));
      setSelected({}); setEdits({});
      setState("idle");
      if (res.reused) setMsg("같은 원문 버전의 이전 분석 결과를 다시 보여줍니다(AI 호출·비용 없음). 새로 분석하려면 '다시 분석'을 누르세요.");
    } catch (e) {
      setState(ac.signal.aborted ? "idle" : "failed");
      setError(ac.signal.aborted ? "응답을 기다리다 중단했습니다 — 서버에서는 요청이 계속 처리됐을 수 있으니 잠시 뒤 새로고침해 결과를 확인하세요(외부 제공자에 요청이 전달됐다면 비용이 발생했을 수 있음)." : e instanceof Error ? e.message : "분석 실패");
    }
  }

  async function runPreflight() {
    setError(null);
    try { setPreflight(await aiPreflight(kind, targetId, documentIds)); } catch (e) { setError(e instanceof Error ? e.message : "사전 점검 실패"); }
  }

  async function approveCall() {
    if (!estimate) return;
    setError(null);
    try {
      const cost = Number(approveCost || Math.max(0.01, Math.ceil((estimate.max_cost_usd ?? estimate.est_cost_usd ?? 0) * 115) / 100));
      await aiCreateApproval({ kind, target_id: targetId, max_cost_usd: cost, valid_minutes: 60, note: "화면에서 1건 승인" });
      setEstimate(await aiEstimate(kind, targetId, documentIds));
      setMsg(`이 1건 호출을 승인했습니다(예산 상한 $${cost}, 60분 유효, 한 번 쓰면 소멸).`);
    } catch (e) { setError(e instanceof Error ? e.message : "승인 실패"); }
  }

  async function saveEvaluation() {
    if (!analysis) return;
    setError(null);
    try {
      const r = await aiSaveEvaluation(analysis.id, { scores: evalScores, semantic_mismatch_cases: evalCounts.semantic, insufficient_evidence_cases: evalCounts.insufficient, wrong_source_cases: evalCounts.wrongSource, notes: evalNotes || undefined });
      setMsg(r.is_mock ? "평가를 저장했습니다 — 모의 응답 평가이므로 실제 AI 정확도 집계에는 합산되지 않습니다." : "평가를 저장했습니다.");
      setEvalOpen(false);
    } catch (e) { setError(e instanceof Error ? e.message : "평가 저장 실패"); }
  }

  async function cancel() {
    abortRef.current?.abort();
    try {
      const running = (await aiList(targetId, kind)).find((a) => a.status === "running");
      if (running) {
        const c = await aiCancel(running.id);
        setMsg(c.cancel_note ?? "취소를 요청했습니다.");
      }
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
      let position: InsertPosition = { mode: "end" };
      if (posMode === "cursor") {
        const idx = manuscript.getCursorIndex?.();
        if (idx == null) { setError("편집기에서 문단을 클릭해 커서를 둔 뒤 다시 시도하세요."); return; }
        position = { mode: "after_index", index: idx };
      } else if (posMode === "heading") {
        if (!posHeading) { setError("삽입할 소제목을 선택하세요."); return; }
        position = { mode: "after_heading", heading_text: posHeading };
      }
      const r = await aiInsert(analysis.id, { manuscript_id: manuscript.id, claim_ids: ids, lock_version: lock, edited_texts: Object.fromEntries(ids.filter((i) => edits[i]).map((i) => [i, edits[i]])), position });
      manuscript.onInserted();
      setSelected({});
      setMsg(`${r.inserted}문장을 ${posMode === "cursor" ? "커서 위치 뒤" : posMode === "heading" ? `'${posHeading}' 소제목 아래` : "원고 끝"}에 삽입했습니다(각주 ${r.footnotes_created}건, 모두 미검증). ${r.note}`);
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
            예상 비용 {estimate.est_cost_usd == null ? <b data-testid="ai-cost-unknown">계산 불가(단가 미설정)</b> : <b>약 ${estimate.est_cost_usd}</b>}{estimate.is_mock ? " (모의 호출 — 실제 비용 미검증)" : " (추정치, 실제 청구금액 아님)"}
            {estimate.max_cost_usd != null && <span data-testid="ai-max-cost"> · 최대 계산 비용 ${estimate.max_cost_usd}(출력 {estimate.max_output_tokens.toLocaleString()}토큰까지 사용한다고 가정)</span>}
          </p>
          <p style={{ fontSize: 11.5, color: "var(--ink-muted)", margin: "0 0 6px" }}>{estimate.price_note} 원문 공개자료만 외부 AI 서비스로 전송됩니다.</p>
          {estimate.existing_candidate_ids.length > 0 && <p style={{ fontSize: 12, color: "var(--warn)" }}>이 이슈에는 이미 후보주제 {estimate.existing_candidate_ids.length}건이 있습니다. 결과는 기존 후보에 연결할 수 있습니다.</p>}
          {estimate.blockers.map((b, i) => <p key={i} role="alert" style={{ color: "var(--bad)", fontSize: 12.5 }}>{b}</p>)}
          {estimate.approval_required && !estimate.approval && (
            <div data-testid="ai-approval-needed" style={{ ...box, background: "var(--warnsoft, #FFF4D6)" }}>
              <b style={{ fontSize: 12.5 }}>실제 AI 호출은 관리자의 1건 승인이 필요합니다</b>
              <div style={{ fontSize: 12 }}>대상·모델·예산 상한을 지정해 승인하며, 한 번 쓰면 소멸합니다(자동 재시도·다음 문서 자동 분석 없음).{estimate.max_cost_per_request_usd != null ? ` 요청당 전역 상한 $${estimate.max_cost_per_request_usd}.` : ""}</div>
              {me?.role === "admin" ? (
                <div style={{ marginTop: 6 }}>
                  <input aria-label="예산 상한(USD)" type="number" step="0.01" placeholder={`예산 상한 USD (기본 예상×1.5)`} value={approveCost} onChange={(e) => setApproveCost(e.target.value)} style={{ ...inp, width: 200 }} />{" "}
                  <button className="tbtn primary" data-testid="ai-approve" onClick={approveCall}>이 1건 호출 승인</button>
                </div>
              ) : <div style={{ fontSize: 12, marginTop: 4 }}>관리자에게 이 대상의 호출 승인을 요청하세요.</div>}
            </div>
          )}
          {me?.role === "admin" && estimate.approval_required && (
            <div style={{ margin: "6px 0" }}>
              <button className="tbtn" data-testid="ai-preflight" onClick={runPreflight}>첫 호출 사전 점검(유료 호출 없음)</button>
              {preflight && (
                <div data-testid="ai-preflight-result" style={{ ...box, fontSize: 12, marginTop: 6 }}>
                  모델 {preflight.model} · API {preflight.api_version ?? "-"} · 전달 키 {preflight.request_top_level_keys.join(", ")} · 미전송 {preflight.not_sent.join(", ")}<br />
                  입력 토큰 {preflight.input_tokens.toLocaleString()} ({preflight.input_tokens_measured ? "실측" : "미측정·추정"}) — {preflight.input_tokens_note}<br />
                  최대 출력 {preflight.max_tokens.toLocaleString()} · 예상 ${preflight.expected_cost_usd ?? "계산 불가"} · 최대 ${preflight.max_cost_usd ?? "계산 불가"} · 권장 승인 상한 ${preflight.recommended_approval_cap_usd ?? "-"}<br />
                  연결 상태: {preflight.connection === "unverified" ? "연결 미검증(키 설정됨)" : "연결 미검증(설정 없음)"} · 지시문+원문 해시 {preflight.prompt_sha256.slice(0, 12)}
                </div>
              )}
            </div>
          )}
          {estimate.approval && <p data-testid="ai-approved" style={{ fontSize: 12, color: "var(--ok)" }}>승인됨: 예산 상한 ${estimate.approval.max_cost_usd} · {estimate.approval.expires_at.slice(0, 16).replace("T", " ")}까지 유효 · 1회용</p>}
          <button className="tbtn primary" data-testid="ai-confirm" disabled={estimate.blockers.length > 0 || (estimate.approval_required && !estimate.approval)} onClick={() => execute(forceNext)}>예상 비용 확인 후 실행</button>{" "}
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
          {ruleBased && ruleBased.length > 0 && (
            <div style={{ ...box }} data-testid="ai-rule-compare">
              <b style={{ fontSize: 13 }}>기존 규칙 기반 결과 ↔ AI 결과 비교</b>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginTop: 6, fontSize: 12.5 }}>
                <div><div style={{ color: "var(--ink-muted)", marginBottom: 2 }}>규칙 기반(원본 보존)</div>{ruleBased.map((r) => <div key={r.label}><b>{r.label}</b>: {r.text || "-"}</div>)}</div>
                <div><div style={{ color: "var(--ink-muted)", marginBottom: 2 }}>AI 생성 · {analysis.model ?? "-"} · {analysis.finished_at?.slice(0, 10) ?? "-"}</div>
                  {analysis.sections?.filter((s) => ["summary", "changes", "field_fit"].includes(s.key)).map((s) => <div key={s.key}><b>{s.title}</b>: {s.claims.map((c) => c.text).join(" ") || "근거 부족"}</div>)}</div>
              </div>
              <div style={{ fontSize: 11.5, color: "var(--ink-muted)", marginTop: 4 }}>두 결과는 서로 다른 방식으로 만든 별도 기록입니다. 달라 보이는 날짜·수치는 원문 근거로 확인하세요(자동으로 어느 쪽이 맞다고 판정하지 않음).</div>
            </div>
          )}
          {analysis.source_changed_during_run && <p role="alert" data-testid="ai-source-changed" style={{ color: "var(--bad)", fontSize: 13 }}>분석 도중 원문이 변경되었습니다 — 이 결과는 변경 전 원문 기준이므로 &lsquo;다시 분석&rsquo;이 필요합니다.</p>}
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
              <p style={{ fontSize: 12.5, margin: "0 0 6px" }}>선택한 문장만 아래에서 고른 위치에 덧붙입니다. 기존 본문·승인·각주는 바뀌지 않고, 삽입 문장에는 AI 표시와 미검증 각주가 붙습니다. AI 초안은 연구원 검토용 초안입니다.</p>
              <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center", marginBottom: 6, fontSize: 12.5 }}>
                <label><input type="radio" name={`pos-${testId}`} checked={posMode === "end"} onChange={() => setPosMode("end")} /> 원고 끝</label>
                <label><input type="radio" name={`pos-${testId}`} checked={posMode === "cursor"} onChange={() => setPosMode("cursor")} data-testid="pos-cursor" /> 현재 커서가 있는 문단 뒤</label>
                <label><input type="radio" name={`pos-${testId}`} checked={posMode === "heading"} onChange={() => { setPosMode("heading"); setPosHeading(manuscript.getHeadings?.()[0] ?? ""); }} data-testid="pos-heading" /> 소제목 아래</label>
                {posMode === "heading" && (
                  <select aria-label="삽입할 소제목" value={posHeading} onChange={(e) => setPosHeading(e.target.value)} style={{ ...inp, width: 220 }}>
                    {(manuscript.getHeadings?.() ?? []).map((h) => <option key={h} value={h}>{h}</option>)}
                  </select>
                )}
              </div>
              <button className="tbtn primary" data-testid="ai-insert" onClick={insert}>선택한 문장 원고에 삽입</button>{" "}
              <button className="tbtn" onClick={() => { setSelected({}); setAnalysis(null); setMsg("제안을 폐기했습니다(저장된 분석 기록은 남습니다)."); }}>전체 제안 폐기</button>
            </div>
          )}
          {analysis.status === "completed" && (
            <div style={{ ...box }} data-testid="ai-evaluation">
              <button className="tbtn" onClick={() => setEvalOpen(!evalOpen)}>{evalOpen ? "품질 평가 닫기" : "품질 평가(7개 항목)"}</button>
              {analysis.is_mock && <span style={{ fontSize: 11.5, color: "var(--warn)", marginLeft: 8 }}>모의 응답 평가는 실제 AI 정확도 집계에 합산되지 않습니다</span>}
              {evalOpen && (
                <div style={{ marginTop: 8, fontSize: 12.5 }}>
                  {Object.entries(EVAL_CRITERIA).map(([k, label]) => (
                    <div key={k} style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 3 }}>
                      <span style={{ flex: 1 }}>{label}</span>
                      <select aria-label={label} value={evalScores[k] ?? ""} onChange={(e) => setEvalScores({ ...evalScores, [k]: e.target.value })} style={{ ...inp, width: 120 }}>
                        <option value="">선택</option><option value="ok">적절</option><option value="partial">일부 문제</option><option value="bad">부적절</option><option value="na">해당 없음</option>
                      </select>
                    </div>
                  ))}
                  <div style={{ display: "flex", gap: 8, flexWrap: "wrap", margin: "6px 0" }}>
                    <label>의미 불일치 사례 <input aria-label="의미 불일치 사례 수" type="number" min={0} value={evalCounts.semantic} onChange={(e) => setEvalCounts({ ...evalCounts, semantic: Number(e.target.value) })} style={{ ...inp, width: 70 }} /></label>
                    <label>근거 부족 사례 <input aria-label="근거 부족 사례 수" type="number" min={0} value={evalCounts.insufficient} onChange={(e) => setEvalCounts({ ...evalCounts, insufficient: Number(e.target.value) })} style={{ ...inp, width: 70 }} /></label>
                    <label>잘못된 출처 연결 <input aria-label="잘못된 출처 연결 사례 수" type="number" min={0} value={evalCounts.wrongSource} onChange={(e) => setEvalCounts({ ...evalCounts, wrongSource: Number(e.target.value) })} style={{ ...inp, width: 70 }} /></label>
                  </div>
                  <textarea aria-label="평가 메모(오류·과장 사례)" placeholder="오류·과장 사례, 정정한 문장" value={evalNotes} onChange={(e) => setEvalNotes(e.target.value)} style={{ ...inp, minHeight: 50 }} />
                  <button className="tbtn primary" data-testid="ai-eval-save" disabled={Object.keys(EVAL_CRITERIA).some((k) => !evalScores[k])} onClick={saveEvaluation}>평가 저장</button>
                </div>
              )}
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
