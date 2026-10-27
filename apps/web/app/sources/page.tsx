"use client";

import { Fragment, useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import AppShell from "@/components/AppShell";
import {
  cancelCollectionJob, createSource, getCollectionJob, getCurrentUser, getSourceHistory, listSourceJobs, listSourceRuns, listSources, startCollection, testSourceConnection, updateSource,
  UnauthorizedError, type CollectionJob, type ConnectionTestResult, type CollectionRunOut, type SourceInput, type SourceOut,
} from "@/lib/api";
import { FIELD_LABELS, fmtDate } from "@/lib/labels";

const METHODS: Record<string, string> = { api: "REST API", rss: "RSS·Atom", html: "공개 HTML", pdf: "공식 PDF", metadata: "메타데이터 전용" };
const INTERVALS: [number, string][] = [[0, "자동 수집 안 함"], [60, "1시간마다"], [360, "6시간마다"], [720, "12시간마다"], [1440, "매일"], [10080, "매주"]];
const API_PROVIDERS: Record<string, string> = { federal_register: "미국 Federal Register", arxiv_api: "arXiv 공식 API" };
const JOB_LABEL: Record<string, string> = { queued: "대기 중", running: "수집 중", succeeded: "완료", failed: "실패", cancelled: "취소됨", timeout: "시간 초과", interrupted: "중단됨" };
const ACCESS_TONE: Record<string, string> = { ok: "green", metadata_only: "", blocked: "bad", moved: "warn", unverified: "", error: "warn" };

const emptyForm: SourceInput = { name: "", org_name: "", field_code: "ai", url: "", source_type: "rss", api_provider: null, country_code: "", interval_minutes: 1440, min_request_interval_seconds: 3, respect_robots: true, config_json: "", description: "" };

function jobSummary(j: CollectionJob): string {
  return `신규 ${j.items_new}건 · 중복 ${j.items_duplicate}건 · 수정 ${j.items_updated}건 · 실패 ${j.items_failed}건`;
}

export default function SourcesPage() {
  const router = useRouter();
  const [sources, setSources] = useState<SourceOut[]>([]);
  const [role, setRole] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [fieldCode, setFieldCode] = useState("");
  const [jobs, setJobs] = useState<Record<string, CollectionJob>>({});  // 정보원별 최근/진행 작업
  const [msg, setMsg] = useState<{ kind: "ok" | "err"; text: string } | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [runs, setRuns] = useState<CollectionRunOut[]>([]);
  const [history, setHistory] = useState<{ action: string; at: string; actor: string }[]>([]);
  const [form, setForm] = useState<(SourceInput & { id?: string }) | null>(null);
  const [test, setTest] = useState<ConnectionTestResult | "running" | null>(null);
  const timers = useRef<Record<string, ReturnType<typeof setTimeout>>>({});

  const canManage = role === "admin" || role === "source_admin";
  const canRun = canManage || role === "approver" || role === "reviewer";

  const load = useCallback(() => {
    setLoading(true);
    listSources({ field_code: fieldCode || undefined })
      .then(setSources)
      .catch((err) => {
        if (err instanceof UnauthorizedError) { router.push("/login"); return; }
        setError(err instanceof Error ? err.message : "불러오기 실패");
      })
      .finally(() => setLoading(false));
  }, [fieldCode, router]);

  useEffect(() => { getCurrentUser().then((u) => setRole(u.role)).catch(() => undefined); }, []);
  useEffect(load, [load]);
  useEffect(() => () => { Object.values(timers.current).forEach(clearTimeout); }, []);

  // 작업 상태를 서버에서 조회해 완료될 때까지 따라간다(화면을 닫아도 서버 작업은 계속된다)
  const follow = useCallback((sourceId: string, jobId: string) => {
    const tick = async () => {
      try {
        const j = await getCollectionJob(jobId);
        setJobs((p) => ({ ...p, [sourceId]: j }));
        if (j.status === "queued" || j.status === "running") { timers.current[jobId] = setTimeout(tick, 1500); return; }
        load();
        if (j.status === "succeeded") setMsg({ kind: "ok", text: `수집 완료: ${jobSummary(j)}` });
        else setMsg({ kind: "err", text: `수집 ${JOB_LABEL[j.status] ?? j.status}: ${j.error_message ?? "원인을 확인하세요"}` });
      } catch { /* 일시 오류는 다음 주기에 다시 조회 */ timers.current[jobId] = setTimeout(tick, 3000); }
    };
    tick();
  }, [load]);

  async function collect(s: SourceOut) {
    setMsg(null);
    try {
      const r = await startCollection(s.id);
      setJobs((p) => ({ ...p, [s.id]: r.job }));
      if (r.already_running) setMsg({ kind: "ok", text: "이미 진행 중인 수집 작업이 있어 그 작업을 보여 드립니다." });
      follow(s.id, r.job.id);
    } catch (err) { setMsg({ kind: "err", text: err instanceof Error ? err.message : "수집을 시작하지 못했습니다" }); }
  }

  async function cancel(s: SourceOut) {
    const j = jobs[s.id];
    if (!j) return;
    try { setJobs((p) => ({ ...p, [s.id]: { ...j, cancel_requested: true } })); await cancelCollectionJob(j.id); } catch (err) { setMsg({ kind: "err", text: err instanceof Error ? err.message : "취소 실패" }); }
  }

  async function toggleActive(s: SourceOut) {
    try { await updateSource(s.id, { is_active: !s.is_active }); setMsg({ kind: "ok", text: s.is_active ? `'${s.name}'을(를) 비활성화했습니다(이력은 보존됩니다)` : `'${s.name}'을(를) 활성화했습니다` }); load(); }
    catch (err) { setMsg({ kind: "err", text: err instanceof Error ? err.message : "변경 실패" }); }
  }

  async function openDetail(s: SourceOut) {
    if (expanded === s.id) { setExpanded(null); return; }
    setExpanded(s.id);
    setRuns(await listSourceRuns(s.id).catch(() => []));
    setHistory(canManage ? await getSourceHistory(s.id).catch(() => []) : []);
    const js = await listSourceJobs(s.id).catch(() => []);
    if (js[0] && (js[0].status === "queued" || js[0].status === "running")) follow(s.id, js[0].id);
  }

  async function runTest() {
    if (!form) return;
    setTest("running");
    try { setTest(await testSourceConnection({ url: form.url, source_type: form.source_type, api_provider: form.api_provider, config_json: form.config_json || null, respect_robots: form.respect_robots, min_request_interval_seconds: form.min_request_interval_seconds })); }
    catch (err) { setTest({ ok: false, found: 0, access_status: "error", message: err instanceof Error ? err.message : "연결 테스트 실패", sample: [] }); }
  }

  async function save(e: React.FormEvent) {
    e.preventDefault();
    if (!form) return;
    setMsg(null);
    const { id, ...body } = form;
    const payload = { ...body, config_json: body.config_json || null, country_code: body.country_code || null, api_provider: body.source_type === "api" ? body.api_provider : null };
    try {
      if (id) await updateSource(id, payload); else await createSource(payload);
      setMsg({ kind: "ok", text: id ? "정보원 설정을 저장했습니다" : "정보원을 등록했습니다. 연결 테스트 후 '지금 수집'으로 확인하세요." });
      setForm(null); setTest(null); load();
    } catch (err) { setMsg({ kind: "err", text: err instanceof Error ? err.message : "저장 실패" }); }
  }

  const edit = (s: SourceOut) => { setTest(null); setForm({ id: s.id, name: s.name, org_name: s.org_name, field_code: s.field_code, url: s.url, source_type: s.source_type, api_provider: s.api_provider, country_code: s.country_code ?? "",
    interval_minutes: s.interval_minutes, min_request_interval_seconds: s.min_request_interval_seconds, respect_robots: s.respect_robots, config_json: s.config_json ?? "", description: s.description ?? "" }); };
  const set = <K extends keyof SourceInput>(k: K, v: SourceInput[K]) => form && setForm({ ...form, [k]: v });

  return (
    <AppShell>
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
        <div>
          <h1 style={{ fontSize: 22, fontWeight: 700, margin: "0 0 4px" }}>출처·수집 관리</h1>
          <p style={{ color: "var(--ink-muted)", fontSize: 13, margin: "0 0 18px" }}>공식 정보원의 접속 상태를 확인하고 수집을 실행합니다. 공식 API·RSS를 우선하며, 접속이 거부되면 우회하지 않고 사유를 표시합니다.</p>
        </div>
        {canManage && <button className="tbtn primary" onClick={() => { setTest(null); setForm({ ...emptyForm }); }}>정보원 등록</button>}
      </div>

      {msg && <div role={msg.kind === "err" ? "alert" : "status"} className={`notice ${msg.kind}`} style={{ marginBottom: 14 }} data-testid="source-msg">{msg.text}</div>}
      {error && <div role="alert" className="notice err" style={{ marginBottom: 14 }}>{error}</div>}

      {form && (
        <form className="panel" onSubmit={save} style={{ marginBottom: 18 }} data-testid="source-form">
          <h2 className="section-title">{form.id ? "정보원 편집" : "새 정보원 등록"}</h2>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: "0 18px" }}>
            <label className="field">정보원명<input required value={form.name} onChange={(e) => set("name", e.target.value)} /></label>
            <label className="field">발행기관<input required value={form.org_name} onChange={(e) => set("org_name", e.target.value)} /></label>
            <label className="field">ICT 분야<select value={form.field_code} onChange={(e) => set("field_code", e.target.value)}>{Object.entries(FIELD_LABELS).map(([c, l]) => <option key={c} value={c}>{l}</option>)}</select></label>
            <label className="field">국가·지역 코드(예: US, EU, JP, INT)<input value={form.country_code ?? ""} onChange={(e) => set("country_code", e.target.value.toUpperCase())} maxLength={10} /></label>
            <label className="field" style={{ gridColumn: "1 / -1" }}>공식 주소(URL)<input required type="url" value={form.url} onChange={(e) => set("url", e.target.value)} placeholder="https://" /></label>
            <label className="field">수집 방식<select value={form.source_type} onChange={(e) => set("source_type", e.target.value)}>{Object.entries(METHODS).map(([c, l]) => <option key={c} value={c}>{l}</option>)}</select></label>
            {form.source_type === "api"
              ? <label className="field">API 공급자<select value={form.api_provider ?? ""} onChange={(e) => set("api_provider", e.target.value)} required><option value="">선택</option>{Object.entries(API_PROVIDERS).map(([c, l]) => <option key={c} value={c}>{l}</option>)}</select></label>
              : <div />}
            <label className="field">자동 수집 주기<select value={form.interval_minutes} onChange={(e) => set("interval_minutes", Number(e.target.value))}>{INTERVALS.map(([m, l]) => <option key={m} value={m}>{l}</option>)}</select></label>
            <label className="field">같은 사이트 요청 최소 간격(초)<input type="number" min={0} max={30} step={0.5} value={form.min_request_interval_seconds} onChange={(e) => set("min_request_interval_seconds", Number(e.target.value))} /></label>
            {(form.source_type === "html" || form.source_type === "pdf") && (
              <label className="field" style={{ gridColumn: "1 / -1" }}>추가 설정(JSON — 예: {"{"}"link_pattern": "/news/\d+"{"}"} 또는 {"{"}"title": "문서 제목"{"}"})<input value={form.config_json ?? ""} onChange={(e) => set("config_json", e.target.value)} /></label>
            )}
            <label className="field" style={{ gridColumn: "1 / -1" }}>설명(선택)<input value={form.description ?? ""} onChange={(e) => set("description", e.target.value)} /></label>
          </div>
          <label style={{ fontSize: 13 }}><input type="checkbox" checked={form.respect_robots} onChange={(e) => set("respect_robots", e.target.checked)} /> robots.txt를 준수합니다(권장 — 거부된 주소는 우회하지 않음)</label>
          <div style={{ display: "flex", gap: 8, marginTop: 14 }}>
            <button type="button" className="tbtn" onClick={runTest} disabled={!form.url || test === "running"} data-testid="source-test">{test === "running" ? "접속 확인 중..." : "연결 테스트"}</button>
            <button type="submit" className="tbtn primary" data-testid="source-save">저장</button>
            <button type="button" className="tbtn" onClick={() => { setForm(null); setTest(null); }}>취소</button>
          </div>
          {test && test !== "running" && (
            <div className={`notice ${test.ok ? "ok" : "err"}`} style={{ marginTop: 12 }} data-testid="source-test-result">
              <b>{test.ok ? "연결 성공" : "연결 실패"}</b> — {test.message}
              {test.sample.length > 0 && <ul style={{ margin: "6px 0 0", paddingLeft: 18 }}>{test.sample.map((s) => <li key={s.link}>{s.title}</li>)}</ul>}
            </div>
          )}
        </form>
      )}

      <div className="panel" style={{ display: "flex", gap: 10, marginBottom: 14, alignItems: "center" }}>
        <select aria-label="분야 필터" value={fieldCode} onChange={(e) => setFieldCode(e.target.value)} style={selectStyle}>
          <option value="">전체 분야</option>
          {Object.entries(FIELD_LABELS).map(([c, l]) => <option key={c} value={c}>{l}</option>)}
        </select>
        <span style={{ marginLeft: "auto", fontSize: 13, color: "var(--ink-muted)" }}>총 {sources.length}곳</span>
      </div>
      {loading && <p role="status" style={{ color: "var(--ink-muted)" }}>불러오는 중...</p>}

      <div className="panel" style={{ padding: 0, overflow: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
          <thead>
            <tr style={{ textAlign: "left", background: "var(--panel-2)" }}>
              <th style={th}>정보원</th><th style={th}>국가·분야</th><th style={th}>방식·주기</th><th style={th}>접속 상태</th><th style={th}>최근 성공 · 신규</th><th style={th} />
            </tr>
          </thead>
          <tbody>
            {sources.map((s) => {
              const j = jobs[s.id];
              const active = j && (j.status === "queued" || j.status === "running");
              return (
                <Fragment key={s.id}>
                  <tr style={{ borderTop: "1px solid var(--border)", opacity: s.is_active ? 1 : 0.6 }} data-testid="source-row">
                    <td style={td}>
                      <b>{s.name}</b>{!s.is_active && <span className="badge" style={{ marginLeft: 6 }}>비활성</span>}
                      <div style={{ fontSize: 12, color: "var(--ink-muted)" }}>{s.org_name}</div>
                      <a href={s.url} target="_blank" rel="noopener noreferrer" style={{ fontSize: 11.5 }}>공식 주소 ↗</a>
                    </td>
                    <td style={td}>{s.country_code ?? "-"}<div style={{ fontSize: 12, color: "var(--ink-muted)" }}>{FIELD_LABELS[s.field_code] ?? s.field_code}</div></td>
                    <td style={td}><span className="badge">{METHODS[s.source_type] ?? s.source_type}</span><div style={{ fontSize: 12, color: "var(--ink-muted)", marginTop: 3 }}>{INTERVALS.find(([m]) => m === s.interval_minutes)?.[1] ?? `${s.interval_minutes}분마다`}</div></td>
                    <td style={td}>
                      <span className={`badge ${ACCESS_TONE[s.access_status] ?? ""}`} data-testid="source-access">{s.access_label}</span>
                      {s.consecutive_failures > 0 && <span className="badge bad" style={{ marginLeft: 4 }}>연속 실패 {s.consecutive_failures}</span>}
                      {s.access_note && s.access_status !== "ok" && <div style={{ fontSize: 11.5, color: "var(--ink-muted)", marginTop: 3, maxWidth: 260 }}>{s.access_note}</div>}
                    </td>
                    <td style={td}>{fmtDate(s.last_successful_collection_at)}<div style={{ fontSize: 12, color: "var(--ink-muted)" }}>최근 신규 {s.last_new_count}건</div></td>
                    <td style={{ ...td, whiteSpace: "nowrap", textAlign: "right" }}>
                      {canRun && <button className="tbtn primary" disabled={!s.is_active || !!active} onClick={() => collect(s)} data-testid="collect-now">{active ? "수집 중..." : "지금 수집"}</button>}{" "}
                      {canManage && <button className="tbtn" onClick={() => edit(s)}>편집</button>}{" "}
                      {canManage && <button className="tbtn" onClick={() => toggleActive(s)}>{s.is_active ? "비활성화" : "활성화"}</button>}{" "}
                      <button className="tbtn" onClick={() => openDetail(s)}>{expanded === s.id ? "접기" : "이력"}</button>
                    </td>
                  </tr>
                  {j && (
                    <tr key={`${s.id}-job`} data-testid="job-row"><td colSpan={6} style={{ padding: "0 12px 10px" }}>
                      <div className={`notice ${j.status === "succeeded" ? "ok" : j.status === "queued" || j.status === "running" ? "info" : "err"}`} data-testid="job-status" data-job-status={j.status}>
                        <b>{JOB_LABEL[j.status] ?? j.status}</b>{j.stage && active ? ` · ${j.stage}` : ""} — {jobSummary(j)}{j.error_message ? ` · ${j.error_message}` : ""}
                        {active && <button className="tbtn" style={{ marginLeft: 10, padding: "3px 10px" }} onClick={() => cancel(s)} disabled={j.cancel_requested}>{j.cancel_requested ? "취소 요청됨" : "취소"}</button>}
                      </div>
                    </td></tr>
                  )}
                  {expanded === s.id && (
                    <tr key={`${s.id}-detail`}><td colSpan={6} style={{ padding: "0 12px 14px" }}>
                      <div style={{ fontSize: 12.5, fontWeight: 700, margin: "6px 0" }}>최근 수집 결과</div>
                      <table style={{ width: "100%", fontSize: 12.5, borderCollapse: "collapse" }}>
                        <thead><tr style={{ textAlign: "left", color: "var(--ink-muted)" }}><th style={{ padding: 5 }}>시작</th><th>상태</th><th>찾음</th><th>신규</th><th>중복</th><th>수정</th><th>오류</th></tr></thead>
                        <tbody>
                          {runs.slice(0, 10).map((r) => (
                            <tr key={r.id} style={{ borderTop: "1px solid var(--border)" }}><td style={{ padding: 5 }}>{fmtDate(r.started_at)}</td><td>{r.status}</td><td>{r.items_found}</td><td>{r.items_new}</td><td>{r.items_duplicate}</td><td>{r.items_updated}</td><td style={{ color: "var(--bad)" }}>{r.error_message ?? "-"}</td></tr>
                          ))}
                          {runs.length === 0 && <tr><td colSpan={7} style={{ padding: 8, color: "var(--ink-muted)" }}>수집 이력이 없습니다</td></tr>}
                        </tbody>
                      </table>
                      {canManage && history.length > 0 && (
                        <>
                          <div style={{ fontSize: 12.5, fontWeight: 700, margin: "10px 0 4px" }}>설정 변경·작업 이력</div>
                          <div style={{ fontSize: 12, color: "var(--ink-muted)" }}>{history.slice(0, 8).map((h) => `${fmtDate(h.at)} ${h.actor} · ${h.action}`).join("  /  ")}</div>
                        </>
                      )}
                    </td></tr>
                  )}
                </Fragment>
              );
            })}
            {!loading && sources.length === 0 && <tr><td colSpan={6} style={{ padding: 20, textAlign: "center", color: "var(--ink-muted)" }}>등록된 출처가 없습니다. {canManage ? "'정보원 등록'으로 공식 정보원을 추가하세요." : ""}</td></tr>}
          </tbody>
        </table>
      </div>
    </AppShell>
  );
}

const selectStyle: React.CSSProperties = { padding: "7px 9px", borderRadius: 8, border: "1px solid var(--border)", fontSize: 13 };
const th: React.CSSProperties = { padding: "9px 12px", whiteSpace: "nowrap" };
const td: React.CSSProperties = { padding: "10px 12px", verticalAlign: "top" };
