"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import AppShell from "@/components/AppShell";
import { createCandidate, listCandidates, listUsers, UnauthorizedError, type Candidate, type UserSummary } from "@/lib/api";
import { CANDIDATE_STATUS_LABELS, FIELD_LABELS, fmtDateOnly } from "@/lib/labels";

function CandidatesList() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [users, setUsers] = useState<UserSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  // 검색 조건은 주소(URL)에 두어 상세 화면에서 뒤로 돌아와도 유지된다
  const [fieldCode, setFieldCode] = useState(searchParams.get("field_code") ?? "");
  const [status, setStatus] = useState(searchParams.get("status") ?? "");
  const [assignee, setAssignee] = useState(searchParams.get("assignee_user_id") ?? "");
  const [mine, setMine] = useState(searchParams.get("mine") === "true");
  const [q, setQ] = useState(searchParams.get("q") ?? "");
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ title: "", field_code: "ai", summary: "", recommended_reason: "", assignee_user_id: "" });
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => { listUsers().then(setUsers).catch(() => undefined); }, []);
  useEffect(() => {
    setLoading(true);
    let stale = false; // 늦게 도착한 이전 조건의 응답이 최신 목록을 덮어쓰지 않도록 한다
    listCandidates({ field_code: fieldCode || undefined, status: status || undefined, q: q || undefined, assignee_user_id: assignee || undefined, mine: mine ? "true" : undefined })
      .then((res) => { if (!stale) setCandidates(res); })
      .catch((err) => {
        if (stale) return;
        if (err instanceof UnauthorizedError) { router.push("/login"); return; }
        setError(err instanceof Error ? err.message : "불러오기 실패");
      })
      .finally(() => { if (!stale) setLoading(false); });
    return () => { stale = true; };
  }, [fieldCode, status, q, assignee, mine, router, reloadKey]);

  function syncUrl(next: Record<string, string>) {
    const merged: Record<string, string> = { field_code: fieldCode, status, q, assignee_user_id: assignee, mine: mine ? "true" : "", ...next };
    const params = new URLSearchParams();
    Object.entries(merged).forEach(([k, v]) => { if (v) params.set(k, v); });
    router.replace(`/candidates${params.toString() ? `?${params}` : ""}`, { scroll: false });
  }

  async function submitNew(e: React.FormEvent) {
    e.preventDefault();
    setError(null); setMessage(null);
    if (!form.title.trim()) { setError("후보주제 제목을 입력하세요"); return; }
    try {
      const c = await createCandidate({ field_code: form.field_code, title: form.title.trim(), summary: form.summary || undefined,
        recommended_reason: form.recommended_reason || undefined, assignee_user_id: form.assignee_user_id || undefined });
      setMessage(`후보주제를 등록했습니다: ${c.title}`);
      setForm({ title: "", field_code: form.field_code, summary: "", recommended_reason: "", assignee_user_id: "" });
      setShowForm(false);
      setReloadKey((k) => k + 1);
    } catch (err) { setError(err instanceof Error ? err.message : "등록 실패"); }
  }

  const nameOf = (id: string | null) => users.find((u) => u.id === id)?.display_name ?? "-";

  return (
    <AppShell>
      <h1 style={{ fontSize: 20, fontWeight: 700, marginBottom: 4 }}>후보주제 선정·검토</h1>
      <p style={{ color: "var(--ink-muted)", fontSize: 13, marginTop: 0 }}>
        AI/규칙 기반 추천과 연구원이 직접 등록한 후보주제를 한 화면에서 다룹니다. 연구원 내부 검토·확정과 IITP 공식 선정은 별개입니다.
      </p>

      <div className="panel" style={{ display: "flex", flexWrap: "wrap", gap: 10, marginBottom: 14, alignItems: "center" }}>
        <select aria-label="분야 필터" value={fieldCode} onChange={(e) => { setFieldCode(e.target.value); syncUrl({ field_code: e.target.value }); }} style={selectStyle}>
          <option value="">전체 분야</option>
          {Object.entries(FIELD_LABELS).map(([c, l]) => <option key={c} value={c}>{l}</option>)}
        </select>
        <select aria-label="검토상태 필터" value={status} onChange={(e) => { setStatus(e.target.value); syncUrl({ status: e.target.value }); }} style={selectStyle}>
          <option value="">전체 검토상태</option>
          {Object.entries(CANDIDATE_STATUS_LABELS).map(([c, l]) => <option key={c} value={c}>{l}</option>)}
        </select>
        <select aria-label="담당자 필터" value={assignee} onChange={(e) => { setAssignee(e.target.value); syncUrl({ assignee_user_id: e.target.value }); }} style={selectStyle}>
          <option value="">전체 담당자</option>
          {users.map((u) => <option key={u.id} value={u.id}>{u.display_name}</option>)}
        </select>
        <label style={{ fontSize: 13 }}><input type="checkbox" checked={mine} onChange={(e) => { setMine(e.target.checked); syncUrl({ mine: e.target.checked ? "true" : "" }); }} /> 내 담당만</label>
        <input aria-label="제목 검색" value={q} onChange={(e) => { setQ(e.target.value); syncUrl({ q: e.target.value }); }} placeholder="제목 검색" style={{ ...selectStyle, minWidth: 200 }} />
        <button className="tbtn primary" onClick={() => setShowForm((v) => !v)}>{showForm ? "등록 닫기" : "후보주제 등록"}</button>
        <span style={{ marginLeft: "auto", fontSize: 13, color: "var(--ink-muted)" }} data-testid="candidate-count">총 {candidates.length}건</span>
      </div>

      {showForm && (
        <form className="panel" onSubmit={submitNew} style={{ display: "grid", gap: 8, marginBottom: 14 }}>
          <b>새 후보주제 등록(연구원 직접 등록 — 내부 후보이며 IITP 선정이 아닙니다)</b>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <select aria-label="후보 분야" value={form.field_code} onChange={(e) => setForm({ ...form, field_code: e.target.value })} style={selectStyle}>
              {Object.entries(FIELD_LABELS).map(([c, l]) => <option key={c} value={c}>{l}</option>)}
            </select>
            <input aria-label="후보주제 제목" placeholder="후보주제 제목" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} style={{ ...selectStyle, flex: 1, minWidth: 260 }} />
            <select aria-label="후보 담당자" value={form.assignee_user_id} onChange={(e) => setForm({ ...form, assignee_user_id: e.target.value })} style={selectStyle}>
              <option value="">담당자 미지정</option>
              {users.map((u) => <option key={u.id} value={u.id}>{u.display_name}</option>)}
            </select>
          </div>
          <textarea aria-label="후보 설명" placeholder="설명" rows={2} value={form.summary} onChange={(e) => setForm({ ...form, summary: e.target.value })} style={selectStyle} />
          <textarea aria-label="후보 등록 근거" placeholder="등록 근거(원문·이슈 등)" rows={2} value={form.recommended_reason} onChange={(e) => setForm({ ...form, recommended_reason: e.target.value })} style={selectStyle} />
          <div><button className="tbtn primary" type="submit">등록</button></div>
        </form>
      )}

      {error && <p role="alert" style={{ color: "var(--bad)" }}>{error}</p>}
      {message && <p role="status" style={{ color: "var(--ok)", fontSize: 13 }}>{message}</p>}
      {loading && <p style={{ color: "var(--ink-muted)" }}>불러오는 중...</p>}

      <div className="panel" style={{ padding: 0, overflow: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13.5 }}>
          <thead>
            <tr style={{ textAlign: "left", background: "var(--panel-2)" }}>
              <th style={th}>분야</th><th style={th}>제목</th><th style={th}>발표일</th><th style={th}>출처</th><th style={th}>담당자</th><th style={th}>상태</th>
            </tr>
          </thead>
          <tbody>
            {candidates.map((c) => (
              <tr key={c.id} style={{ borderTop: "1px solid var(--border)" }}>
                <td style={td}>{FIELD_LABELS[c.field_code] ?? c.field_code}</td>
                <td style={td}><Link href={`/candidates/${c.id}`}>{c.title}</Link></td>
                <td style={td}>{fmtDateOnly(c.announced_date)}</td>
                <td style={td}>{c.source_org ?? "-"}</td>
                <td style={td}>{nameOf(c.assignee_user_id ?? null)}</td>
                <td style={td}><span className={`pill ${c.status}`}>{CANDIDATE_STATUS_LABELS[c.status] ?? c.status}</span></td>
              </tr>
            ))}
            {!loading && candidates.length === 0 && (
              <tr><td colSpan={6} style={{ padding: 20, textAlign: "center", color: "var(--ink-muted)" }}>조건에 맞는 후보주제가 없습니다</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </AppShell>
  );
}

const selectStyle: React.CSSProperties = { padding: "7px 9px", borderRadius: 8, border: "1px solid var(--border)", fontSize: 13 };
const th: React.CSSProperties = { padding: "9px 14px" };
const td: React.CSSProperties = { padding: "9px 14px" };

export default function CandidatesPage() {
  return (
    <Suspense fallback={<AppShell><p>불러오는 중...</p></AppShell>}>
      <CandidatesList />
    </Suspense>
  );
}
