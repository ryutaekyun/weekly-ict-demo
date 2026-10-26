"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import AppShell from "@/components/AppShell";
import { pCommissions, pRespond, uploadForm, type JManuscript, type PCommission } from "@/lib/journalApi";

const inp: React.CSSProperties = { padding: 8, borderRadius: 8, border: "1px solid var(--border)", fontSize: 13, minWidth: 0 };

export default function PortalCommissionPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [c, setC] = useState<PCommission | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState("");
  const [f, setF] = useState({ title: "", title_en: "", summary: "", authors: "", references_text: "", copyright: false, third_party_note: "", note: "" });

  const load = useCallback(() => { pCommissions().then((all) => { const m = all.find((x) => x.id === id) ?? null; setC(m); if (m) setF((s) => ({ ...s, title: s.title || m.topic })); }).catch((e) => setError(e instanceof Error ? e.message : "불러오기 실패")); }, [id]);
  useEffect(() => { load(); }, [load]);

  async function respond(response: "accept" | "decline") {
    setError(null); setBusy(true);
    try { await pRespond(id, response, note || undefined); setMessage(response === "accept" ? "집필을 수락했습니다. 아래에서 원고를 제출하세요." : "집필을 거절했습니다."); load(); }
    catch (e) { setError(e instanceof Error ? e.message : "응답 실패"); } finally { setBusy(false); }
  }

  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null); setMessage(null);
    const file = (e.currentTarget.elements.namedItem("manuscript") as HTMLInputElement).files?.[0];
    if (!file) { setError("원고 파일(DOCX 또는 PDF)을 선택하세요"); return; }
    const authors = f.authors.split("\n").map((l) => l.trim()).filter(Boolean).map((l, i) => { const [name, ...rest] = l.split("|"); return { name: name.trim(), affiliation: rest.join("|").trim(), corresponding: i === 0 }; });
    const fd = new FormData();
    fd.append("file", file); fd.append("title", f.title); fd.append("title_en", f.title_en); fd.append("summary", f.summary); fd.append("authors_json", JSON.stringify(authors));
    fd.append("references_text", f.references_text); fd.append("copyright_confirmed", String(f.copyright)); fd.append("third_party_note", f.third_party_note); fd.append("note", f.note);
    setBusy(true);
    try {
      const ms = await uploadForm<JManuscript>(`/journal/portal/author/commissions/${id}/submit`, fd);
      router.push(`/portal/manuscripts/${ms.id}`);
    } catch (err) { setError(err instanceof Error ? err.message : "제출 실패"); } finally { setBusy(false); }
  }

  if (!c) return <AppShell>{error ? <p role="alert" style={{ color: "#b42318" }}>{error}</p> : <p>불러오는 중...</p>}</AppShell>;
  return (
    <AppShell>
      <div style={{ marginBottom: 8 }}><Link href="/portal" style={{ fontSize: 13 }}>← 원고 집필 포털</Link></div>
      <h1 style={{ fontSize: 19, fontWeight: 700, marginBottom: 4 }}>{c.topic}</h1>
      <div style={{ fontSize: 13, marginBottom: 8 }}>{c.issue_label} · 제출 기한 {c.due_date ?? "미정"} · <span className="pill hold">{c.status_label}</span></div>
      {error && <p role="alert" style={{ color: "#b42318", fontSize: 13 }}>{error}</p>}
      {message && <p role="status" style={{ color: "var(--ok)", fontSize: 13 }}>{message}</p>}
      <section className="panel" style={{ fontSize: 13, marginBottom: 12 }}>
        <b>의뢰 내용</b>
        {([["작성 취지", c.purpose], ["권장 목차·주요 내용", c.outline], ["원고 분량", c.length_spec], ["양식", c.format_spec], ["제출 방법", c.delivery_method], ["담당자 연락처", c.contact_info]] as [string, string | null][])
          .filter(([, v]) => v).map(([k, v]) => <div key={k}>{k}: {v}</div>)}
      </section>
      {c.can_respond && (
        <section className="panel" style={{ marginBottom: 12 }}>
          <b>집필 수락 여부</b>
          <div style={{ display: "flex", gap: 8, marginTop: 6, flexWrap: "wrap" }}>
            <input aria-label="응답 메모" placeholder="메모(선택)" value={note} onChange={(e) => setNote(e.target.value)} style={{ ...inp, minWidth: 260 }} />
            <button className="tbtn primary" disabled={busy} onClick={() => respond("accept")}>집필 수락</button>
            <button className="tbtn" disabled={busy} onClick={() => respond("decline")}>집필 거절</button>
          </div>
        </section>
      )}
      {c.can_submit && (
        <form className="panel" onSubmit={submit} style={{ display: "grid", gap: 8 }}>
          <b>원고 제출</b>
          <p style={{ fontSize: 12, color: "var(--ink-muted)", margin: 0 }}>DOCX 또는 PDF만 접수합니다. 매크로·스크립트·임베디드 개체가 있는 파일은 접수되지 않습니다. 제출한 파일은 버전으로 보관되며 덮어쓰지 않습니다.</p>
          <input aria-label="원고 제목" placeholder="원고 제목" value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} style={inp} />
          <input aria-label="영문 제목" placeholder="영문 제목" value={f.title_en} onChange={(e) => setF({ ...f, title_en: e.target.value })} style={inp} />
          <textarea aria-label="원고 요약" placeholder="원고 요약" rows={3} value={f.summary} onChange={(e) => setF({ ...f, summary: e.target.value })} style={inp} />
          <textarea aria-label="저자·소속" placeholder={"저자 (한 줄에 한 명: 이름|소속)\n예: 홍길동|가상대학교"} rows={3} value={f.authors} onChange={(e) => setF({ ...f, authors: e.target.value })} style={inp} />
          <textarea aria-label="참고문헌" placeholder="참고문헌(원고 안에 있으면 생략 가능)" rows={2} value={f.references_text} onChange={(e) => setF({ ...f, references_text: e.target.value })} style={inp} />
          <textarea aria-label="제3자 자료 사용 기록" placeholder="그림·표·사진 등 제3자 자료의 출처와 사용 허락 여부" rows={2} value={f.third_party_note} onChange={(e) => setF({ ...f, third_party_note: e.target.value })} style={inp} />
          <label style={{ fontSize: 13 }}><input type="checkbox" aria-label="저작권 이용 동의" checked={f.copyright} onChange={(e) => setF({ ...f, copyright: e.target.checked })} /> 원고의 저작권 및 이용(게재)에 관한 사항을 확인하고 동의합니다.</label>
          <input aria-label="원고 파일" name="manuscript" type="file" accept=".docx,.pdf" />
          <input aria-label="제출 메모" placeholder="제출 메모(선택)" value={f.note} onChange={(e) => setF({ ...f, note: e.target.value })} style={inp} />
          <div><button className="tbtn primary" type="submit" disabled={busy}>{busy ? "제출 중..." : "원고 제출"}</button></div>
        </form>
      )}
      {c.manuscript_id && <p style={{ fontSize: 13 }}><Link href={`/portal/manuscripts/${c.manuscript_id}`}>제출한 원고 보기</Link></p>}
    </AppShell>
  );
}
