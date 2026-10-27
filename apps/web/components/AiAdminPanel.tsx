"use client";

import { useCallback, useEffect, useState } from "react";
import { aiApprovals, aiDiagnostics, aiEvaluationSummary, aiPricing, aiRevokeApproval, aiSetPricing, aiStatus, aiUsage, EVAL_CRITERIA, type AiApproval, type AiDiagnostics, type AiPrice, type AiStatus, type AiUsage, type EvalGroup } from "@/lib/aiApi";

const inp: React.CSSProperties = { padding: 7, borderRadius: 8, border: "1px solid var(--border)", fontSize: 13 };
const CONN_LABEL: Record<string, string> = { not_configured: "연결 미검증(설정 없음)", unverified: "연결 미검증", mock: "모의 공급자(실제 연결 아님)" };

/** 설정 화면의 'AI 분석' 섹션 — 연결 상태(키 값은 표시하지 않음)·사용량·관리자 단가표. 연결 진단은 관리자만 실행한다. */
export default function AiAdminPanel({ isAdmin }: { isAdmin: boolean }) {
  const [status, setStatus] = useState<AiStatus | null>(null);
  const [usage, setUsage] = useState<AiUsage | null>(null);
  const [prices, setPrices] = useState<AiPrice[]>([]);
  const [diag, setDiag] = useState<AiDiagnostics | null>(null);
  const [approvals, setApprovals] = useState<AiApproval[]>([]);
  const [evals, setEvals] = useState<{ real: EvalGroup; mock: EvalGroup; note: string } | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [form, setForm] = useState({ provider: "anthropic", model: "", input: "", output: "", date: new Date().toISOString().slice(0, 10), note: "" });

  const load = useCallback(() => {
    aiStatus().then(setStatus).catch(() => setStatus(null));
    aiUsage("me", 1).then(setUsage).catch(() => setUsage(null));
    aiPricing().then(setPrices).catch(() => setPrices([]));
    aiEvaluationSummary().then(setEvals).catch(() => setEvals(null));
    if (isAdmin) aiApprovals().then(setApprovals).catch(() => setApprovals([]));
  }, [isAdmin]);
  useEffect(() => { load(); }, [load]);

  async function runDiag() {
    setDiag(null); setMsg(null);
    try { setDiag(await aiDiagnostics()); } catch (e) { setMsg(e instanceof Error ? e.message : "진단 실패"); }
  }
  async function savePrice(e: React.FormEvent) {
    e.preventDefault(); setMsg(null);
    try {
      const r = await aiSetPricing({ provider: form.provider, model: form.model, input_per_mtok: Number(form.input), output_per_mtok: Number(form.output), effective_date: form.date, source_note: form.note || undefined });
      setMsg(`단가를 v${r.version}으로 저장했습니다(이전 단가는 보존).`);
      load();
    } catch (err) { setMsg(err instanceof Error ? err.message : "저장 실패"); }
  }

  return (
    <section className="panel" style={{ marginBottom: 16 }} data-testid="ai-admin-panel">
      <h2 style={{ fontSize: 14, margin: "0 0 10px" }}>분석 기능 상태·사용량</h2>
      {status && (
        <p style={{ fontSize: 13, margin: "0 0 8px" }} data-testid="ai-conn-status">
          상태: <b>{status.configured ? `${status.provider} / ${status.model}` : "AI 설정 필요"}</b> · <span className="pill hold">{CONN_LABEL[status.connection] ?? status.connection}</span>
          <span style={{ display: "block", fontSize: 12, color: "var(--ink-muted)" }}>{status.connection_note}{status.config_gaps.length > 0 ? ` (${status.config_gaps.join("; ")})` : ""}</span>
        </p>
      )}
      {status?.paid_locked && <p data-testid="ai-paid-locked" style={{ fontSize: 12.5, margin: "0 0 8px" }}><b>무료 시연 버전</b> — 유료 외부 AI(Anthropic·OpenAI) 연결·진단·호출 승인·단가 설정은 코드 수준으로 비활성화되어 있으며 환경변수나 이 화면으로 켤 수 없습니다.</p>}
      {isAdmin && !status?.paid_locked && <p style={{ margin: "0 0 8px" }}><button className="tbtn" data-testid="ai-diagnose" onClick={runDiag}>연결 진단(모델 목록 조회, 토큰 사용 없음)</button></p>}
      {diag && <p role="status" data-testid="ai-diag-result" style={{ fontSize: 12.5, color: diag.verified ? "var(--ok)" : "var(--warn)" }}>{diag.verified ? "확인됨" : "미검증"} — {diag.message}</p>}
      {usage && (
        <p style={{ fontSize: 12.5, margin: "8px 0" }} data-testid="ai-usage">
          오늘 내 사용량: 요청 {usage.requests}건(한도 {usage.daily_limit_per_user}) · 제공자 전달 {usage.provider_requests_sent} · 실패·취소 {usage.failed_or_cancelled} · 모의 {usage.mock_requests} · 토큰 {usage.input_tokens.toLocaleString()}/{usage.output_tokens.toLocaleString()} ·
          예상 ${usage.est_cost_usd} · 계산 ${usage.calculated_cost_usd}
          <span style={{ display: "block", color: "var(--ink-muted)" }}>{usage.cost_note}</span>
        </p>
      )}
      {!status?.paid_locked && <h3 style={{ fontSize: 13, margin: "10px 0 4px" }}>제공자·모델별 단가표 (USD/100만 토큰, 관리자 갱신)</h3>}
      {!status?.paid_locked && <table style={{ fontSize: 12.5, borderCollapse: "collapse", width: "100%" }} data-testid="ai-price-table">
        <thead><tr style={{ textAlign: "left" }}><th>제공자</th><th>모델</th><th>입력</th><th>출력</th><th>기준일</th><th>버전</th><th>상태</th><th>출처</th></tr></thead>
        <tbody>
          {prices.map((p) => (
            <tr key={p.id} style={{ borderTop: "1px solid var(--border)", opacity: p.is_active ? 1 : 0.55 }}>
              <td>{p.provider}</td><td>{p.model}</td><td>{p.input_per_mtok}</td><td>{p.output_per_mtok}</td><td>{p.effective_date}</td><td>v{p.version}</td><td>{p.is_active ? "사용 중" : "이전 버전"}</td><td>{p.source_note ?? "-"}</td>
            </tr>
          ))}
          {prices.length === 0 && <tr><td colSpan={8} style={{ color: "var(--ink-muted)" }}>등록된 단가가 없습니다 — 단가가 없으면 비용은 &lsquo;계산 불가&rsquo;로 표시되며 0원으로 간주하지 않습니다.</td></tr>}
        </tbody>
      </table>}
      {isAdmin && !status?.paid_locked && (
        <form onSubmit={savePrice} style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 8 }}>
          <select aria-label="제공자" value={form.provider} onChange={(e) => setForm({ ...form, provider: e.target.value })} style={inp}><option>anthropic</option><option>openai</option></select>
          <input aria-label="모델 ID" placeholder="정확한 모델 ID" value={form.model} onChange={(e) => setForm({ ...form, model: e.target.value })} style={inp} required />
          <input aria-label="입력 단가" type="number" step="any" placeholder="입력 단가" value={form.input} onChange={(e) => setForm({ ...form, input: e.target.value })} style={{ ...inp, width: 100 }} required />
          <input aria-label="출력 단가" type="number" step="any" placeholder="출력 단가" value={form.output} onChange={(e) => setForm({ ...form, output: e.target.value })} style={{ ...inp, width: 100 }} required />
          <input aria-label="요금 기준일" type="date" value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })} style={inp} required />
          <input aria-label="단가 출처" placeholder="출처(공식 가격표 확인일)" value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} style={{ ...inp, minWidth: 220 }} />
          <button className="tbtn primary" type="submit">단가 저장(새 버전)</button>
        </form>
      )}
      {msg && <p role="status" style={{ fontSize: 12.5 }}>{msg}</p>}
      {status && !status.paid_locked && <p style={{ fontSize: 12, margin: "8px 0" }} data-testid="ai-gate-status">첫 실호출 안전장치: {status.require_approval ? "관리자 1건 승인 필수(승인 1회용·자동 재시도 금지)" : "승인 불필요(모의 공급자이거나 AI_REQUIRE_APPROVAL=0)"}{status.max_cost_per_request_usd != null ? ` · 요청당 상한 $${status.max_cost_per_request_usd}` : ""}</p>}
      {isAdmin && !status?.paid_locked && approvals.length > 0 && (
        <details style={{ fontSize: 12.5, marginTop: 6 }}>
          <summary>호출 승인 내역 {approvals.length}건</summary>
          {approvals.map((a) => (
            <div key={a.id}>{a.kind} · {a.model} · 상한 ${a.max_cost_usd} · {a.used_at ? "사용됨" : a.revoked ? "취소됨" : "미사용"}
              {!a.used_at && !a.revoked && <button className="tbtn" style={{ marginLeft: 6 }} onClick={async () => { await aiRevokeApproval(a.id); load(); }}>승인 취소</button>}</div>
          ))}
        </details>
      )}
      {evals && (
        <div style={{ marginTop: 10, fontSize: 12.5 }} data-testid="ai-eval-summary">
          <b>품질 평가 집계</b> — <span style={{ color: "var(--ink-muted)" }}>{evals.note}</span>
          {(["real", "mock"] as const).map((g) => (
            <div key={g}>{g === "real" ? "실제 AI" : "모의 응답"}: 평가 {evals[g].evaluations}건 · 사실 문장 {evals[g].facts}건 중 근거 없음/불일치 {evals[g].facts_without_valid_evidence}건
              {evals[g].ratio_without_valid_evidence != null ? ` (${Math.round((evals[g].ratio_without_valid_evidence ?? 0) * 100)}%)` : ""} · 의미 불일치 {evals[g].semantic_mismatch_cases} · 근거 부족 {evals[g].insufficient_evidence_cases} · 잘못된 출처 {evals[g].wrong_source_cases}
              {evals[g].evaluations > 0 && <span style={{ color: "var(--ink-muted)" }}> · 부적절 {Object.entries(evals[g].criteria).filter(([, v]) => v.bad > 0).map(([k, v]) => `${(EVAL_CRITERIA[k] ?? k).slice(0, 2)}×${v.bad}`).join(" ") || "없음"}</span>}</div>
          ))}
        </div>
      )}
    </section>
  );
}
