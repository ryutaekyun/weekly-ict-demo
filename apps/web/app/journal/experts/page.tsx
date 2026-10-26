"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import AppShell from "@/components/AppShell";
import { getCurrentUser, type CurrentUser } from "@/lib/api";
import { jConsent, jCreateAuthorAccount, jCreateExpert, jCreateReviewerAccount, jExperts, type JExpert } from "@/lib/journalApi";

const inp: React.CSSProperties = { padding: 8, borderRadius: 8, border: "1px solid var(--border)", fontSize: 13, minWidth: 0 };
const FIELDS = ["AI", "반도체", "통신·네트워크", "SW·클라우드", "보안", "데이터", "XR·메타버스", "로봇·자율주행", "ICT 융합"];
const CONSENT: Record<string, string> = { none: "동의 전", agreed: "동의", withdrawn: "철회" };

export default function ExpertsPage() {
  const [items, setItems] = useState<JExpert[]>([]);
  const [q, setQ] = useState("");
  const [field, setField] = useState("");
  const [form, setForm] = useState({ name: "", affiliation: "", department: "", position_title: "", email: "", phone: "", research_summary: "", fields: [] as string[], is_synthetic: false });
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [me, setMe] = useState<CurrentUser | null>(null);
  const [acc, setAcc] = useState({ kind: "author", expert_id: "", email: "", display_name: "", password: "" });

  const load = useCallback(() => { jExperts(q, field).then(setItems).catch((e) => setError(e instanceof Error ? e.message : "불러오기 실패")); }, [q, field]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => { getCurrentUser().then(setMe).catch(() => undefined); }, []);

  async function createAccount(e: React.FormEvent) {
    e.preventDefault();
    setError(null); setMessage(null);
    try {
      if (acc.kind === "author") { await jCreateAuthorAccount({ email: acc.email, display_name: acc.display_name, password: acc.password, expert_id: acc.expert_id }); }
      else { await jCreateReviewerAccount({ email: acc.email, display_name: acc.display_name, password: acc.password }); }
      setMessage(`포털 계정을 만들었습니다(${acc.email}). 비밀번호는 전달 후 변경하도록 안내하세요.`);
      setAcc({ ...acc, email: "", display_name: "", password: "" });
      load();
    } catch (err) { setError(err instanceof Error ? err.message : "계정 생성 실패"); }
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null); setMessage(null);
    if (!form.name.trim() || !form.affiliation.trim()) { setError("성명과 소속은 필수입니다"); return; }
    try {
      const c = await jCreateExpert({ ...form, department: form.department || null, position_title: form.position_title || null, email: form.email || null, phone: form.phone || null,
        research_summary: form.research_summary || null });
      setMessage(`전문가를 등록했습니다(${c.expert_code}). 개인정보 이용 동의는 등록 후 별도로 기록하세요.`);
      setForm({ name: "", affiliation: "", department: "", position_title: "", email: "", phone: "", research_summary: "", fields: [], is_synthetic: false });
      load();
    } catch (err) { setError(err instanceof Error ? err.message : "등록 실패"); }
  }

  return (
    <AppShell>
      <div style={{ marginBottom: 8 }}><Link href="/journal" style={{ fontSize: 13 }}>← 주간기술동향지 편집 대시보드</Link></div>
      <h1 style={{ fontSize: 20, fontWeight: 700, marginBottom: 4 }}>외부 전문가(집필진) DB</h1>
      <p style={{ color: "var(--ink-muted)", fontSize: 13, marginTop: 0 }}>
        전문가 정보는 개인정보이므로 편집 담당자 이상만 조회하며 조회 이력이 남습니다. 실제 집필 가능 여부는 추정하지 않고 의뢰 응답 이력만 보여줍니다.
        이 화면의 데이터는 공개 저장소에 올라가지 않습니다.
      </p>
      {error && <p role="alert" style={{ color: "#b42318", fontSize: 13 }}>{error}</p>}
      {message && <p role="status" style={{ color: "var(--ok)", fontSize: 13 }}>{message}</p>}
      <form className="panel" onSubmit={submit} style={{ display: "grid", gap: 8, marginBottom: 14 }}>
        <b>전문가 등록</b>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <input aria-label="성명" placeholder="성명" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} style={{ ...inp, flex: 1 }} />
          <input aria-label="소속기관" placeholder="소속기관" value={form.affiliation} onChange={(e) => setForm({ ...form, affiliation: e.target.value })} style={{ ...inp, flex: 1 }} />
          <input aria-label="부서" placeholder="부서" value={form.department} onChange={(e) => setForm({ ...form, department: e.target.value })} style={{ ...inp, flex: 1 }} />
          <input aria-label="직위" placeholder="직위" value={form.position_title} onChange={(e) => setForm({ ...form, position_title: e.target.value })} style={{ ...inp, flex: 1 }} />
        </div>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <input aria-label="이메일" placeholder="이메일" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} style={{ ...inp, flex: 1 }} />
          <input aria-label="연락처" placeholder="연락처" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} style={{ ...inp, flex: 1 }} />
        </div>
        <div style={{ fontSize: 13 }}>전문 분야(복수 선택):{" "}
          {FIELDS.map((f) => (
            <label key={f} style={{ marginRight: 10 }}><input type="checkbox" aria-label={`분야 ${f}`} checked={form.fields.includes(f)}
              onChange={(e) => setForm({ ...form, fields: e.target.checked ? [...form.fields, f] : form.fields.filter((x) => x !== f) })} /> {f}</label>
          ))}
        </div>
        <textarea aria-label="주요 연구·집필 분야" placeholder="주요 연구·집필 분야" rows={2} value={form.research_summary} onChange={(e) => setForm({ ...form, research_summary: e.target.value })} style={inp} />
        <label style={{ fontSize: 13 }}><input type="checkbox" checked={form.is_synthetic} onChange={(e) => setForm({ ...form, is_synthetic: e.target.checked })} /> 합성 테스트 데이터(가상 인물)</label>
        <div><button className="tbtn primary" type="submit">전문가 등록</button></div>
      </form>

      <div style={{ display: "flex", gap: 8, marginBottom: 8 }}>
        <input aria-label="전문가 검색" placeholder="이름·소속·연구 분야 검색" value={q} onChange={(e) => setQ(e.target.value)} style={{ ...inp, minWidth: 260 }} />
        <select aria-label="분야 필터" value={field} onChange={(e) => setField(e.target.value)} style={inp}>
          <option value="">전체 분야</option>
          {FIELDS.map((f) => <option key={f} value={f}>{f}</option>)}
        </select>
      </div>
      <div className="panel" style={{ padding: 0, overflow: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
          <thead><tr style={{ textAlign: "left", background: "var(--panel-2)" }}>
            {["식별번호", "성명", "소속", "전문 분야", "의뢰 이력", "개인정보 동의", ""].map((h) => <th key={h} style={{ padding: "9px 12px" }}>{h}</th>)}
          </tr></thead>
          <tbody>
            {items.map((x) => (
              <tr key={x.id} style={{ borderTop: "1px solid var(--border)" }}>
                <td style={{ padding: "8px 12px" }}>{x.expert_code}{x.is_synthetic && <span className="pill hold" style={{ marginLeft: 4 }}>합성</span>}</td>
                <td style={{ padding: "8px 12px" }}>{x.name}</td>
                <td style={{ padding: "8px 12px" }}>{x.affiliation}</td>
                <td style={{ padding: "8px 12px" }}>{x.fields.join(", ") || "-"}</td>
                <td style={{ padding: "8px 12px" }}>수락 {x.commission_counts.accepted ?? 0} · 거절 {x.commission_counts.declined ?? 0} · 미응답 {x.commission_counts.no_response ?? 0}</td>
                <td style={{ padding: "8px 12px" }}>{CONSENT[x.consent_status]}</td>
                <td style={{ padding: "8px 12px" }}>
                  <button className="tbtn" aria-label={`${x.name} 동의 기록`} onClick={() => jConsent(x.id, "agreed").then(load).catch((e) => setError(e.message))}>동의 기록</button>
                </td>
              </tr>
            ))}
            {items.length === 0 && <tr><td colSpan={7} style={{ padding: 14, color: "var(--ink-muted)" }}>등록된 전문가가 없습니다.</td></tr>}
          </tbody>
        </table>
      </div>
      {me?.role === "admin" && (
        <form className="panel" onSubmit={createAccount} style={{ display: "grid", gap: 8, marginTop: 14 }}>
          <b>포털 계정 만들기(관리자)</b>
          <p style={{ fontSize: 12, color: "var(--ink-muted)", margin: 0 }}>외부 집필 전문가·검토 전문가가 로그인해 자신의 원고만 보도록 계정을 만듭니다. 실제 인물에게는 별도 승인 후에만 안내하세요(이 화면은 이메일을 보내지 않습니다).</p>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <select aria-label="계정 종류" value={acc.kind} onChange={(e) => { const v = e.target.value; setAcc((a) => ({ ...a, kind: v })); }} style={inp}>
              <option value="author">외부 집필 전문가</option><option value="reviewer">외부 검토 전문가</option>
            </select>
            {acc.kind === "author" && (
              <select aria-label="연결할 전문가" value={acc.expert_id} onChange={(e) => { const v = e.target.value; setAcc((a) => ({ ...a, expert_id: v })); }} style={inp}>
                <option value="">연결할 전문가 선택</option>
                {items.filter((x) => !x.user_id).map((x) => <option key={x.id} value={x.id}>{x.name} ({x.expert_code})</option>)}
              </select>
            )}
            <input aria-label="계정 이메일" placeholder="로그인 이메일" value={acc.email} onChange={(e) => setAcc({ ...acc, email: e.target.value })} style={inp} />
            <input aria-label="계정 표시 이름" placeholder="표시 이름" value={acc.display_name} onChange={(e) => setAcc({ ...acc, display_name: e.target.value })} style={inp} />
            <input aria-label="계정 비밀번호" type="password" placeholder="비밀번호(12자 이상)" value={acc.password} onChange={(e) => setAcc({ ...acc, password: e.target.value })} style={inp} />
            <button className="tbtn primary" type="submit">계정 생성</button>
          </div>
        </form>
      )}
    </AppShell>
  );
}
