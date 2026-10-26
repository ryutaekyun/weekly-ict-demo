"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import AppShell from "@/components/AppShell";
import { downloadFile, pManuscript, pReply, uploadForm, type JManuscript } from "@/lib/journalApi";

const inp: React.CSSProperties = { padding: 8, borderRadius: 8, border: "1px solid var(--border)", fontSize: 13, minWidth: 0 };
const ITEM_LABEL: Record<string, string> = { pass: "통과", fail: "보완 필요", warn: "확인", info: "안내" };

export default function PortalManuscriptPage() {
  const { id } = useParams<{ id: string }>();
  const [ms, setMs] = useState<JManuscript | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [replies, setReplies] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [docType, setDocType] = useState("");

  const load = useCallback(() => { pManuscript(id).then(setMs).catch((e) => setError(e instanceof Error ? e.message : "불러오기 실패")); }, [id]);
  useEffect(() => { load(); }, [load]);

  async function run(fn: () => Promise<unknown>, ok: string) {
    setError(null); setMessage(null); setBusy(true);
    try { await fn(); setMessage(ok); load(); } catch (e) { setError(e instanceof Error ? e.message : "처리 실패"); } finally { setBusy(false); }
  }

  if (!ms) return <AppShell>{error ? <p role="alert" style={{ color: "#b42318" }}>{error}</p> : <p>불러오는 중...</p>}</AppShell>;
  const last = ms.versions[ms.versions.length - 1];
  const canReply = ms.status === "revision_requested" || ms.status === "format_fix_needed";

  return (
    <AppShell>
      <div style={{ marginBottom: 8 }}><Link href="/portal" style={{ fontSize: 13 }}>← 원고 집필 포털</Link></div>
      <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", marginBottom: 6 }}>
        <h1 style={{ fontSize: 19, fontWeight: 700, margin: 0 }}>{ms.title}</h1>
        <span className="pill review" data-testid="author-status">{ms.status_label}</span>
      </div>
      <div style={{ fontSize: 13, marginBottom: 8 }}>{ms.issue_label} · 제출 버전 {ms.version_count}건</div>
      {error && <p role="alert" style={{ color: "#b42318", fontSize: 13 }}>{error}</p>}
      {message && <p role="status" style={{ color: "var(--ok)", fontSize: 13 }}>{message}</p>}

      <section className="panel" style={{ marginBottom: 12 }}>
        <b>제출한 파일(버전)</b>
        {ms.versions.map((v) => (
          <div key={v.id} style={{ fontSize: 13, borderTop: "1px solid var(--border)", padding: "6px 0" }}>
            v{v.version_no} · {v.kind_label} · {v.file_name} · {Math.round(v.file_size / 1024)}KB · {v.uploaded_at.slice(0, 10)} · SHA-256 {v.sha256.slice(0, 10)}…
            <button className="tbtn" style={{ marginLeft: 6 }} onClick={() => downloadFile(`/journal/portal/author/manuscripts/${id}/versions/${v.id}/download`, v.file_name).catch((e) => setError(e.message))}>다운로드</button>
          </div>
        ))}
        {last?.format_check.items && (
          <div style={{ marginTop: 6 }}>
            <b style={{ fontSize: 13 }}>형식 점검 결과(최신)</b>
            {last.format_check.items.map((i) => <div key={i.key} style={{ fontSize: 12.5 }}>[{ITEM_LABEL[i.status]}] {i.label}: {i.detail}</div>)}
          </div>
        )}
      </section>

      <section className="panel" style={{ marginBottom: 12 }}>
        <b>검토 의견</b>
        {ms.comments.length === 0 && <p style={{ fontSize: 12.5, color: "var(--ink-muted)" }}>아직 받은 의견이 없습니다.</p>}
        {ms.comments.map((c) => (
          <div key={c.id} style={{ borderTop: "1px solid var(--border)", padding: "6px 0", fontSize: 13 }}>
            <span className={`pill ${c.status === "resolved" ? "rec" : c.status === "answered" ? "hold" : "review"}`}>{{ open: "답변 필요", answered: "답변함", resolved: "해결됨" }[c.status]}</span>{" "}
            [{{ doc: "문서 전체", paragraph: "문단", table: "표", figure: "그림" }[c.scope]}] {c.author_name}: {c.text}
            {c.anchor_text && <div style={{ fontSize: 12, color: "var(--ink-muted)" }}>대상: {c.anchor_text.slice(0, 80)}</div>}
            {c.author_reply && <div style={{ fontSize: 12.5, background: "var(--panel-2)", padding: 4, borderRadius: 6 }}>내 답변: {c.author_reply}</div>}
            {canReply && c.status !== "resolved" && (
              <div style={{ display: "flex", gap: 6, marginTop: 4 }}>
                <input aria-label={`답변: ${c.text.slice(0, 12)}`} placeholder="답변(수정한 내용 설명)" value={replies[c.id] ?? ""} onChange={(e) => setReplies({ ...replies, [c.id]: e.target.value })} style={{ ...inp, flex: 1 }} />
                <button className="tbtn" disabled={busy || !(replies[c.id] ?? "").trim()} onClick={() => run(() => pReply(id, c.id, replies[c.id]), "답변을 저장했습니다")}>답변 저장</button>
              </div>
            )}
          </div>
        ))}
      </section>

      {ms.status === "revision_requested" && (
        <form className="panel" style={{ marginBottom: 12, display: "grid", gap: 8 }}
          onSubmit={(e) => { e.preventDefault(); const f = (e.currentTarget.elements.namedItem("rev") as HTMLInputElement).files?.[0]; if (!f) { setError("수정본 파일을 선택하세요"); return; }
            const fd = new FormData(); fd.append("file", f); fd.append("note", (e.currentTarget.elements.namedItem("revnote") as HTMLInputElement).value);
            run(() => uploadForm(`/journal/portal/author/manuscripts/${id}/revision`, fd), "수정본을 제출했습니다(이전 제출본은 그대로 보관됩니다)"); }}>
          <b>수정본 재제출</b>
          <p style={{ fontSize: 12, color: "var(--ink-muted)", margin: 0 }}>검토 의견에 답변한 뒤 수정본을 올리세요. 이전 제출본과 수정본은 별도 버전으로 보관되고 차이가 편집 담당자에게 비교됩니다.</p>
          <input aria-label="수정본 파일" name="rev" type="file" accept=".docx,.pdf" />
          <input aria-label="수정 요약" name="revnote" placeholder="수정 내용 요약" style={inp} />
          <div><button className="tbtn primary" type="submit" disabled={busy}>수정본 제출</button></div>
        </form>
      )}

      <section className="panel">
        <b>제출서류·첨부</b>
        {ms.attachments.map((a) => <div key={a.id} style={{ fontSize: 13 }}>{a.doc_type}: {a.file_name} ({Math.round(a.file_size / 1024)}KB)</div>)}
        {ms.required_docs.length > 0 && <div style={{ fontSize: 12.5, color: "var(--ink-muted)" }}>필수 제출서류: {ms.required_docs.map((d) => `${d.label}(${d.key})`).join(", ")}</div>}
        <form style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 6 }}
          onSubmit={(e) => { e.preventDefault(); const f = (e.currentTarget.elements.namedItem("att") as HTMLInputElement).files?.[0]; if (!f || !docType.trim()) { setError("서류 종류와 파일을 선택하세요"); return; }
            const fd = new FormData(); fd.append("doc_type", docType.trim()); fd.append("file", f); run(() => uploadForm(`/journal/portal/author/manuscripts/${id}/attachments`, fd), "서류를 제출했습니다"); }}>
          <input aria-label="서류 종류" placeholder="서류 종류(키)" list="doc-types" value={docType} onChange={(e) => setDocType(e.target.value)} style={inp} />
          <datalist id="doc-types">{ms.required_docs.map((d) => <option key={d.key} value={d.key}>{d.label}</option>)}</datalist>
          <input aria-label="서류 파일" name="att" type="file" accept=".pdf,.docx,.png,.jpg,.jpeg,.xlsx,.txt" />
          <button className="tbtn" type="submit" disabled={busy}>서류 제출</button>
        </form>
      </section>
    </AppShell>
  );
}
