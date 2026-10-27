"use client";

import { useState } from "react";
import { getDocumentFullText, type RelatedDocument } from "@/lib/api";
import OriginalLink from "@/components/OriginalLink";

export type InsertSource = { doc: RelatedDocument; excerpt?: string; location?: string };

/** 집필 작업실 왼쪽 '원문·근거 작업대' — 원문을 확인하면서 제목·기관·발표일 인용이나 직접 고른 발췌문을 커서 위치에 넣는다.
 *  원문을 가져왔다고 해서 사실관계가 검증된 것으로 처리하지 않는다(각주는 항상 '근거 미검증'으로 시작). */
export default function SourceBench({ docs, canEdit, onInsert }: { docs: RelatedDocument[]; canEdit: boolean; onInsert: (text: string, src: InsertSource) => Promise<void> }) {
  const [open, setOpen] = useState<string | null>(null);
  const [paras, setParas] = useState<Record<string, string[]>>({});
  const [msg, setMsg] = useState<string | null>(null);

  const date = (iso: string | null) => (iso ? iso.slice(0, 10).replace(/-/g, ".") + "." : "발표일 미상");

  async function citation(d: RelatedDocument) {
    setMsg(null);
    await onInsert(`${d.org ? `${d.org}, ` : ""}「${d.title}」(${date(d.published_at)})`, { doc: d });
    setMsg("제목·기관·발표일 인용을 커서가 있는 문단 뒤에 넣었습니다(근거 미검증 각주 연결).");
  }

  async function toggle(d: RelatedDocument) {
    if (open === d.document_id) { setOpen(null); return; }
    setOpen(d.document_id);
    if (!paras[d.document_id]) {
      try {
        const ft = await getDocumentFullText(d.document_id);
        const list = (ft.full_text ?? "").split(/\n\s*\n/).map((p) => p.replace(/\s+/g, " ").trim()).filter((p) => p.length >= 40).slice(0, 60);
        setParas((prev) => ({ ...prev, [d.document_id]: list }));
      } catch {
        setParas((prev) => ({ ...prev, [d.document_id]: [] }));
      }
    }
  }

  async function excerpt(d: RelatedDocument, text: string, idx: number) {
    setMsg(null);
    await onInsert(text.length > 400 ? text.slice(0, 400) + "…" : text, { doc: d, excerpt: text.slice(0, 1500), location: `${idx + 1}번째 문단` });
    setMsg("선택한 발췌문을 넣었습니다 — 문장은 원문 그대로이므로 요약·해석은 연구원이 직접 쓰고 근거를 확인하세요(미검증 각주 연결).");
  }

  return (
    <div data-testid="source-bench" style={{ fontSize: 12.5 }}>
      <h2 style={{ fontSize: 13, margin: "12px 0 8px" }}>관련 원문·근거 작업대</h2>
      {docs.length === 0 && <p style={{ color: "var(--ink-muted)" }}>연결된 근거 원문이 없습니다.</p>}
      {msg && <p role="status" style={{ color: "var(--ok)" }}>{msg}</p>}
      {docs.map((d) => (
        <div key={d.document_id} data-testid="bench-doc" style={{ borderTop: "1px solid var(--border)", padding: "6px 0" }}>
          <OriginalLink url={d.origin_url} state={d.link_state} blocked={d.link_blocked} note={d.link_note} isPdf={d.is_pdf} testId="bench-link">{d.title.slice(0, 70)}</OriginalLink>
          <div style={{ color: "var(--ink-muted)" }}>{d.org ?? ""} · {date(d.published_at)}</div>
          <div style={{ display: "flex", gap: 4, flexWrap: "wrap", marginTop: 4 }}>
            <button className="tbtn" disabled={!canEdit} data-testid="bench-cite" onClick={() => citation(d)}>인용 넣기</button>
            <button className="tbtn" data-testid="bench-excerpt-toggle" onClick={() => toggle(d)}>{open === d.document_id ? "발췌문 닫기" : "발췌문 고르기"}</button>
          </div>
          {open === d.document_id && (
            <div data-testid="bench-paragraphs" style={{ maxHeight: 220, overflow: "auto", marginTop: 6, border: "1px solid var(--border)", borderRadius: 8, padding: 6 }}>
              {!paras[d.document_id] && <p>원문을 불러오는 중...</p>}
              {paras[d.document_id]?.length === 0 && <p style={{ color: "var(--ink-muted)" }}>확보된 원문 전문이 없습니다.</p>}
              {paras[d.document_id]?.map((p, i) => (
                <div key={i} style={{ padding: "4px 0", borderTop: i ? "1px dashed var(--border)" : undefined }}>
                  <span style={{ color: "var(--ink-muted)" }}>{i + 1}.</span> {p.slice(0, 220)}{p.length > 220 ? "…" : ""}
                  <button className="tbtn" style={{ marginLeft: 6 }} disabled={!canEdit} data-testid="bench-use-excerpt" onClick={() => excerpt(d, p, i)}>이 발췌문 사용</button>
                </div>
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
