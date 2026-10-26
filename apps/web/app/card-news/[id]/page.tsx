"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import AppShell from "@/components/AppShell";
import CardPreview from "@/components/CardPreview";
import { getCurrentUser, listUsers, UnauthorizedError, type CurrentUser, type UserSummary } from "@/lib/api";
import {
  addCnCard, addCnEvidence, addCnReview, approveCn, createCnExport, deleteCnCard, deleteCnEvidence, duplicateCn, duplicateCnCard,
  fetchCnBlob, getCardNews, getCnScenes, listCnExports, listCnReviews, listCnTemplates, listCnVersions, patchCardNews, patchCnCard,
  patchCnElement, reopenCn, reorderCnCards, requestCnChanges, requestCnReview, resolveCnReview, restoreCnVersion, saveCnMilestone,
  setCnIitp, verifyCnEvidence,
  type CardNewsDetail, type CnElement, type CnExport, type CnReview, type CnScene, type CnTemplateInfo, type CnVersion,
} from "@/lib/cardNewsApi";
import { fmtDate } from "@/lib/labels";

const STATUS: Record<string, string> = { draft: "작성 중", review_requested: "검토 요청됨", changes_requested: "수정 요청됨", approved: "내부 확정" };
const KIND: Record<string, string> = { cover: "표지", body: "본문", closing: "마무리" };
const EV_LABEL: Record<string, { text: string; cls: string }> = {
  none: { text: "근거 없음", cls: "hold" }, not_verified: { text: "검증 필요", cls: "review" },
  verified: { text: "검증 완료", cls: "rec" }, stale: { text: "수정됨·재검증 필요", cls: "hold" },
};
const PALETTE: [string, string][] = [["1B2A4A", "네이비"], ["FFFFFF", "화이트"], ["6E7685", "그레이"], ["2F7D62", "그린"], ["000000", "검정"]];
const inp: React.CSSProperties = { padding: 7, borderRadius: 8, border: "1px solid var(--border)", fontSize: 13, minWidth: 0, width: "100%" };
type Tab = "edit" | "evidence" | "review" | "output" | "versions";

function errMessage(err: unknown): string {
  return err instanceof Error ? err.message : "요청 실패";
}

export default function CardNewsEditorPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const id = params.id;
  const [me, setMe] = useState<CurrentUser | null>(null);
  const [cn, setCn] = useState<CardNewsDetail | null>(null);
  const [scenes, setScenes] = useState<CnScene[]>([]);
  const [templates, setTemplates] = useState<CnTemplateInfo[]>([]);
  const [activeIdx, setActiveIdx] = useState(0);
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("edit");
  const [saveStatus, setSaveStatus] = useState<"idle" | "saving" | "saved" | "conflict" | "error">("idle");
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [reviewers, setReviewers] = useState<UserSummary[]>([]);
  const [reviews, setReviews] = useState<CnReview[]>([]);
  const [versions, setVersions] = useState<CnVersion[]>([]);
  const [exportsList, setExportsList] = useState<CnExport[]>([]);
  const [pngUrls, setPngUrls] = useState<string[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [reviewerChoice, setReviewerChoice] = useState("");
  const [changesText, setChangesText] = useState("");
  const [commentText, setCommentText] = useState("");
  const [exceptionReason, setExceptionReason] = useState("");
  const [milestoneNote, setMilestoneNote] = useState("");
  const [shortPx, setShortPx] = useState(1000);
  const [evForm, setEvForm] = useState<Record<string, { url: string; org: string; excerpt: string }>>({});

  const lockRef = useRef(0);
  const queueRef = useRef<Promise<void>>(Promise.resolve());
  const timersRef = useRef<Record<string, ReturnType<typeof setTimeout>>>({});
  const draftsRef = useRef<Record<string, string>>({});
  const cnRef = useRef<CardNewsDetail | null>(null);
  const pngRef = useRef<string[]>([]);
  draftsRef.current = drafts;
  cnRef.current = cn;

  const fail = useCallback((err: unknown) => {
    if (err instanceof UnauthorizedError) { router.push("/login"); return; }
    const msg = errMessage(err);
    if (msg.includes("다른 사용자가")) setSaveStatus("conflict"); else setSaveStatus("error");
    setMessage(null);
    setError(msg);
  }, [router]);

  const refreshScenes = useCallback(() => {
    getCnScenes(id).then((r) => setScenes(r.scenes)).catch(() => {});
  }, [id]);

  const apply = useCallback((d: CardNewsDetail) => {
    cnRef.current = d;
    setCn(d);
    lockRef.current = d.lock_version;
    setActiveIdx((i) => Math.min(i, d.cards.length - 1));
    refreshScenes();
  }, [refreshScenes]);

  /** 저장 요청을 한 줄로 세워 순서대로 보낸다 — 앞선 요청이 끝난 뒤 갱신된 lock_version으로 다음 요청을 보내 스스로 충돌을 만들지 않는다. */
  const run = useCallback((fn: (lock: number) => Promise<CardNewsDetail>, okMessage?: string) => {
    queueRef.current = queueRef.current.then(async () => {
      setSaveStatus("saving"); setError(null);
      try {
        apply(await fn(lockRef.current));
        setSaveStatus("saved");
        if (okMessage) setMessage(okMessage);
      } catch (err) { fail(err); }
    });
    return queueRef.current;
  }, [apply, fail]);

  const loadSide = useCallback(() => {
    listCnReviews(id).then(setReviews).catch(() => {});
    listCnVersions(id).then(setVersions).catch(() => {});
    listCnExports(id).then(setExportsList).catch(() => {});
  }, [id]);

  const load = useCallback(() => {
    getCardNews(id).then((d) => { apply(d); setSaveStatus("idle"); }).catch(fail);
    loadSide();
  }, [id, apply, fail, loadSide]);

  useEffect(() => {
    getCurrentUser().then(setMe).catch(() => {});
    listUsers().then(setReviewers).catch(() => {});
    listCnTemplates().then(setTemplates).catch(() => {});
    load();
    const timers = timersRef.current;
    const pngs = pngRef;
    return () => { Object.values(timers).forEach(clearTimeout); pngs.current.forEach((u) => URL.revokeObjectURL(u)); };
  }, [load]);

  if (!cn) return <AppShell>{error ? <p role="alert" style={{ color: "#b42318" }}>{error}</p> : <p>불러오는 중...</p>}</AppShell>;

  const privileged = me?.role === "admin" || me?.role === "approver" || me?.role === "reviewer";
  const canApprove = me?.role === "admin" || me?.role === "approver";
  const isOwner = me?.id === cn.created_by_user_id;
  const locked = cn.status === "approved";
  const canEdit = !locked && (isOwner || privileged);
  const card = cn.cards[activeIdx];
  const scene = scenes.find((s) => s.card_id === card?.id) ?? scenes[activeIdx];

  // ---- 요소 텍스트 편집: 입력 → 0.7초 뒤 자동 저장, 포커스를 잃으면 즉시 저장 ----
  const dKey = (cardId: string, key: string) => `${cardId}:${key}`;
  function flush(cardId: string, key: string) {
    const k = dKey(cardId, key);
    clearTimeout(timersRef.current[k]);
    const value = draftsRef.current[k];
    if (value === undefined) return;
    const current = cnRef.current?.cards.find((c) => c.id === cardId)?.elements.find((e) => e.key === key);
    if (current && current.text === value) { setDrafts((d) => { const n = { ...d }; delete n[k]; return n; }); return; }
    run((lock) => patchCnElement(id, cardId, key, { lock_version: lock, text: value })).then(() => {
      setDrafts((d) => { if (d[k] !== value) return d; const n = { ...d }; delete n[k]; return n; });
    });
  }
  function onType(cardId: string, key: string, value: string) {
    const k = dKey(cardId, key);
    setDrafts((d) => ({ ...d, [k]: value }));
    clearTimeout(timersRef.current[k]);
    timersRef.current[k] = setTimeout(() => flush(cardId, key), 700);
  }
  const textOf = (c: string, el: CnElement) => drafts[dKey(c, el.key)] ?? el.text;
  function flushAll() {
    Object.keys(draftsRef.current).forEach((k) => { const [c, key] = k.split(":"); flush(c, key); });
  }
  const saveStyle = (el: CnElement, patch: Record<string, unknown>) =>
    run((lock) => patchCnElement(id, card.id, el.key, { lock_version: lock, style: { ...el.style, ...patch } }));

  // ---- 출력 ----
  async function download(path: string, fileName: string) {
    const blob = await fetchCnBlob(path);
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = fileName;
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 5000);
  }
  async function exportFile(fmt: "pptx" | "png") {
    flushAll();
    await queueRef.current;
    setBusy(`export-${fmt}`); setError(null); setMessage(null);
    try {
      const exp = await createCnExport(id, fmt, shortPx);
      setExportsList(await listCnExports(id));
      if (exp.status !== "success") throw new Error(`${fmt.toUpperCase()} 생성 실패: ${exp.error_message ?? "알 수 없는 오류"}`);
      await download(`/card-news/${id}/exports/${exp.id}/download`, exp.file_name ?? `cardnews.${fmt === "png" ? "zip" : fmt}`);
      setMessage(fmt === "pptx" ? `PPTX를 생성하고 내려받았습니다 (${exp.card_count}장)` : `PNG ${exp.card_count}장(${exp.png_width_px}×${exp.png_height_px}px)을 ZIP으로 내려받았습니다`);
      if (fmt === "png") await showPngs(exp);
    } catch (err) { fail(err); } finally { setBusy(null); }
  }
  async function showPngs(exp: CnExport) {
    pngRef.current.forEach((u) => URL.revokeObjectURL(u));
    const urls: string[] = [];
    for (let i = 1; i <= (exp.card_count ?? 0); i++) {
      urls.push(URL.createObjectURL(await fetchCnBlob(`/card-news/${id}/exports/${exp.id}/cards/${i}.png`)));
    }
    pngRef.current = urls;
    setPngUrls(urls);
  }

  // ---- 카드 조작 ----
  const moveCard = (delta: number) => {
    const ids = cn.cards.map((c) => c.id);
    const t = activeIdx + delta;
    if (t < 0 || t >= ids.length) return;
    [ids[activeIdx], ids[t]] = [ids[t], ids[activeIdx]];
    run((lock) => reorderCnCards(id, ids, lock)).then(() => setActiveIdx(t));
  };

  const issuesForCard = cn.preflight.filter((i) => i.card_index === activeIdx + 1);
  const blockingText = cn.blocking.length;
  const chartEl = card?.elements.find((e) => e.type === "chart");

  function ChartEditor({ el }: { el: CnElement }) {
    const data = el.data ?? { title: "", unit: "", base_year: "", comparison: "", source: "", synthetic: false, series: [{ label: "", value: "" }, { label: "", value: "" }] };
    const series: { label: string; value: string | number }[] = data.series ?? [];
    const save = (next: Record<string, any>) => run((lock) => patchCnElement(id, card.id, el.key, { lock_version: lock, data: next }));
    return (
      <div style={{ display: "grid", gap: 6 }}>
        {(["title", "unit", "base_year", "comparison", "source"] as const).map((f) => (
          <input key={f} aria-label={`그래프 ${f}`} placeholder={{ title: "그래프 제목", unit: "단위(필수)", base_year: "기준연도(필수)", comparison: "비교대상", source: "출처(필수)" }[f]}
            defaultValue={data[f] ?? ""} disabled={!canEdit} onBlur={(e) => { if (e.target.value !== (data[f] ?? "")) save({ ...data, series, [f]: e.target.value }); }} style={inp} />
        ))}
        {series.map((s, i) => (
          <div key={i} style={{ display: "flex", gap: 6 }}>
            <input aria-label={`항목 ${i + 1} 이름`} placeholder="항목" defaultValue={s.label} disabled={!canEdit}
              onBlur={(e) => { const ns = series.map((x, j) => (j === i ? { ...x, label: e.target.value } : x)); save({ ...data, series: ns }); }} style={inp} />
            <input aria-label={`항목 ${i + 1} 값`} placeholder="값" defaultValue={s.value} disabled={!canEdit}
              onBlur={(e) => { const ns = series.map((x, j) => (j === i ? { ...x, value: e.target.value } : x)); save({ ...data, series: ns }); }} style={inp} />
          </div>
        ))}
        <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
          <button className="tbtn" disabled={!canEdit || series.length >= 6} onClick={() => save({ ...data, series: [...series, { label: "", value: "" }] })}>항목 추가</button>
          <label style={{ fontSize: 12 }}>
            <input type="checkbox" checked={!!data.synthetic} disabled={!canEdit} onChange={(e) => save({ ...data, series, synthetic: e.target.checked })} /> 합성 테스트 데이터(실제 통계 아님)
          </label>
        </div>
      </div>
    );
  }

  return (
    <AppShell>
      <div style={{ marginBottom: 8 }}><Link href="/card-news" style={{ fontSize: 13 }}>← 카드뉴스 목록으로</Link></div>
      <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", marginBottom: 8 }}>
        <input aria-label="카드뉴스 제목" key={cn.title} defaultValue={cn.title} disabled={!canEdit}
          onBlur={(e) => { const v = e.target.value.trim(); if (v && v !== cn.title) run((lock) => patchCardNews(id, { lock_version: lock, title: v })); }}
          style={{ ...inp, fontSize: 17, fontWeight: 700, flex: 1, minWidth: 220 }} />
        <select aria-label="디자인 템플릿" value={cn.template_key} disabled={!canEdit}
          onChange={(e) => { const v = e.target.value; /* 비동기 콜백에서 e를 읽으면 제어 select가 이미 원래 값으로 돌아가 있다 */ run((lock) => patchCardNews(id, { lock_version: lock, template_key: v }), "템플릿을 바꿨습니다 — 같은 항목의 내용은 유지되고 핵심 내용은 순서대로 옮겨졌습니다"); }}
          style={{ ...inp, width: "auto" }}>
          {templates.map((t) => <option key={t.key} value={t.key}>{t.name}</option>)}
        </select>
        <span className={`pill ${locked ? "rec" : "review"}`}>{STATUS[cn.status] ?? cn.status}</span>
        <span className="pill hold">{cn.iitp_confirmed ? "IITP 확인 완료" : "IITP 공식 확인 전"}</span>
        {cn.is_pilot && <span className="pill hold">시범</span>}
        {cn.is_synthetic && <span className="pill review">합성 데이터</span>}
        <span style={{ fontSize: 12.5 }}>저장 상태: {{ idle: "대기", saving: "저장 중...", saved: "저장 완료", conflict: "충돌 발생", error: "저장 실패" }[saveStatus]}</span>
        <button className="tbtn" onClick={() => { flushAll(); }} disabled={!canEdit}>저장</button>
      </div>
      {saveStatus === "conflict" && (
        <div role="alert" className="panel" style={{ background: "#FFF4D6", marginBottom: 8, fontSize: 13 }}>
          다른 사용자가 먼저 수정했습니다. 내 수정은 저장되지 않았습니다. <button className="tbtn" onClick={() => { setDrafts({}); load(); }}>최신 내용 다시 불러오기</button>
        </div>
      )}
      {error && saveStatus !== "conflict" && <p role="alert" style={{ color: "#b42318", fontSize: 13, margin: "4px 0" }}>{error}</p>}
      {message && <p role="status" style={{ color: "var(--ok)", fontSize: 13, margin: "4px 0" }}>{message}</p>}
      {(cn.needs_review || cn.source_changed) && (
        <p style={{ fontSize: 12.5, color: "#9a4b00", margin: "4px 0" }}>
          {cn.needs_review ? "원본 변경·재검토 필요: 연결된 보고서/원고의 문장이 바뀌었습니다(카드 내용은 자동으로 바뀌지 않았습니다)." : "연결된 원고의 버전이 카드뉴스 생성 이후 바뀌었습니다."}
        </p>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "150px minmax(300px, 1fr) minmax(340px, 400px)", gap: 12, alignItems: "start" }}>
        {/* 왼쪽 — 카드 목록 */}
        <div className="panel" style={{ padding: 8 }}>
          <div style={{ fontSize: 12, fontWeight: 700, marginBottom: 6 }}>카드 목록 ({cn.cards.length}장)</div>
          <div style={{ display: "grid", gap: 8, maxHeight: 640, overflow: "auto" }}>
            {cn.cards.map((c, i) => {
              const sc = scenes.find((s) => s.card_id === c.id);
              return (
                <button key={c.id} aria-label={`카드 ${i + 1} (${KIND[c.kind]})`} onClick={() => { setActiveIdx(i); setSelectedKey(null); }}
                  style={{ border: `2px solid ${i === activeIdx ? "var(--navy)" : "transparent"}`, borderRadius: 8, padding: 3, background: "transparent", cursor: "pointer", textAlign: "center" }}>
                  {sc ? <CardPreview scene={sc} widthPx={92} label={`카드 ${i + 1} 썸네일`} /> : <div style={{ width: 92, height: 205, background: "#eee" }} />}
                  <div style={{ fontSize: 11, marginTop: 2 }}>{i + 1}. {KIND[c.kind]}</div>
                </button>
              );
            })}
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 4, marginTop: 8 }}>
            <button className="tbtn" disabled={!canEdit} onClick={() => run((lock) => addCnCard(id, { lock_version: lock, kind: "body", after_card_id: card.id }), "카드를 추가했습니다")}>추가</button>
            <button className="tbtn" disabled={!canEdit} onClick={() => run((lock) => duplicateCnCard(id, card.id, lock), "카드를 복제했습니다")}>복제</button>
            <button className="tbtn" disabled={!canEdit || cn.cards.length <= 1} onClick={() => run((lock) => deleteCnCard(id, card.id, lock), "카드를 삭제했습니다(버전에서 복원 가능)")}>삭제</button>
            <button className="tbtn" aria-label="카드 위로" disabled={!canEdit || activeIdx === 0} onClick={() => moveCard(-1)}>↑</button>
            <button className="tbtn" aria-label="카드 아래로" disabled={!canEdit || activeIdx === cn.cards.length - 1} onClick={() => moveCard(1)}>↓</button>
          </div>
        </div>

        {/* 가운데 — 카드 미리보기 */}
        <div className="panel" style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 8 }}>
          <div style={{ fontSize: 12.5, color: "var(--ink-muted)", alignSelf: "stretch" }}>
            {activeIdx + 1}번 카드 · {KIND[card.kind]} · {cn.width_cm}×{cn.height_cm}cm — 글자를 누르면 오른쪽에서 해당 항목을 고칩니다
          </div>
          {scene ? <CardPreview scene={scene} widthPx={300} selectedKey={selectedKey} onSelect={(k) => { setSelectedKey(k); setTab("edit"); }} label={`카드 ${activeIdx + 1} 미리보기`} /> : <p>미리보기를 불러오는 중...</p>}
          {scene?.notes.map((n, i) => <div key={i} style={{ fontSize: 12, color: "#7A5B00", background: "#FFF4D6", padding: "4px 8px", borderRadius: 6 }}>{n}</div>)}
          {issuesForCard.filter((i) => i.level !== "info").slice(0, 4).map((i, idx) => (
            <div key={idx} style={{ fontSize: 12, alignSelf: "stretch", color: i.level === "error" ? "#b42318" : "#9a4b00" }}>⚠ {i.message}</div>
          ))}
          <div style={{ fontSize: 11.5, color: "var(--ink-muted)", alignSelf: "stretch" }}>{cn.size_note}</div>
        </div>

        {/* 오른쪽 — 속성·근거·검토·출력 */}
        <div className="panel">
          <div style={{ display: "flex", gap: 4, flexWrap: "wrap", marginBottom: 8 }}>
            {([["edit", "내용·디자인"], ["evidence", "원문 근거"], ["review", "검토·승인"], ["output", "점검·출력"], ["versions", "버전"]] as [Tab, string][]).map(([t, l]) => (
              <button key={t} className="tbtn" aria-pressed={tab === t} onClick={() => setTab(t)}
                style={tab === t ? { background: "var(--navy)", color: "#fff" } : undefined}>{l}{t === "output" && blockingText ? ` (${blockingText})` : ""}</button>
            ))}
          </div>

          {tab === "edit" && (
            <div style={{ display: "grid", gap: 10 }}>
              {locked && <p style={{ fontSize: 12.5, color: "#9a4b00", margin: 0 }}>내부 확정된 카드뉴스입니다. 승인권자의 확정 해제 또는 &ldquo;새 수정 버전&rdquo;으로만 수정할 수 있습니다.</p>}
              <div style={{ display: "flex", gap: 6, alignItems: "center", fontSize: 12.5 }}>
                카드 배경색
                <select aria-label="카드 배경색" disabled={!canEdit} value={card.bg_color ?? ""}
                  onChange={(e) => { const v = e.target.value; run((lock) => patchCnCard(id, card.id, v ? { lock_version: lock, bg_color: v } : { lock_version: lock, clear_bg: true })); }} style={{ ...inp, width: "auto" }}>
                  <option value="">템플릿 기본</option>
                  {[["FFFFFF", "화이트"], ["F4F7FB", "연한 블루"], ["E6F4EE", "연한 그린"], ["FFF4D6", "연한 노랑"], ["1B2A4A", "네이비"]].map(([c, l]) => <option key={c} value={c}>{l}</option>)}
                </select>
              </div>
              {card.elements.filter((e) => !e.hidden || true).map((el) => {
                const value = textOf(card.id, el);
                const ev = EV_LABEL[el.evidence_state];
                return (
                  <div key={el.key} data-field={el.key} style={{ outline: selectedKey === el.key ? "2px solid #5CAD8E" : undefined, borderRadius: 8, padding: 4 }}
                    onClick={() => setSelectedKey(el.key)}>
                    <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12.5, fontWeight: 700 }}>
                      <span>{el.label}{el.required ? " *" : ""}</span>
                      {el.evidence_required && value.trim() && ev && <span className={`pill ${ev.cls}`}>{ev.text}</span>}
                      {el.source_stale && <span className="pill hold">원본 변경·재검토 필요</span>}
                      {el.type === "text" && <span style={{ marginLeft: "auto", fontWeight: 400, color: value.length > el.max_chars ? "#b42318" : "var(--ink-muted)" }}>{value.length}/{el.max_chars}</span>}
                    </div>
                    {el.type === "choice" && (
                      <select aria-label={el.label} value={el.text || "other"} disabled={!canEdit}
                        onChange={(e) => { const v = e.target.value; run((lock) => patchCnElement(id, card.id, el.key, { lock_version: lock, text: v })); }} style={inp}>
                        {Object.entries(el.options).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
                      </select>
                    )}
                    {el.type === "chart" && ChartEditor({ el })}
                    {el.type === "text" && (el.multiline ? (
                      <textarea aria-label={el.label} value={value} disabled={!canEdit} rows={3} onChange={(e) => onType(card.id, el.key, e.target.value)}
                        onBlur={() => flush(card.id, el.key)} style={{ ...inp, resize: "vertical" }} />
                    ) : (
                      <input aria-label={el.label} value={value} disabled={!canEdit} onChange={(e) => onType(card.id, el.key, e.target.value)}
                        onBlur={() => flush(card.id, el.key)} style={inp} />
                    ))}
                    {el.hint && <div style={{ fontSize: 11, color: "var(--ink-muted)" }}>{el.hint}</div>}
                    {el.type === "text" && (
                      <details style={{ fontSize: 12 }}>
                        <summary style={{ cursor: "pointer", color: "var(--ink-muted)" }}>서식 (크기·색·굵기·정렬)</summary>
                        <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center", marginTop: 4 }}>
                          <label>크기 <input aria-label={`${el.label} 글자 크기`} type="number" min={5} max={40} step={0.5} defaultValue={el.style.size ?? ""} disabled={!canEdit}
                            placeholder="기본" onBlur={(e) => { const v = e.target.value ? Number(e.target.value) : undefined; if (v !== el.style.size) saveStyle(el, { size: v }); }} style={{ ...inp, width: 64 }} /></label>
                          <select aria-label={`${el.label} 글자색`} value={el.style.color ?? ""} disabled={!canEdit} onChange={(e) => saveStyle(el, { color: e.target.value || undefined })} style={{ ...inp, width: "auto" }}>
                            <option value="">색 기본</option>{PALETTE.map(([c, l]) => <option key={c} value={c}>{l}</option>)}
                          </select>
                          <label><input type="checkbox" checked={!!el.style.bold} disabled={!canEdit} onChange={(e) => saveStyle(el, { bold: e.target.checked })} /> 굵게</label>
                          <select aria-label={`${el.label} 정렬`} value={el.style.align ?? ""} disabled={!canEdit} onChange={(e) => saveStyle(el, { align: e.target.value || undefined })} style={{ ...inp, width: "auto" }}>
                            <option value="">정렬 기본</option><option value="left">왼쪽</option><option value="center">가운데</option><option value="right">오른쪽</option>
                          </select>
                          <button className="tbtn" disabled={!canEdit} onClick={() => run((lock) => patchCnElement(id, card.id, el.key, { lock_version: lock, style: {} }))}>서식 초기화</button>
                        </div>
                      </details>
                    )}
                  </div>
                );
              })}
            </div>
          )}

          {tab === "evidence" && (
            <div style={{ display: "grid", gap: 10 }}>
              <p style={{ fontSize: 12, color: "var(--ink-muted)", margin: 0 }}>
                사실·수치·일정·정책명은 원문 근거와 연결합니다. 원문과 카드 내용을 직접 대조한 뒤에만 &ldquo;검증 완료&rdquo;로 표시하세요. 원고 각주가 검증되었어도 카드에서는 별도로 확인해야 하며, 검증 후 내용을 고치면 다시 재검증이 필요합니다.
              </p>
              {card.elements.filter((e) => e.evidence_required && (textOf(card.id, e).trim() || e.type === "chart")).map((el) => {
                const form = evForm[el.key] ?? { url: "", org: "", excerpt: "" };
                const setForm = (patch: Partial<typeof form>) => setEvForm({ ...evForm, [el.key]: { ...form, ...patch } });
                const ev = EV_LABEL[el.evidence_state];
                return (
                  <div key={el.key} className="panel" style={{ background: "var(--panel-2)", fontSize: 12.5 }}>
                    <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                      <b>{el.label}</b>{ev && <span className={`pill ${ev.cls}`}>{ev.text}</span>}
                    </div>
                    {el.text && <div style={{ color: "var(--ink-muted)", margin: "2px 0" }}>“{el.text.slice(0, 60)}”</div>}
                    {el.evidence_items.map((e) => (
                      <div key={e.id} style={{ borderTop: "1px solid var(--border)", padding: "6px 0" }}>
                        <div>{e.source_org ?? "출처"} · <a href={e.source_url} target="_blank" rel="noreferrer">{e.source_url}</a></div>
                        {e.excerpt && <div style={{ color: "var(--ink-muted)" }}>발췌: {e.excerpt}</div>}
                        {e.original_footnote_status && <div style={{ color: "var(--ink-muted)" }}>원고 각주 상태: {e.original_footnote_status === "matched" ? "검증됨" : "미검증"} (카드에서는 별도 확인 필요)</div>}
                        <div style={{ display: "flex", gap: 6, marginTop: 4, alignItems: "center" }}>
                          <span className={`pill ${EV_LABEL[e.verification_status].cls}`}>{EV_LABEL[e.verification_status].text}</span>
                          {e.verification_status !== "verified" && <button className="tbtn" disabled={locked} onClick={() => run(async () => { const d = await verifyCnEvidence(id, e.id, true); return d; }, "근거를 검증 완료로 표시했습니다")}>검증 완료로 표시</button>}
                          {e.verification_status === "verified" && <button className="tbtn" disabled={locked} onClick={() => run(() => verifyCnEvidence(id, e.id, false))}>검증 취소</button>}
                          <button className="tbtn" disabled={locked} onClick={() => run(() => deleteCnEvidence(id, e.id))}>삭제</button>
                        </div>
                      </div>
                    ))}
                    {el.evidence_items.length === 0 && <div style={{ color: "#9a4b00" }}>연결된 근거가 없습니다</div>}
                    {!locked && (
                      <div style={{ display: "grid", gap: 4, marginTop: 6 }}>
                        <input aria-label={`${el.label} 근거 URL`} placeholder="원문 URL(필수)" value={form.url} onChange={(e) => setForm({ url: e.target.value })} style={inp} />
                        <input aria-label={`${el.label} 근거 기관`} placeholder="발표 기관" value={form.org} onChange={(e) => setForm({ org: e.target.value })} style={inp} />
                        <textarea aria-label={`${el.label} 근거 발췌`} placeholder="근거 원문 발췌" value={form.excerpt} onChange={(e) => setForm({ excerpt: e.target.value })} style={{ ...inp, minHeight: 44 }} />
                        <button className="tbtn" disabled={!form.url.trim()} onClick={() => run(async () => {
                          const d = await addCnEvidence(id, card.id, { element_key: el.key, source_url: form.url, source_org: form.org || undefined, excerpt: form.excerpt || undefined });
                          setEvForm({ ...evForm, [el.key]: { url: "", org: "", excerpt: "" } });
                          return d;
                        }, "근거를 연결했습니다(아직 검증 전)")}>근거 연결</button>
                      </div>
                    )}
                  </div>
                );
              })}
              {card.elements.filter((e) => e.evidence_required).every((e) => !textOf(card.id, e).trim() && e.type !== "chart") && (
                <p style={{ fontSize: 12.5, color: "var(--ink-muted)" }}>이 카드에는 근거 연결 대상 내용이 아직 없습니다.</p>
              )}
            </div>
          )}

          {tab === "review" && (
            <div style={{ display: "grid", gap: 10, fontSize: 12.5 }}>
              <div>
                <b>검토 의견</b>
                {reviews.length === 0 && <div style={{ color: "var(--ink-muted)" }}>검토 의견이 없습니다</div>}
                {reviews.map((r) => (
                  <div key={r.id} style={{ borderTop: "1px solid var(--border)", padding: "6px 0" }}>
                    <div>{r.comment_text}</div>
                    <div style={{ color: "var(--ink-muted)" }}>{r.card_id ? `${cn.cards.findIndex((c) => c.id === r.card_id) + 1}번 카드` : "전체"} · {r.status === "open" ? "미해결" : "해결됨"}</div>
                    {r.status === "open" && <button className="tbtn" onClick={() => resolveCnReview(id, r.id).then(setReviews).catch(fail)}>해결 처리</button>}
                  </div>
                ))}
                <textarea aria-label="검토 의견 입력" placeholder="이 카드에 대한 의견" value={commentText} onChange={(e) => setCommentText(e.target.value)} style={{ ...inp, minHeight: 50, marginTop: 6 }} />
                <button className="tbtn" disabled={!commentText.trim()} onClick={() => addCnReview(id, { comment_text: commentText, card_id: card.id }).then((r) => { setReviews(r); setCommentText(""); }).catch(fail)}>의견 등록</button>
              </div>
              <hr style={{ width: "100%", border: 0, borderTop: "1px solid var(--border)" }} />
              <b>검토·승인 절차 (내부 확정 ≠ IITP 공식 확인)</b>
              {(cn.status === "draft" || cn.status === "changes_requested") && (isOwner || privileged) && (
                <div style={{ display: "grid", gap: 4 }}>
                  <select aria-label="검토자 선택" value={reviewerChoice} onChange={(e) => setReviewerChoice(e.target.value)} style={inp}>
                    <option value="">검토자 선택</option>
                    {reviewers.filter((u) => u.role !== "researcher").map((u) => <option key={u.id} value={u.id}>{u.display_name}({u.role})</option>)}
                  </select>
                  <button className="tbtn primary" onClick={() => { flushAll(); queueRef.current.then(() => requestCnReview(id, reviewerChoice || undefined)).then((d) => { apply(d); loadSide(); setMessage("검토를 요청했습니다"); }).catch(fail); }}>검토 요청</button>
                </div>
              )}
              {cn.status === "review_requested" && privileged && (
                <div style={{ display: "grid", gap: 4 }}>
                  <textarea aria-label="수정 요청 사유" placeholder="구체적인 수정 요청 사항" value={changesText} onChange={(e) => setChangesText(e.target.value)} style={{ ...inp, minHeight: 50 }} />
                  <button className="tbtn" disabled={!changesText.trim()} onClick={() => requestCnChanges(id, changesText).then((d) => { apply(d); loadSide(); setChangesText(""); setMessage("수정을 요청했습니다"); }).catch(fail)}>수정 요청 보내기</button>
                </div>
              )}
              {cn.status === "review_requested" && canApprove && (
                <div style={{ display: "grid", gap: 4 }}>
                  {cn.blocking.length > 0 && <div style={{ color: "#9a4b00" }}>확정을 막는 점검 항목 {cn.blocking.length}건 — 해결하거나 예외 사유를 남기세요.</div>}
                  <textarea aria-label="예외 승인 사유" placeholder="예외 승인 사유(필수 점검 미통과·미해결 의견이 있을 때)" value={exceptionReason} onChange={(e) => setExceptionReason(e.target.value)} style={{ ...inp, minHeight: 44 }} />
                  <button className="tbtn primary" onClick={() => approveCn(id, exceptionReason).then((d) => { apply(d); loadSide(); setMessage("내부 확정되었습니다(IITP 공식 확인 아님)"); }).catch(fail)}>내부 확정</button>
                </div>
              )}
              {cn.status === "approved" && (
                <div style={{ display: "grid", gap: 4 }}>
                  {cn.approve_exception_reason && <div>예외 사유: {cn.approve_exception_reason}</div>}
                  <button className="tbtn" onClick={() => duplicateCn(id).then((d) => router.push(`/card-news/${d.id}`)).catch(fail)}>새 수정 버전 만들기</button>
                  {canApprove && <button className="tbtn" onClick={() => reopenCn(id).then((d) => { apply(d); setMessage("확정을 해제했습니다"); }).catch(fail)}>확정 해제</button>}
                </div>
              )}
              {canApprove && (
                <label>
                  <input type="checkbox" checked={cn.iitp_confirmed} onChange={(e) => setCnIitp(id, e.target.checked).then(apply).catch(fail)} /> IITP 공식 확인 완료로 기록(내부 확정과 별개)
                </label>
              )}
            </div>
          )}

          {tab === "output" && (
            <div style={{ display: "grid", gap: 10, fontSize: 12.5 }}>
              <div>
                <b>발간 사전점검</b>
                {cn.preflight.length === 0 && <div style={{ color: "var(--ink-muted)" }}>점검 항목이 없습니다</div>}
                {cn.preflight.map((i, idx) => (
                  <div key={idx} style={{ borderTop: "1px solid var(--border)", padding: "4px 0" }}>
                    <span style={{ fontWeight: 700, color: i.level === "error" ? "#b42318" : i.level === "warn" ? "#9a4b00" : "#475467" }}>
                      [{i.level === "error" ? "필수" : i.level === "warn" ? "경고" : "안내"}]
                    </span> {i.message}
                  </div>
                ))}
              </div>
              <hr style={{ width: "100%", border: 0, borderTop: "1px solid var(--border)" }} />
              <b>출력 · 다운로드</b>
              <p style={{ margin: 0, color: "var(--ink-muted)" }}>
                누르는 순간의 카드 내용·템플릿 버전으로 고정해 실제 파일을 만듭니다. PPTX의 글자·도형·표·차트는 PowerPoint에서 직접 편집할 수 있고, PNG는 같은 PPTX를 렌더링한 결과입니다.
              </p>
              <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center" }}>
                <button className="tbtn primary" disabled={busy !== null} onClick={() => exportFile("pptx")}>{busy === "export-pptx" ? "PPTX 생성 중..." : "PPTX 다운로드"}</button>
                <button className="tbtn primary" disabled={busy !== null} onClick={() => exportFile("png")}>{busy === "export-png" ? "PNG 생성 중..." : "PNG(ZIP) 다운로드"}</button>
                <label>해상도(짧은 변) <select aria-label="PNG 해상도" value={shortPx} onChange={(e) => setShortPx(Number(e.target.value))} style={{ ...inp, width: "auto" }}>
                  {[1000, 1500, 2000].map((p) => <option key={p} value={p}>{p}px</option>)}
                </select></label>
              </div>
              {pngUrls.length > 0 && (
                <div>
                  <div style={{ fontWeight: 700, marginBottom: 4 }}>생성된 PNG 미리보기</div>
                  <div style={{ display: "flex", gap: 6, overflowX: "auto" }}>
                    {pngUrls.map((u, i) => <img key={u} src={u} alt={`PNG ${i + 1}번 카드`} style={{ height: 220, borderRadius: 4, border: "1px solid var(--border)" }} />)}
                  </div>
                </div>
              )}
              <b>출력 이력</b>
              {exportsList.length === 0 && <div style={{ color: "var(--ink-muted)" }}>아직 출력한 파일이 없습니다</div>}
              {exportsList.map((e) => (
                <div key={e.id} style={{ borderTop: "1px solid var(--border)", padding: "6px 0" }}>
                  <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
                    <b>{e.file_format.toUpperCase()}</b>
                    <span className={`pill ${e.status === "success" ? "rec" : e.status === "failed" ? "hold" : "review"}`}>{e.status === "success" ? "성공" : e.status === "failed" ? "실패" : "진행 중"}</span>
                    <span style={{ color: "var(--ink-muted)" }}>{fmtDate(e.created_at)}</span>
                    {e.status === "success" && <button className="tbtn" style={{ marginLeft: "auto" }} onClick={() => download(`/card-news/${id}/exports/${e.id}/download`, e.file_name ?? "cardnews").catch(fail)}>재다운로드</button>}
                  </div>
                  {e.status === "failed" && <div style={{ color: "#b42318" }}>{e.error_message}</div>}
                  {e.status === "success" && (
                    <div style={{ color: "var(--ink-muted)" }}>
                      {e.card_count}장{e.png_width_px ? ` · ${e.png_width_px}×${e.png_height_px}px` : ""} · 내용 v{e.content_version} · 템플릿 v{e.template_version} · {e.approval_state === "approved" ? "내부 확정본" : "초안"} · SHA-256 {e.file_sha256?.slice(0, 10)}…
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}

          {tab === "versions" && (
            <div style={{ display: "grid", gap: 8, fontSize: 12.5 }}>
              <div style={{ display: "flex", gap: 6 }}>
                <input aria-label="버전 메모" placeholder="예: 1차 초안 완료" value={milestoneNote} onChange={(e) => setMilestoneNote(e.target.value)} style={inp} />
                <button className="tbtn" onClick={() => { flushAll(); queueRef.current.then(() => saveCnMilestone(id, milestoneNote || undefined)).then((v) => { setVersions(v); setMilestoneNote(""); setMessage("주요 버전을 저장했습니다"); }).catch(fail); }}>주요 버전 저장</button>
              </div>
              {versions.map((v) => (
                <div key={v.id} style={{ borderTop: "1px solid var(--border)", padding: "6px 0", display: "flex", gap: 6, alignItems: "center" }}>
                  <span><b>v{v.version_no}</b> {v.is_milestone ? "★" : ""} {v.change_note ?? "자동 저장"} <span style={{ color: "var(--ink-muted)" }}>{fmtDate(v.created_at)}</span></span>
                  <button className="tbtn" style={{ marginLeft: "auto" }} disabled={!canEdit}
                    onClick={() => run((lock) => restoreCnVersion(id, v.id, lock), `v${v.version_no}로 복원했습니다(복원 전 상태도 버전으로 남았습니다)`).then(loadSide)}>복원</button>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </AppShell>
  );
}
