"use client";

import { Fragment, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import AppShell from "@/components/AppShell";
import {
  createFollowup, detectFollowups, getFollowup, listFollowups,
  type FollowupImpact, type FollowupNotice,
} from "@/lib/followupApi";
import { fmtDate } from "@/lib/labels";

const inp: React.CSSProperties = { padding: 8, borderRadius: 8, border: "1px solid var(--border)", fontSize: 13, minWidth: 0 };
const ENTITY: Record<string, { label: string; href: (id: string) => string }> = {
  manuscript: { label: "원고", href: (id) => `/manuscripts/${id}` },
  report: { label: "보고서", href: (id) => `/reports/${id}` },
  card_news: { label: "카드뉴스", href: (id) => `/card-news/${id}` },
};
const EMPTY = { title: "", original_doc_number: "", followup_url: "", followup_doc_number: "", followup_org: "", followup_effective_on: "",
  change_summary: "", item: "", old: "", new: "" };

export default function FollowupsPage() {
  const [items, setItems] = useState<(FollowupNotice & { open_count: number; affected_count: number })[]>([]);
  const [open, setOpen] = useState<string | null>(null);
  const [impact, setImpact] = useState<FollowupImpact | null>(null);
  const [form, setForm] = useState(EMPTY);
  const [candidates, setCandidates] = useState<Record<string, string | null>[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => { listFollowups().then(setItems).catch((e) => setError(e instanceof Error ? e.message : "불러오기 실패")); }, []);
  useEffect(() => { load(); }, [load]);

  async function toggle(id: string) {
    if (open === id) { setOpen(null); return; }
    setOpen(id);
    setImpact(null);
    getFollowup(id).then((r) => setImpact(r.impact)).catch(() => setImpact(null));
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null); setMessage(null);
    if (!form.title.trim() || !form.original_doc_number.trim() || !form.followup_url.trim() || !form.change_summary.trim()) {
      setError("제목, 기존 문서 번호, 후속 문서 URL, 변경 요약은 필수입니다");
      return;
    }
    setBusy(true);
    try {
      const created = await createFollowup({
        title: form.title.trim(), original_doc_number: form.original_doc_number.trim(), followup_url: form.followup_url.trim(),
        followup_doc_number: form.followup_doc_number.trim() || undefined, followup_org: form.followup_org.trim() || undefined,
        followup_effective_on: form.followup_effective_on.trim() || undefined, change_summary: form.change_summary.trim(),
        changes: form.item.trim() ? [{ item: form.item.trim(), old: form.old.trim(), new: form.new.trim() }] : [],
      });
      const n = Object.values(created.impact).reduce((a, rows) => a + rows.length, 0);
      setMessage(`후속 규정 알림을 등록했습니다 — 영향받는 산출물 ${n}건에 '재검토 필요'가 표시됩니다(내용은 바뀌지 않았습니다).`);
      setForm(EMPTY);
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "등록 실패");
    } finally { setBusy(false); }
  }

  async function detect() {
    setError(null); setBusy(true);
    try { setCandidates((await detectFollowups()).candidates); } catch (err) { setError(err instanceof Error ? err.message : "후보 검색 실패"); } finally { setBusy(false); }
  }

  return (
    <AppShell>
      <h1 style={{ fontSize: 20, fontWeight: 700, marginBottom: 4 }}>후속 규정 알림</h1>
      <p style={{ color: "var(--ink-muted)", fontSize: 13, marginTop: 0 }}>
        이미 근거로 쓴 원문을 바꾸는 후속 공식 문서(시행일 연기·정정 등)를 등록하면, 그 원문을 인용한 원고·보고서·카드뉴스에
        <b> 후속 규정 발견·재검토 필요</b>가 표시됩니다. 등록해도 내용과 검증 상태는 자동으로 바뀌지 않으며, 연구원이 수정하고 사유와 함께 확인해야 합니다.
      </p>
      {error && <p role="alert" style={{ color: "#b42318", fontSize: 13 }}>{error}</p>}
      {message && <p role="status" style={{ color: "var(--ok)", fontSize: 13 }}>{message}</p>}

      <form className="panel" onSubmit={submit} style={{ display: "grid", gap: 8, marginBottom: 14 }}>
        <div style={{ fontWeight: 700, fontSize: 14 }}>후속 규정 등록</div>
        <input aria-label="알림 제목" placeholder="예: FMVSS No. 305a 최종 규정 시행일 연기" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} style={inp} />
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <input aria-label="기존 문서 번호" placeholder="기존 문서 번호(예: 2024-28707)" value={form.original_doc_number} onChange={(e) => setForm({ ...form, original_doc_number: e.target.value })} style={{ ...inp, flex: 1 }} />
          <input aria-label="후속 문서 번호" placeholder="후속 문서 번호(예: 2025-02582)" value={form.followup_doc_number} onChange={(e) => setForm({ ...form, followup_doc_number: e.target.value })} style={{ ...inp, flex: 1 }} />
          <input aria-label="후속 문서 기관" placeholder="발표 기관" value={form.followup_org} onChange={(e) => setForm({ ...form, followup_org: e.target.value })} style={{ ...inp, flex: 1 }} />
        </div>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <input aria-label="후속 문서 URL" placeholder="후속 문서 원문 URL" value={form.followup_url} onChange={(e) => setForm({ ...form, followup_url: e.target.value })} style={{ ...inp, flex: 3 }} />
          <input aria-label="후속 문서 시행일" placeholder="시행일(YYYY-MM-DD)" value={form.followup_effective_on} onChange={(e) => setForm({ ...form, followup_effective_on: e.target.value })} style={{ ...inp, flex: 1 }} />
        </div>
        <textarea aria-label="변경 요약" placeholder="무엇이 바뀌었는지(원문에서 확인한 내용만)" rows={2} value={form.change_summary} onChange={(e) => setForm({ ...form, change_summary: e.target.value })} style={inp} />
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <input aria-label="변경 항목" placeholder="변경 항목(예: 시행일)" value={form.item} onChange={(e) => setForm({ ...form, item: e.target.value })} style={{ ...inp, flex: 1 }} />
          <input aria-label="변경 전" placeholder="변경 전" value={form.old} onChange={(e) => setForm({ ...form, old: e.target.value })} style={{ ...inp, flex: 1 }} />
          <input aria-label="변경 후" placeholder="변경 후" value={form.new} onChange={(e) => setForm({ ...form, new: e.target.value })} style={{ ...inp, flex: 1 }} />
        </div>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <button className="tbtn primary" type="submit" disabled={busy}>알림 등록</button>
          <button className="tbtn" type="button" onClick={detect} disabled={busy}>연방관보에서 후속 규정 후보 찾기</button>
          <span style={{ fontSize: 12, color: "var(--ink-muted)" }}>후보는 자동 등록되지 않습니다 — 원문을 확인한 뒤 위 양식으로 등록하세요.</span>
        </div>
        {candidates && (
          <div style={{ fontSize: 12.5 }}>
            {candidates.length === 0 ? "새 후속 규정 후보가 없습니다." : candidates.map((c) => (
              <div key={String(c.followup_doc_number)} style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 4 }}>
                <span>{c.published_at} · {c.title}</span>
                <button className="tbtn" type="button" onClick={() => setForm({ ...form, title: String(c.title).slice(0, 120), original_doc_number: String(c.original_doc_number ?? ""),
                  followup_doc_number: String(c.followup_doc_number ?? ""), followup_url: String(c.followup_url ?? ""), followup_effective_on: String(c.effective_on ?? "") })}>양식에 채우기</button>
              </div>
            ))}
          </div>
        )}
      </form>

      <div className="panel" style={{ padding: 0, overflow: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
          <thead>
            <tr style={{ textAlign: "left", background: "var(--panel-2)" }}>
              <th style={{ padding: "9px 12px" }}>알림</th><th style={{ padding: "9px 12px" }}>후속 문서</th>
              <th style={{ padding: "9px 12px" }}>시행일</th><th style={{ padding: "9px 12px" }}>확인 필요 / 영향</th><th style={{ padding: "9px 12px" }}>등록일</th>
            </tr>
          </thead>
          <tbody>
            {items.map((n) => (
              <Fragment key={n.id}>
                <tr style={{ borderTop: "1px solid var(--border)", cursor: "pointer" }} onClick={() => toggle(n.id)}>
                  <td style={{ padding: "9px 12px" }}><b>{n.title}</b>{n.is_pilot && <span className="pill hold" style={{ marginLeft: 6 }}>시범</span>}</td>
                  <td style={{ padding: "9px 12px" }}><a href={n.followup_url} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()}>{n.followup_doc_number ?? "원문"}</a></td>
                  <td style={{ padding: "9px 12px" }}>{n.followup_effective_on ?? "-"}</td>
                  <td style={{ padding: "9px 12px" }}>{n.open_count}건 / {n.affected_count}건</td>
                  <td style={{ padding: "9px 12px" }}>{fmtDate(n.created_at)}</td>
                </tr>
                {open === n.id && (
                  <tr key={`${n.id}-d`}><td colSpan={5} style={{ padding: "8px 12px 14px", background: "var(--panel-2)" }}>
                    <div>{n.change_summary}</div>
                    {n.changes.map((c, i) => <div key={i} style={{ fontSize: 12.5 }}>· {c.item}: <s>{c.old}</s> → <b>{c.new}</b></div>)}
                    {!impact ? <p>영향 범위를 불러오는 중...</p> : (Object.keys(ENTITY) as (keyof FollowupImpact)[]).map((k) => (
                      <div key={k} style={{ marginTop: 6 }}>
                        <b>{ENTITY[k].label}</b> {impact[k].length === 0 && <span style={{ color: "var(--ink-muted)" }}>영향 없음</span>}
                        {impact[k].map((r) => (
                          <div key={r.id} style={{ fontSize: 12.5, marginLeft: 8 }}>
                            <Link href={ENTITY[k].href(r.id)}>{r.title}</Link>{" "}
                            {r.acked ? <span className="pill rec">확인됨({r.resolution === "updated" ? "수정 반영" : "영향 없음"})</span> : <span className="pill review">재검토 필요</span>}
                            {r.note && <span style={{ color: "var(--ink-muted)" }}> — {r.note}</span>}
                          </div>
                        ))}
                      </div>
                    ))}
                  </td></tr>
                )}
              </Fragment>
            ))}
            {items.length === 0 && <tr><td colSpan={5} style={{ padding: 14, color: "var(--ink-muted)" }}>등록된 후속 규정 알림이 없습니다.</td></tr>}
          </tbody>
        </table>
      </div>
    </AppShell>
  );
}
