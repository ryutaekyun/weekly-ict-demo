"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import AppShell from "@/components/AppShell";
import { listReports, type ReportListItem } from "@/lib/api";
import {
  createCardNews, getCnReportSentences, listCardNews, listCnTemplates,
  type CardNewsListItem, type CnSentence, type CnTemplateInfo,
} from "@/lib/cardNewsApi";
import { fmtDate } from "@/lib/labels";

const STATUS: Record<string, string> = { draft: "작성 중", review_requested: "검토 요청됨", changes_requested: "수정 요청됨", approved: "내부 확정" };
const MODES = [
  { key: "report", label: "기존 보고서에서 만들기" },
  { key: "summary", label: "보고서 요약본에서 만들기" },
  { key: "manual", label: "새로 직접 작성" },
] as const;
const inp: React.CSSProperties = { padding: 8, borderRadius: 8, border: "1px solid var(--border)", fontSize: 13, minWidth: 0 };

export default function CardNewsListPage() {
  const router = useRouter();
  const [items, setItems] = useState<CardNewsListItem[]>([]);
  const [templates, setTemplates] = useState<CnTemplateInfo[]>([]);
  const [reports, setReports] = useState<ReportListItem[]>([]);
  const [mode, setMode] = useState<"report" | "summary" | "manual">("manual");
  const [reportId, setReportId] = useState("");
  const [sentences, setSentences] = useState<CnSentence[]>([]);
  const [picked, setPicked] = useState<Set<number>>(new Set());
  const [templateKey, setTemplateKey] = useState("A");
  const [title, setTitle] = useState("");
  const [bodyCount, setBodyCount] = useState(3);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    listCardNews().then(setItems).catch(() => {});
    listCnTemplates().then(setTemplates).catch(() => {});
    listReports().then(setReports).catch(() => {});
  }, []);

  const candidates = useMemo(
    () => reports.filter((r) => (mode === "summary" ? r.report_type === "summary" : r.report_type !== "summary")),
    [reports, mode],
  );

  useEffect(() => {
    setSentences([]); setPicked(new Set());
    if (mode === "manual" || !reportId) return;
    getCnReportSentences(reportId).then((r) => setSentences(r.sentences)).catch((e) => setError(e.message));
  }, [mode, reportId]);

  function toggle(i: number) {
    const next = new Set(picked);
    if (next.has(i)) next.delete(i); else next.add(i);
    setPicked(next);
  }

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!title.trim()) { setError("카드뉴스 제목을 입력하세요"); return; }
    if (mode !== "manual" && !reportId) { setError("보고서를 선택하세요"); return; }
    setCreating(true); setError(null);
    try {
      const created = await createCardNews({
        title: title.trim(), template_key: templateKey, source_type: mode, body_count: bodyCount,
        source_report_id: mode === "manual" ? undefined : reportId,
        selections: [...picked].sort((a, b) => a - b).map((i) => ({ manuscript_id: sentences[i].manuscript_id, sentence: sentences[i].sentence })),
      });
      router.push(`/card-news/${created.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "생성 실패");
      setCreating(false);
    }
  }

  return (
    <AppShell>
      <h1 style={{ fontSize: 20, fontWeight: 700, marginBottom: 4 }}>카드뉴스 제작</h1>
      <p style={{ color: "var(--ink-muted)", fontSize: 13, marginTop: 0 }}>
        보고서·요약본의 핵심 문장을 골라 카드뉴스를 만들고, 웹에서 고친 뒤 <b>편집 가능한 PPTX</b>와 <b>고화질 PNG</b>로 출력합니다.
        기본 규격 7 × 15.62cm는 작업용 값이며 IITP 공식 규격이 아닙니다. 출력물은 내부 검토용이며 AI가 쓴 글이 아닙니다.
      </p>

      <form className="panel" onSubmit={handleCreate} style={{ marginBottom: 16 }}>
        <h2 style={{ fontSize: 14, margin: "0 0 10px" }}>새 카드뉴스 만들기</h2>
        <div role="radiogroup" aria-label="생성 방식" style={{ display: "flex", gap: 14, flexWrap: "wrap", marginBottom: 10 }}>
          {MODES.map((m) => (
            <label key={m.key} style={{ fontSize: 13 }}>
              <input type="radio" name="mode" checked={mode === m.key} onChange={() => { setMode(m.key); setReportId(""); }} /> {m.label}
            </label>
          ))}
        </div>

        {mode !== "manual" && (
          <div style={{ marginBottom: 10 }}>
            <select aria-label="원본 보고서" value={reportId} onChange={(e) => setReportId(e.target.value)} style={{ ...inp, width: "100%" }}>
              <option value="">{mode === "summary" ? "요약본 선택" : "보고서 선택"}</option>
              {candidates.map((r) => <option key={r.id} value={r.id}>{r.title}</option>)}
            </select>
            {reportId && (
              <div style={{ maxHeight: 220, overflow: "auto", marginTop: 8, border: "1px solid var(--border)", borderRadius: 8 }}>
                {sentences.length === 0 && <div style={{ padding: 10, fontSize: 12.5, color: "var(--ink-muted)" }}>선택할 수 있는 문장이 없습니다(보고서에 원고가 배치되어 있어야 합니다)</div>}
                {sentences.map((s, i) => (
                  <label key={i} style={{ display: "flex", gap: 8, padding: "6px 10px", borderTop: i ? "1px solid var(--border)" : undefined, fontSize: 12.5, alignItems: "flex-start" }}>
                    <input type="checkbox" checked={picked.has(i)} onChange={() => toggle(i)} aria-label={`문장 선택: ${s.sentence.slice(0, 20)}`} />
                    <span style={{ flex: 1 }}>
                      {s.sentence}
                      <span style={{ display: "block", color: "var(--ink-muted)", fontSize: 11.5 }}>
                        {s.manuscript_title} · {s.footnotes.length ? `원문 각주 ${s.footnotes.length}건(${s.footnotes.every((f) => f.status === "matched") ? "원고에서 검증됨" : "미검증 포함"})` : "연결된 각주 없음"}
                      </span>
                    </span>
                  </label>
                ))}
              </div>
            )}
            <p style={{ fontSize: 11.5, color: "var(--ink-muted)", margin: "6px 0 0" }}>
              선택한 {picked.size}개 문장이 카드에 순서대로 들어갑니다. 문장을 새로 쓰거나 요약하지 않으며, 원고 각주가 검증되었어도 카드에서는 연구원이 근거를 다시 확인해야 검증 완료가 됩니다.
            </p>
          </div>
        )}

        <div role="radiogroup" aria-label="디자인 템플릿" style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(200px,1fr))", gap: 8, marginBottom: 10 }}>
          {templates.map((t) => (
            <label key={t.key} style={{ border: `2px solid ${templateKey === t.key ? "var(--navy)" : "var(--border)"}`, borderRadius: 10, padding: 10, fontSize: 12.5, cursor: "pointer" }}>
              <input type="radio" name="template" checked={templateKey === t.key} onChange={() => setTemplateKey(t.key)} /> <b>{t.name}</b>
              <div style={{ color: "var(--ink-muted)", marginTop: 4 }}>{t.purpose}</div>
            </label>
          ))}
        </div>

        <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
          <input aria-label="카드뉴스 제목" placeholder="카드뉴스 제목" value={title} onChange={(e) => setTitle(e.target.value)} style={{ ...inp, flex: 1, minWidth: 240 }} />
          <label style={{ fontSize: 13 }}>본문 카드 수 <input aria-label="본문 카드 수" type="number" min={1} max={8} value={bodyCount} onChange={(e) => setBodyCount(Number(e.target.value))} style={{ ...inp, width: 64 }} /></label>
          <button className="tbtn primary" type="submit" disabled={creating}>{creating ? "생성 중..." : "카드뉴스 만들기"}</button>
        </div>
        {error && <p role="alert" style={{ color: "#b42318", fontSize: 12.5, marginBottom: 0 }}>{error}</p>}
      </form>

      <div className="panel" style={{ padding: 0, overflow: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
          <thead>
            <tr style={{ textAlign: "left", background: "var(--panel-2)" }}>
              <th style={{ padding: "9px 12px" }}>제목</th><th style={{ padding: "9px 12px" }}>템플릿</th>
              <th style={{ padding: "9px 12px" }}>상태</th><th style={{ padding: "9px 12px" }}>수정일</th>
            </tr>
          </thead>
          <tbody>
            {items.map((c) => (
              <tr key={c.id} style={{ borderTop: "1px solid var(--border)" }}>
                <td style={{ padding: "9px 12px" }}>
                  <Link href={`/card-news/${c.id}`}>{c.title}</Link>
                  {c.is_pilot && <span className="pill hold" style={{ marginLeft: 6 }}>시범</span>}
                  {c.is_synthetic && <span className="pill review" style={{ marginLeft: 6 }}>합성</span>}
                </td>
                <td style={{ padding: "9px 12px" }}>{c.template_key}형</td>
                <td style={{ padding: "9px 12px" }}>{STATUS[c.status] ?? c.status}</td>
                <td style={{ padding: "9px 12px" }}>{fmtDate(c.updated_at)}</td>
              </tr>
            ))}
            {items.length === 0 && <tr><td colSpan={4} style={{ padding: 20, textAlign: "center", color: "var(--ink-muted)" }}>만든 카드뉴스가 없습니다</td></tr>}
          </tbody>
        </table>
      </div>
    </AppShell>
  );
}
