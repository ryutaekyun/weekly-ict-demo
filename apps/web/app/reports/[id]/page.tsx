"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import AppShell from "@/components/AppShell";
import {
  addReportItem, addSummaryItem, createReportExport, deleteReportItem, fetchReportExportBlob, finalizeReport,
  getCurrentUser, getReport, getSourceSentences, listManuscripts, listReportExports, reopenReport,
  reorderReportItems, updateReport, updateReportItem, UnauthorizedError,
  type CurrentUser, type ManuscriptListItem, type PreflightIssue, type ReportDetail, type ReportExportOut,
  type ReportItemOut,
} from "@/lib/api";
import { fmtDate, REPORT_STATUS_LABELS, REPORT_TYPE_LABELS } from "@/lib/labels";

const GENERAL_PARTS: { key: string; label: string; required: boolean }[] = [
  { key: "key_issue", label: "Ⅰ. 주요 이슈", required: true },
  { key: "country_trend", label: "Ⅱ. 주요국 동향", required: true },
  { key: "field_brief", label: "Ⅲ. ICT 9대 분야 주요 단신", required: false },
  { key: "schedule", label: "Ⅳ. 주요 일정", required: false },
];
const SUMMARY_PARTS = [
  { key: "key_issue", label: "Ⅰ. 주요 이슈 요약" },
  { key: "country_trend", label: "Ⅱ. 주요국 동향 요약" },
  { key: "key_message", label: "Ⅲ. 핵심 메시지" },
];
const MS_STATUS: Record<string, string> = {
  draft: "초안", review_requested: "검토 요청됨", changes_requested: "수정 요청됨", approved: "내부 확정", final: "최종",
};
// minWidth:0 — 긴 원고 제목이 있는 select가 flex 안에서 줄어들지 못해 옆 칸을 덮는 문제를 막는다
const inp: React.CSSProperties = { padding: 7, borderRadius: 8, border: "1px solid var(--border)", fontSize: 13, minWidth: 0, maxWidth: "100%" };
const LEVEL_STYLE: Record<string, { label: string; color: string }> = {
  error: { label: "필수", color: "#b42318" }, warn: { label: "경고", color: "#9a4b00" }, info: { label: "안내", color: "#475467" },
};

function sizeLabel(n: number | null): string {
  if (n === null) return "-";
  return n > 1024 * 1024 ? `${(n / 1024 / 1024).toFixed(1)}MB` : `${Math.max(1, Math.round(n / 1024))}KB`;
}

export default function ReportDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const [me, setMe] = useState<CurrentUser | null>(null);
  const [report, setReport] = useState<ReportDetail | null>(null);
  const [manuscripts, setManuscripts] = useState<ManuscriptListItem[]>([]);
  const [exportsList, setExportsList] = useState<ReportExportOut[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [pick, setPick] = useState<Record<string, string>>({});
  const [summaryMs, setSummaryMs] = useState("");
  const [sentences, setSentences] = useState<string[]>([]);
  const [summaryPart, setSummaryPart] = useState("key_issue");
  const [exceptionReason, setExceptionReason] = useState("");
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [titleDraft, setTitleDraft] = useState("");
  const previewRef = useRef<string | null>(null);

  const routerRef = useRef(router);
  routerRef.current = router;
  // router 객체 정체성에 의존하지 않도록 ref를 쓴다(의존하면 매 렌더마다 재조회가 반복될 수 있다)
  const fail = useCallback((err: unknown) => {
    if (err instanceof UnauthorizedError) { routerRef.current.push("/login"); return; }
    setMessage(null);
    setError(err instanceof Error ? err.message : "요청 실패");
  }, []);

  const load = useCallback(() => {
    getReport(params.id).then((r) => { setReport(r); setTitleDraft(r.title); }).catch(fail);
    listReportExports(params.id).then(setExportsList).catch(() => setExportsList([]));
  }, [params.id, fail]);

  useEffect(() => {
    getCurrentUser().then(setMe).catch(() => {});
    listManuscripts().then(setManuscripts).catch(() => {});
    load();
  }, [load]);

  useEffect(() => () => { if (previewRef.current) URL.revokeObjectURL(previewRef.current); }, []);

  useEffect(() => {
    if (!summaryMs) { setSentences([]); return; }
    getSourceSentences(summaryMs).then((r) => setSentences(r.sentences)).catch(fail);
  }, [summaryMs, fail]);

  if (!report) return <AppShell>{error ? <p role="alert" style={{ color: "#b42318" }}>{error}</p> : <p>불러오는 중...</p>}</AppShell>;

  const locked = report.status === "final";
  const canApprove = me?.role === "admin" || me?.role === "approver";

  async function run<T>(label: string, fn: () => Promise<T>, after?: (v: T) => void) {
    setBusy(label); setError(null); setMessage(null);
    try {
      const v = await fn();
      after?.(v);
    } catch (err) { fail(err); } finally { setBusy(null); }
  }

  const applyDetail = (r: ReportDetail) => { setReport(r); setTitleDraft(r.title); };

  function move(item: ReportItemOut, delta: number, scope: ReportItemOut[]) {
    const ids = scope.map((i) => i.id);
    const idx = ids.indexOf(item.id);
    const target = idx + delta;
    if (target < 0 || target >= ids.length) return;
    [ids[idx], ids[target]] = [ids[target], ids[idx]];
    // 전체 순서 배열로 환산: 범위 밖 항목은 현재 순서를 유지한다
    const others = report!.items.filter((i) => !scope.includes(i)).map((i) => i.id);
    run("reorder", () => reorderReportItems(report!.id, [...ids, ...others]), applyDetail);
  }

  async function download(exp: ReportExportOut) {
    await run("download", async () => {
      const blob = await fetchReportExportBlob(report!.id, exp.id);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = exp.file_name ?? `report.${exp.file_format}`;
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 5000);
      setMessage(`${exp.file_format.toUpperCase()} 파일을 내려받았습니다 (${exp.file_name})`);
    });
  }

  async function preview(exp: ReportExportOut) {
    await run("preview", async () => {
      const blob = await fetchReportExportBlob(report!.id, exp.id);
      if (previewRef.current) URL.revokeObjectURL(previewRef.current);
      const url = URL.createObjectURL(blob);
      previewRef.current = url;
      setPreviewUrl(url);
    });
  }

  async function exportAndDownload(fmt: "docx" | "pdf") {
    await run(`export-${fmt}`, async () => {
      const exp = await createReportExport(report!.id, fmt);
      setExportsList(await listReportExports(report!.id));
      if (exp.status !== "success") throw new Error(`${fmt.toUpperCase()} 생성 실패: ${exp.error_message ?? "알 수 없는 오류"}`);
      const blob = await fetchReportExportBlob(report!.id, exp.id);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = exp.file_name ?? `report.${fmt}`;
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 5000);
      setMessage(`${fmt.toUpperCase()} 파일을 생성하고 내려받았습니다 (${exp.file_name}, ${sizeLabel(exp.file_size)}${exp.page_count ? `, ${exp.page_count}페이지` : ""})`);
      if (fmt === "pdf") await preview(exp);
      load();
    });
  }

  const itemsOf = (key: string) => report.items.filter((i) => i.part_key === key && i.manuscript_id);
  const freeItems = report.items.filter((i) => i.manuscript_id);
  const summaryItemsOf = (key: string) => report.items.filter((i) => i.part_key === key && i.summary_text !== null);

  // 컴포넌트가 아니라 렌더 함수로 둔다 — 안에서 컴포넌트를 선언하면 렌더마다 DOM이 새로 만들어져 클릭이 불안정해진다
  function renderPartAdder(partKey: string) {
    const chosen = pick[partKey] ?? "";
    const used = new Set(report!.items.map((i) => i.manuscript_id));
    return (
      <div key={`adder-${partKey}`} style={{ display: "flex", gap: 6, marginTop: 8 }}>
        <select aria-label={`${partKey} 원고 선택`} value={chosen} onChange={(e) => setPick({ ...pick, [partKey]: e.target.value })} style={{ ...inp, flex: 1 }} disabled={locked}>
          <option value="">배치할 원고 선택</option>
          {manuscripts.filter((m) => !used.has(m.id)).map((m) => <option key={m.id} value={m.id}>{m.title}{m.is_pilot ? " (시범)" : ""} · {MS_STATUS[m.status] ?? m.status}</option>)}
        </select>
        <button className="tbtn" disabled={!chosen || locked || busy !== null}
          onClick={() => run("add", () => addReportItem(report!.id, { part_key: partKey, manuscript_id: chosen }), (r) => { applyDetail(r); setPick({ ...pick, [partKey]: "" }); })}>
          원고 배치
        </button>
      </div>
    );
  }

  function renderItemRow(item: ReportItemOut, scope: ReportItemOut[]) {
    return (
      <div key={item.id} style={{ display: "flex", alignItems: "center", gap: 8, padding: "6px 0", borderTop: "1px solid var(--border)" }}>
        <div style={{ flex: 1 }}>
          <Link href={`/manuscripts/${item.manuscript_id}`}>{item.manuscript_title}</Link>
          <span className={`pill ${item.manuscript_status === "approved" ? "rec" : "review"}`} style={{ marginLeft: 6 }}>{MS_STATUS[item.manuscript_status ?? ""] ?? item.manuscript_status}</span>
        </div>
        <button className="tbtn" aria-label="위로" disabled={locked} onClick={() => move(item, -1, scope)}>↑</button>
        <button className="tbtn" aria-label="아래로" disabled={locked} onClick={() => move(item, 1, scope)}>↓</button>
        <button className="tbtn" disabled={locked} onClick={() => run("del", () => deleteReportItem(report!.id, item.id), applyDetail)}>제거</button>
      </div>
    );
  }

  const issueGroups: Record<string, PreflightIssue[]> = { error: [], warn: [], info: [] };
  report.preflight.forEach((i) => issueGroups[i.level]?.push(i));

  return (
    <AppShell>
      <div style={{ marginBottom: 10 }}><Link href="/reports" style={{ fontSize: 13 }}>← 보고서 목록으로</Link></div>
      <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap", marginBottom: 8 }}>
        <input aria-label="보고서 제목" value={titleDraft} disabled={locked} onChange={(e) => setTitleDraft(e.target.value)}
          onBlur={() => { if (titleDraft.trim() && titleDraft !== report.title) run("title", () => updateReport(report.id, { title: titleDraft.trim() }), applyDetail); }}
          style={{ ...inp, fontSize: 18, fontWeight: 700, flex: 1, minWidth: 260 }} />
        <span className="pill review">{REPORT_TYPE_LABELS[report.report_type]}</span>
        {report.report_type === "summary" && <span className="pill hold">{report.layout === "compact" ? "간결형" : "정식형"}</span>}
        <span className={`pill ${locked ? "rec" : "review"}`}>{REPORT_STATUS_LABELS[report.status] ?? report.status}</span>
        <span className="pill hold">{report.iitp_confirmed ? "IITP 확인 완료" : "IITP 공식 확인 전"}</span>
      </div>
      {error && <p role="alert" style={{ color: "#b42318", fontSize: 13 }}>{error}</p>}
      {message && <p role="status" style={{ color: "var(--ok)", fontSize: 13 }}>{message}</p>}

      <div style={{ display: "grid", gridTemplateColumns: "minmax(0,3fr) minmax(0,2fr)", gap: 14, alignItems: "start" }}>
        {/* 구성 */}
        <div style={{ minWidth: 0 }}>
          <div className="panel" style={{ marginBottom: 14 }}>
            <h2 style={{ fontSize: 14, margin: "0 0 8px" }}>① 보고서 구성</h2>
            {report.report_type === "general" && GENERAL_PARTS.map((p) => (
              <div key={p.key} style={{ marginBottom: 12 }}>
                <div style={{ fontWeight: 700, fontSize: 13 }}>{p.label} {p.required ? <span style={{ color: "#b42318", fontSize: 11 }}>(필수)</span> : null}</div>
                {itemsOf(p.key).map((it) => renderItemRow(it, itemsOf(p.key)))}
                {itemsOf(p.key).length === 0 && <div style={{ color: "var(--ink-muted)", fontSize: 12.5, padding: "4px 0" }}>배치된 원고 없음 — 비워 두면 출력본에 &ldquo;원고 미배치(미완성)&rdquo;로 표시됩니다</div>}
                {renderPartAdder(p.key)}
              </div>
            ))}

            {report.report_type === "special" && (
              <div>
                <p style={{ fontSize: 12.5, color: "var(--ink-muted)", marginTop: 0 }}>특집호는 일반호 목차를 강제하지 않습니다. 소제목과 원고 순서를 직접 정하세요.</p>
                {freeItems.map((it) => (
                  <div key={it.id}>
                    {renderItemRow(it, freeItems)}
                    <input aria-label={`소제목: ${it.manuscript_title}`} defaultValue={it.heading ?? ""} placeholder="소제목(비우면 원고 제목 사용)" disabled={locked}
                      onBlur={(e) => { if ((e.target.value || "") !== (it.heading ?? "")) run("heading", () => updateReportItem(report.id, it.id, { heading: e.target.value }), applyDetail); }}
                      style={{ ...inp, width: "100%", marginBottom: 6 }} />
                  </div>
                ))}
                {renderPartAdder("free")}
              </div>
            )}

            {report.report_type === "summary" && (
              <div>
                <p style={{ fontSize: 12.5, color: "var(--ink-muted)", marginTop: 0 }}>
                  AI 자동 요약이 아닙니다. 원고에서 핵심 문장을 직접 골라 요약본에 넣고 다듬습니다. 원고가 바뀌면 &ldquo;재검토 필요&rdquo;로 표시되며, 다듬은 요약문은 자동으로 덮어쓰이지 않습니다.
                </p>
                {SUMMARY_PARTS.map((p) => (
                  <div key={p.key} style={{ marginBottom: 12 }}>
                    <div style={{ fontWeight: 700, fontSize: 13 }}>{p.label}</div>
                    {summaryItemsOf(p.key).map((it) => (
                      <div key={it.id} style={{ borderTop: "1px solid var(--border)", padding: "6px 0" }}>
                        <textarea aria-label={`요약문: ${it.source_sentence?.slice(0, 20)}`} defaultValue={it.summary_text ?? ""} disabled={locked}
                          onBlur={(e) => { if (e.target.value !== it.summary_text) run("summary", () => updateReportItem(report.id, it.id, { summary_text: e.target.value }), applyDetail); }}
                          style={{ ...inp, width: "100%", minHeight: 54 }} />
                        <div style={{ fontSize: 11.5, color: "var(--ink-muted)", display: "flex", gap: 8, alignItems: "center" }}>
                          <span>원본: <Link href={`/manuscripts/${it.manuscript_id}`}>{it.manuscript_title}</Link></span>
                          {it.needs_review && <span className="pill hold">원고 변경 — 요약본 재검토 필요</span>}
                          <button className="tbtn" style={{ marginLeft: "auto" }} disabled={locked} onClick={() => run("del", () => deleteReportItem(report.id, it.id), applyDetail)}>제거</button>
                        </div>
                      </div>
                    ))}
                  </div>
                ))}
                <div className="panel" style={{ background: "var(--panel-2)" }}>
                  <div style={{ fontWeight: 700, fontSize: 13, marginBottom: 6 }}>원고에서 핵심 문장 선택</div>
                  <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                    <select aria-label="요약 대상 원고" value={summaryMs} onChange={(e) => setSummaryMs(e.target.value)} style={{ ...inp, flex: 1 }} disabled={locked}>
                      <option value="">원고 선택</option>
                      {manuscripts.map((m) => <option key={m.id} value={m.id}>{m.title}</option>)}
                    </select>
                    <select aria-label="요약본 파트" value={summaryPart} onChange={(e) => setSummaryPart(e.target.value)} style={inp} disabled={locked}>
                      {SUMMARY_PARTS.map((p) => <option key={p.key} value={p.key}>{p.label}</option>)}
                    </select>
                  </div>
                  <div style={{ maxHeight: 190, overflow: "auto", marginTop: 6 }}>
                    {sentences.map((s, idx) => (
                      <div key={idx} style={{ display: "flex", gap: 6, alignItems: "flex-start", padding: "4px 0", borderTop: "1px solid var(--border)", fontSize: 12.5 }}>
                        <span style={{ flex: 1 }}>{s}</span>
                        <button className="tbtn" disabled={locked || busy !== null}
                          onClick={() => run("sum-add", () => addSummaryItem(report.id, { part_key: summaryPart, manuscript_id: summaryMs, source_sentence: s }), applyDetail)}>
                          요약에 추가
                        </button>
                      </div>
                    ))}
                    {summaryMs && sentences.length === 0 && <div style={{ color: "var(--ink-muted)", fontSize: 12.5 }}>선택할 문단이 없습니다(원고 본문이 비어 있음)</div>}
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* 점검·출력·확정 */}
        <div style={{ minWidth: 0 }}>
          <div className="panel" style={{ marginBottom: 14 }}>
            <h2 style={{ fontSize: 14, margin: "0 0 8px" }}>② 발간 점검</h2>
            {report.preflight.length === 0 && <p style={{ color: "var(--ink-muted)", fontSize: 12.5 }}>점검 항목이 없습니다</p>}
            {(["error", "warn", "info"] as const).map((lvl) => issueGroups[lvl].map((i, idx) => (
              <div key={`${lvl}-${idx}`} style={{ fontSize: 12.5, padding: "4px 0", borderTop: "1px solid var(--border)" }}>
                <span style={{ color: LEVEL_STYLE[lvl].color, fontWeight: 700 }}>[{LEVEL_STYLE[lvl].label}]</span> {i.message}
              </div>
            )))}
          </div>

          <div className="panel" style={{ marginBottom: 14 }}>
            <h2 style={{ fontSize: 14, margin: "0 0 8px" }}>③ 출력 · 다운로드</h2>
            <p style={{ fontSize: 12, color: "var(--ink-muted)", marginTop: 0 }}>
              누르는 순간의 원고 버전·템플릿으로 고정(스냅샷)해 실제 파일을 생성합니다. 임시 표준 템플릿(IITP 공식 양식 아님).
              검증 미완료여도 내부 검토용 초안은 출력할 수 있습니다.
            </p>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              <button className="tbtn primary" disabled={busy !== null} onClick={() => exportAndDownload("docx")}>
                {busy === "export-docx" ? "DOCX 생성 중..." : "DOCX 다운로드"}
              </button>
              <button className="tbtn primary" disabled={busy !== null} onClick={() => exportAndDownload("pdf")}>
                {busy === "export-pdf" ? "PDF 생성 중..." : "PDF 다운로드"}
              </button>
            </div>
            {previewUrl && (
              <div style={{ marginTop: 10 }}>
                <div style={{ fontSize: 12.5, fontWeight: 700, marginBottom: 4 }}>PDF 미리보기</div>
                <iframe title="PDF 미리보기" src={previewUrl} style={{ width: "100%", height: 460, border: "1px solid var(--border)", borderRadius: 8 }} />
              </div>
            )}
          </div>

          <div className="panel" style={{ marginBottom: 14 }}>
            <h2 style={{ fontSize: 14, margin: "0 0 8px" }}>④ 출력 이력 (이전 출력본)</h2>
            {exportsList.length === 0 && <p style={{ color: "var(--ink-muted)", fontSize: 12.5 }}>아직 출력한 파일이 없습니다</p>}
            {exportsList.map((e) => (
              <div key={e.id} style={{ borderTop: "1px solid var(--border)", padding: "6px 0", fontSize: 12 }}>
                <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
                  <b>{e.file_format.toUpperCase()}</b>
                  <span className={`pill ${e.status === "success" ? "rec" : e.status === "failed" ? "hold" : "review"}`}>{e.status === "success" ? "성공" : e.status === "failed" ? "실패" : "진행 중"}</span>
                  {e.is_final && <span className="pill rec">확정본</span>}
                  <span style={{ color: "var(--ink-muted)" }}>{fmtDate(e.created_at)}</span>
                  {e.status === "success" && <button className="tbtn" style={{ marginLeft: "auto" }} onClick={() => download(e)}>재다운로드</button>}
                  {e.status === "success" && e.file_format === "pdf" && <button className="tbtn" onClick={() => preview(e)}>미리보기</button>}
                </div>
                {e.status === "failed" && <div style={{ color: "#b42318" }}>{e.error_message}</div>}
                {e.status === "success" && (
                  <div style={{ color: "var(--ink-muted)" }}>
                    {e.page_count ? `${e.page_count}쪽 · ` : "페이지 수 미확인 · "}각주 {e.footnote_count ?? 0} · 표 {e.table_count ?? 0} · {sizeLabel(e.file_size)} · 템플릿 v{e.template_version} · SHA-256 {e.file_sha256?.slice(0, 10)}…
                  </div>
                )}
              </div>
            ))}
          </div>

          <div className="panel">
            <h2 style={{ fontSize: 14, margin: "0 0 8px" }}>⑤ 출력용 확정</h2>
            <p style={{ fontSize: 12, color: "var(--ink-muted)", marginTop: 0 }}>
              출력용 확정은 내부 절차이며 IITP 공식 확인이 아닙니다. 필수 점검(필수 파트·미검증 각주·미승인 원고 등)을 통과하지 못하면 승인권자가 예외 사유를 남겨야 합니다.
            </p>
            {report.finalize_exception_reason && <p style={{ fontSize: 12.5 }}>예외 사유: {report.finalize_exception_reason}</p>}
            {!locked && report.blocking.length > 0 && (
              <p style={{ fontSize: 12.5, color: "#9a4b00" }}>확정을 막는 점검 항목 {report.blocking.length}건이 있습니다.</p>
            )}
            {!locked && canApprove && (
              <div style={{ display: "flex", gap: 6, flexDirection: "column" }}>
                <textarea aria-label="예외 승인 사유" placeholder="예외 승인 사유(필수 점검 미통과 시 입력)" value={exceptionReason} onChange={(e) => setExceptionReason(e.target.value)} style={{ ...inp, minHeight: 50 }} />
                <button className="tbtn primary" disabled={busy !== null} onClick={() => run("finalize", () => finalizeReport(report.id, exceptionReason), (r) => { applyDetail(r); setMessage("출력용 확정되었습니다(IITP 공식 확인 아님)"); })}>출력용 확정</button>
              </div>
            )}
            {!locked && !canApprove && <p style={{ fontSize: 12.5, color: "var(--ink-muted)" }}>출력용 확정은 승인권자·관리자만 할 수 있습니다.</p>}
            {locked && canApprove && (
              <button className="tbtn" disabled={busy !== null} onClick={() => run("reopen", () => reopenReport(report.id), applyDetail)}>확정 해제</button>
            )}
          </div>
        </div>
      </div>
    </AppShell>
  );
}
