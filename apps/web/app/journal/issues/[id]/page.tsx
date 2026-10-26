"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import AppShell from "@/components/AppShell";
import { getCurrentUser, type CurrentUser } from "@/lib/api";
import {
  downloadFile, jCommissionStatus, jCompleteStep, jCreateCommission, jCreateExport, jExperts, jIitp, jIssue, jMailPreview, jPatchIssue, jPublish,
  jReopenStep, jSaveMail, jSetItems, type JCommission, type JExpert, type JIssueDetail,
} from "@/lib/journalApi";

const inp: React.CSSProperties = { padding: 7, borderRadius: 8, border: "1px solid var(--border)", fontSize: 13, minWidth: 0 };
const STATE: Record<string, { label: string; cls: string }> = {
  done: { label: "완료", cls: "rec" }, delayed: { label: "지연", cls: "review" }, due_soon: { label: "마감 임박", cls: "hold" },
  upcoming: { label: "예정", cls: "hold" }, no_date: { label: "발간일 미입력", cls: "hold" },
};
const NEXT: Record<string, { to: string; label: string }[]> = {
  draft: [{ to: "requested", label: "의뢰함으로 기록" }], ready: [{ to: "requested", label: "의뢰함으로 기록" }],
  requested: [{ to: "accepted", label: "수락 처리" }, { to: "declined", label: "거절 처리" }, { to: "no_response", label: "미응답 처리" }],
  no_response: [{ to: "accepted", label: "수락 처리" }, { to: "declined", label: "거절 처리" }, { to: "requested", label: "다시 의뢰" }],
  accepted: [{ to: "declined", label: "거절(철회) 처리" }], declined: [{ to: "requested", label: "다시 의뢰" }],
};
const STATUSES = [["planning", "기획"], ["recruiting", "집필진 확보"], ["receiving", "원고 접수"], ["reviewing", "검토·심의"], ["editing", "편집·교정"], ["iitp_check", "IITP 확인 대기"]];

export default function JournalIssuePage() {
  const { id } = useParams<{ id: string }>();
  const [me, setMe] = useState<CurrentUser | null>(null);
  const [issue, setIssue] = useState<JIssueDetail | null>(null);
  const [experts, setExperts] = useState<JExpert[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [form, setForm] = useState({ expert_id: "", topic: "", due_date: "", purpose: "", length_spec: "", outline: "" });
  const [mail, setMail] = useState<{ id: string; subject: string; body: string; notice: string } | null>(null);
  const [order, setOrder] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    jIssue(id).then((d) => { setIssue(d); setOrder(d.items.map((i) => i.manuscript_id)); }).catch((e) => setError(e instanceof Error ? e.message : "불러오기 실패"));
  }, [id]);
  useEffect(() => { getCurrentUser().then(setMe).catch(() => undefined); jExperts().then(setExperts).catch(() => undefined); }, []);
  useEffect(() => { load(); }, [load]);

  async function act<T>(fn: () => Promise<T>, ok?: string) {
    setError(null); setMessage(null); setBusy(true);
    try { await fn(); if (ok) setMessage(ok); load(); } catch (e) { setError(e instanceof Error ? e.message : "처리 실패"); } finally { setBusy(false); }
  }

  if (!issue) return <AppShell>{error ? <p role="alert" style={{ color: "#b42318" }}>{error}</p> : <p>불러오는 중...</p>}</AppShell>;
  const isAdmin = me?.role === "admin";
  const canDecide = me?.role === "admin" || me?.role === "approver";
  const accepted = issue.manuscripts.filter((m) => m.status === "accepted");
  const move = (idx: number, d: number) => setOrder((o) => { const n = [...o]; const j = idx + d; if (j < 0 || j >= n.length) return n; [n[idx], n[j]] = [n[j], n[idx]]; return n; });

  return (
    <AppShell>
      <div style={{ marginBottom: 8 }}><Link href="/journal" style={{ fontSize: 13 }}>← 주간기술동향지 편집 대시보드</Link></div>
      <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap", marginBottom: 6 }}>
        <h1 style={{ fontSize: 20, fontWeight: 700, margin: 0 }}>주간기술동향지 {issue.label}</h1>
        <span className="pill review">{issue.status_label}</span>
        <span className="pill hold">{issue.iitp_confirmed ? "IITP 확인 완료" : "IITP 공식 확인 전"}</span>
        {issue.is_synthetic && <span className="pill review">합성 테스트 회차</span>}
        {issue.published_at && <span className="pill rec">발간 기록 {issue.published_at}</span>}
      </div>
      {error && <p role="alert" style={{ color: "#b42318", fontSize: 13 }}>{error}</p>}
      {message && <p role="status" style={{ color: "var(--ok)", fontSize: 13 }}>{message}</p>}

      <section className="panel" style={{ marginBottom: 12, display: "grid", gap: 8 }}>
        <b>회차 정보</b>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
          <label style={{ fontSize: 13 }}>발간 예정일{" "}
            <input aria-label="발간 예정일" type="date" defaultValue={issue.publish_date ?? ""} disabled={!isAdmin} style={inp}
              onBlur={(e) => { if (e.target.value && e.target.value !== issue.publish_date) { const v = e.target.value; act(() => jPatchIssue(id, { publish_date: v }), "발간 예정일을 저장하고 마감일을 다시 계산했습니다"); } }} /></label>
          {!isAdmin && <span style={{ fontSize: 12, color: "var(--ink-muted)" }}>발간일은 관리자만 입력·변경합니다</span>}
          <label style={{ fontSize: 13 }}>진행 상태{" "}
            <select aria-label="진행 상태" value={STATUSES.some(([k]) => k === issue.status) ? issue.status : ""} disabled={issue.status === "published"} style={inp}
              onChange={(e) => { const v = e.target.value; act(() => jPatchIssue(id, { status: v }), "진행 상태를 바꿨습니다"); }}>
              {issue.status === "published" && <option value="">발간 기록</option>}
              {STATUSES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
            </select></label>
          <input aria-label="회차 주제" placeholder="기획 주제" defaultValue={issue.topic ?? ""} style={{ ...inp, minWidth: 260 }}
            onBlur={(e) => { if (e.target.value !== (issue.topic ?? "")) { const v = e.target.value; act(() => jPatchIssue(id, { topic: v })); } }} />
          <input aria-label="회차 기술 분야" placeholder="주요 기술 분야" defaultValue={issue.tech_field ?? ""} style={inp}
            onBlur={(e) => { if (e.target.value !== (issue.tech_field ?? "")) { const v = e.target.value; act(() => jPatchIssue(id, { tech_field: v })); } }} />
        </div>
      </section>

      <section className="panel" style={{ marginBottom: 12 }}>
        <b>편집 일정 (발간일 기준)</b>
        <p style={{ fontSize: 12, color: "var(--ink-muted)", margin: "2px 0 6px" }}>마감일과 실제 완료일은 구분합니다. 기한이 지나도 자동으로 완료 처리하지 않고 &lsquo;지연&rsquo;으로 표시합니다.</p>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
          <tbody>
            {issue.steps.map((s) => (
              <tr key={s.id} style={{ borderTop: "1px solid var(--border)" }}>
                <td style={{ padding: "6px 8px", width: 90 }}>D-{s.window_start_days ? `${s.window_start_days}~${s.offset_days}` : s.offset_days}</td>
                <td style={{ padding: "6px 8px" }}>{s.label}{s.impact && <div style={{ fontSize: 12, color: "#9a4b00" }}>{s.impact}</div>}</td>
                <td style={{ padding: "6px 8px", whiteSpace: "nowrap" }}>{s.window_start_date ? `${s.window_start_date} ~ ` : ""}{s.due_date ?? "-"}</td>
                <td style={{ padding: "6px 8px" }}><span className={`pill ${STATE[s.state].cls}`}>{STATE[s.state].label}</span>{s.completed_at && <span style={{ fontSize: 12 }}> 완료일 {s.completed_at.slice(0, 10)}</span>}</td>
                <td style={{ padding: "6px 8px" }}>
                  {s.completed_at ? <button className="tbtn" disabled={busy} onClick={() => act(() => jReopenStep(id, s.id))}>완료 취소</button>
                    : <button className="tbtn" disabled={busy} aria-label={`${s.label} 완료 처리`} onClick={() => act(() => jCompleteStep(id, s.id))}>완료 처리</button>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="panel" style={{ marginBottom: 12 }}>
        <b>집필 의뢰</b>
        <form onSubmit={(e) => { e.preventDefault(); if (!form.expert_id || !form.topic.trim()) { setError("전문가와 집필 주제를 입력하세요"); return; }
          act(() => jCreateCommission({ issue_id: id, expert_id: form.expert_id, topic: form.topic.trim(), due_date: form.due_date || null, purpose: form.purpose || null,
            length_spec: form.length_spec || null, outline: form.outline || null }), "의뢰서를 작성했습니다(아직 의뢰하지 않은 초안입니다)").then(() => setForm({ expert_id: "", topic: "", due_date: "", purpose: "", length_spec: "", outline: "" })); }}
          style={{ display: "flex", gap: 8, flexWrap: "wrap", margin: "8px 0" }}>
          <select aria-label="의뢰 전문가" value={form.expert_id} onChange={(e) => { const v = e.target.value; setForm((f) => ({ ...f, expert_id: v })); }} style={inp}>
            <option value="">전문가 선택</option>
            {experts.map((x) => <option key={x.id} value={x.id}>{x.name} ({x.affiliation}) {x.fields.join("·")}</option>)}
          </select>
          <input aria-label="집필 주제" placeholder="집필 요청 주제" value={form.topic} onChange={(e) => setForm({ ...form, topic: e.target.value })} style={{ ...inp, flex: 1, minWidth: 220 }} />
          <input aria-label="집필 마감일" type="date" value={form.due_date} onChange={(e) => setForm({ ...form, due_date: e.target.value })} style={inp} />
          <input aria-label="원고 분량" placeholder="분량(예: 해당 연도 안내 기준)" value={form.length_spec} onChange={(e) => setForm({ ...form, length_spec: e.target.value })} style={inp} />
          <input aria-label="작성 취지" placeholder="작성 취지" value={form.purpose} onChange={(e) => setForm({ ...form, purpose: e.target.value })} style={{ ...inp, flex: 1, minWidth: 200 }} />
          <button className="tbtn primary" type="submit" disabled={busy}>의뢰서 작성</button>
        </form>
        {issue.commissions.map((c: JCommission) => (
          <div key={c.id} style={{ borderTop: "1px solid var(--border)", padding: "8px 0", fontSize: 13 }}>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
              <b>{c.topic}</b> · {c.expert_name}({c.expert_code}) · 마감 {c.due_date ?? "미정"} <span className="pill hold">{c.status_label}</span>
              {c.mail_status !== "none" && <span className="pill hold">안내 메일: {c.mail_status === "pending_send" ? "발송 대기(미발송)" : "임시저장"}</span>}
              {c.manuscript_id && <Link href={`/journal/manuscripts/${c.manuscript_id}`}>원고 열기</Link>}
            </div>
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 4 }}>
              {(NEXT[c.status] ?? []).map((n) => <button key={n.to} className="tbtn" disabled={busy} aria-label={`${c.topic} ${n.label}`} onClick={() => act(() => jCommissionStatus(c.id, n.to), `의뢰 상태: ${n.label}`)}>{n.label}</button>)}
              <button className="tbtn" onClick={() => jMailPreview(c.id).then((m) => setMail({ id: c.id, ...m })).catch((e) => setError(e.message))}>안내 메일 미리보기</button>
            </div>
            {mail?.id === c.id && (
              <div style={{ background: "var(--panel-2)", padding: 8, borderRadius: 8, marginTop: 6 }}>
                <div style={{ fontSize: 12, color: "#9a4b00" }}>{mail.notice}</div>
                <input aria-label="메일 제목" value={mail.subject} onChange={(e) => setMail({ ...mail, subject: e.target.value })} style={{ ...inp, width: "100%", margin: "4px 0" }} />
                <textarea aria-label="메일 본문" rows={8} value={mail.body} onChange={(e) => setMail({ ...mail, body: e.target.value })} style={{ ...inp, width: "100%" }} />
                <div style={{ display: "flex", gap: 6, marginTop: 4 }}>
                  <button className="tbtn" onClick={() => act(() => jSaveMail(c.id, mail.subject, mail.body, false), "임시저장했습니다(발송되지 않았습니다)")}>임시저장</button>
                  <button className="tbtn" onClick={() => act(() => jSaveMail(c.id, mail.subject, mail.body, true), "발송 대기로 표시했습니다 — 실제 발송은 이루어지지 않습니다")}>발송 대기로 표시</button>
                  <button className="tbtn" onClick={() => setMail(null)}>닫기</button>
                </div>
              </div>
            )}
          </div>
        ))}
        {issue.commissions.length === 0 && <p style={{ color: "var(--ink-muted)", fontSize: 12.5 }}>등록된 의뢰가 없습니다.</p>}
      </section>

      <section className="panel" style={{ marginBottom: 12 }}>
        <b>접수 원고</b>
        {issue.manuscripts.map((m) => (
          <div key={m.id} style={{ borderTop: "1px solid var(--border)", padding: "6px 0", fontSize: 13 }}>
            <Link href={`/journal/manuscripts/${m.id}`}>{m.title}</Link> · {m.expert_name} · <span className="pill hold">{m.status_label}</span> · 제출 버전 {m.version_count}건{m.proof_confirmed ? " · 최종 교정 확인" : ""}
          </div>
        ))}
        {issue.manuscripts.length === 0 && <p style={{ color: "var(--ink-muted)", fontSize: 12.5 }}>접수된 원고가 없습니다.</p>}
      </section>

      <section className="panel" style={{ marginBottom: 12 }}>
        <b>게재 원고 구성·발간본</b>
        <p style={{ fontSize: 12, color: "var(--ink-muted)", margin: "2px 0 6px" }}>게재 확정된 원고만 배치할 수 있습니다. 교정본이 확정되어 있으면 교정본이 발간본에 쓰입니다. 공식 주간기술동향지 양식이 없어 임시 템플릿으로 출력합니다.</p>
        {accepted.length === 0 && <p style={{ fontSize: 12.5, color: "var(--ink-muted)" }}>게재 확정된 원고가 없습니다.</p>}
        {accepted.map((m) => (
          <label key={m.id} style={{ display: "block", fontSize: 13 }}>
            <input type="checkbox" aria-label={`게재 배치: ${m.title}`} checked={order.includes(m.id)}
              onChange={(e) => setOrder((o) => (e.target.checked ? [...o, m.id] : o.filter((x) => x !== m.id)))} /> {m.title} ({m.expert_name}) {m.proof_confirmed ? "· 교정 확인" : "· 교정 미확인"}
          </label>
        ))}
        {order.length > 0 && (
          <ol style={{ fontSize: 13 }}>
            {order.map((mid, idx) => {
              const m = issue.manuscripts.find((x) => x.id === mid);
              return <li key={mid}>{m?.title} <button className="tbtn" onClick={() => move(idx, -1)} aria-label={`${m?.title} 위로`}>↑</button> <button className="tbtn" onClick={() => move(idx, 1)} aria-label={`${m?.title} 아래로`}>↓</button></li>;
            })}
          </ol>
        )}
        <button className="tbtn" disabled={busy || accepted.length === 0} onClick={() => act(() => jSetItems(id, order), "게재 구성을 저장했습니다")}>게재 구성 저장</button>
        {issue.export_preflight.length > 0 && (
          <ul style={{ fontSize: 12.5, margin: "8px 0" }}>
            {issue.export_preflight.map((p, i) => <li key={i} style={{ color: p.level === "error" ? "#b42318" : p.level === "warn" ? "#9a4b00" : "var(--ink-muted)" }}>[{p.level === "error" ? "필수" : p.level === "warn" ? "경고" : "안내"}] {p.message}</li>)}
          </ul>
        )}
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 6 }}>
          <button className="tbtn" disabled={busy || issue.items.length === 0} onClick={() => act(() => jCreateExport(id, "docx", false), "DOCX 초안을 생성했습니다")}>DOCX 초안 생성</button>
          <button className="tbtn" disabled={busy || issue.items.length === 0} onClick={() => act(() => jCreateExport(id, "pdf", false), "PDF 초안을 생성했습니다")}>PDF 초안 생성</button>
          {canDecide && <button className="tbtn primary" disabled={busy || issue.items.length === 0} onClick={() => act(() => jCreateExport(id, "docx", true), "확정 DOCX를 생성했습니다")}>확정 DOCX 생성</button>}
          {canDecide && <button className="tbtn primary" disabled={busy || issue.items.length === 0} onClick={() => act(() => jCreateExport(id, "pdf", true), "확정 PDF를 생성했습니다")}>확정 PDF 생성</button>}
        </div>
        {issue.exports.map((e) => (
          <div key={e.id} style={{ borderTop: "1px solid var(--border)", marginTop: 6, paddingTop: 6, fontSize: 12.5 }}>
            {e.file_format.toUpperCase()} · {e.is_final ? "확정(내부)" : "초안"} · {e.status === "success" ? "성공" : e.status} · {e.page_count ?? "-"}쪽 · {e.file_size ? `${Math.round(e.file_size / 1024)}KB` : ""} · 템플릿 v{e.template_version} · {e.created_at.slice(0, 16).replace("T", " ")}
            {e.status === "success" && <button className="tbtn" style={{ marginLeft: 6 }} onClick={() => downloadFile(`/journal/issues/${id}/exports/${e.id}/download`, e.file_name ?? "journal").catch((er) => setError(er.message))}>다운로드</button>}
            {e.error_message && <span style={{ color: "#b42318" }}> {e.error_message}</span>}
            <div style={{ color: "var(--ink-muted)" }}>고정된 원고 버전: {e.items.map((i) => `v${i.version_no}`).join(", ")} · SHA-256 {e.file_sha256?.slice(0, 12)}…</div>
          </div>
        ))}
      </section>

      {canDecide && (
        <section className="panel">
          <b>IITP 확인·발간 기록</b>
          <p style={{ fontSize: 12, color: "var(--ink-muted)", margin: "2px 0 6px" }}>내부 확정과 IITP 공식 확인은 별개입니다. IITP 확인은 실제로 확인한 뒤에만 기록하세요. 발간 기록은 내부 이력이며 외부 업로드·발송은 하지 않습니다.</p>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <button className="tbtn" disabled={busy} onClick={() => act(() => jIitp(id, !issue.iitp_confirmed, "담당자 확인"), issue.iitp_confirmed ? "IITP 확인 기록을 해제했습니다" : "IITP 확인을 기록했습니다")}>{issue.iitp_confirmed ? "IITP 확인 해제" : "IITP 공식 확인 기록"}</button>
            <button className="tbtn" disabled={busy || issue.status === "published"} onClick={() => act(() => jPublish(id), "발간 이력을 기록했습니다")}>발간 이력 기록</button>
          </div>
        </section>
      )}
    </AppShell>
  );
}
