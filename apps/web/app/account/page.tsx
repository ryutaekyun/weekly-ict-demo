"use client";

import { useEffect, useState } from "react";
import AppShell from "@/components/AppShell";
import { apiFetch, getCurrentUser, updateMyProfile, type CurrentUser } from "@/lib/api";
import { FIELD_LABELS, fmtDate, ROLE_LABELS } from "@/lib/labels";

export default function AccountPage() {
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [name, setName] = useState("");
  const [job, setJob] = useState("");
  const [favs, setFavs] = useState<string[]>([]);
  const [msg, setMsg] = useState<{ kind: "ok" | "err"; text: string } | null>(null);
  const [pw, setPw] = useState({ current: "", next: "" });
  const [pwMsg, setPwMsg] = useState<{ kind: "ok" | "err"; text: string } | null>(null);

  useEffect(() => {
    getCurrentUser().then((u) => { setUser(u); setName(u.display_name); setJob(u.job_title ?? ""); setFavs(u.favorite_fields); }).catch(() => undefined);
  }, []);

  async function saveProfile(e: React.FormEvent) {
    e.preventDefault();
    setMsg(null);
    try {
      const u = await updateMyProfile({ display_name: name, job_title: job, favorite_fields: favs });
      setUser(u);
      setMsg({ kind: "ok", text: "내 정보를 저장했습니다" });
    } catch (err) { setMsg({ kind: "err", text: err instanceof Error ? err.message : "저장 실패" }); }
  }

  async function changePw(e: React.FormEvent) {
    e.preventDefault();
    setPwMsg(null);
    try {
      await apiFetch("/auth/password", { method: "PATCH", body: JSON.stringify({ current_password: pw.current, new_password: pw.next }) });
      setPw({ current: "", next: "" });
      setPwMsg({ kind: "ok", text: "비밀번호를 변경했습니다" });
    } catch (err) { setPwMsg({ kind: "err", text: err instanceof Error ? err.message : "변경 실패" }); }
  }

  const toggle = (c: string) => setFavs(favs.includes(c) ? favs.filter((f) => f !== c) : [...favs, c]);

  return (
    <AppShell>
      <h1 style={{ fontSize: 22, fontWeight: 700, margin: "0 0 20px" }}>내 정보</h1>
      {user && (
        <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 3fr) minmax(0, 2fr)", gap: 20 }}>
          <form className="panel" onSubmit={saveProfile}>
            <h2 className="section-title">프로필·관심 분야</h2>
            <p style={{ fontSize: 13, color: "var(--ink-muted)", margin: "0 0 14px" }}>{user.email} · <span className="badge">{ROLE_LABELS[user.role] ?? user.role}</span> · 최근 로그인 {fmtDate(user.last_login_at)}</p>
            <label className="field">이름<input value={name} onChange={(e) => setName(e.target.value)} required minLength={2} /></label>
            <label className="field">직함<input value={job} onChange={(e) => setJob(e.target.value)} /></label>
            <fieldset style={{ border: 0, padding: 0, margin: "0 0 14px" }}>
              <legend style={{ fontSize: 13, fontWeight: 700, marginBottom: 8 }}>관심 ICT 분야 <span style={{ fontWeight: 400, color: "var(--ink-muted)" }}>— 대시보드의 &lsquo;관심 분야 최신 동향&rsquo;에 쓰입니다</span></legend>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6 }}>
                {Object.entries(FIELD_LABELS).map(([c, l]) => (
                  <label key={c} style={{ fontSize: 13 }}><input type="checkbox" checked={favs.includes(c)} onChange={() => toggle(c)} data-testid={`fav-${c}`} /> {l}</label>
                ))}
              </div>
            </fieldset>
            {msg && <div role={msg.kind === "err" ? "alert" : "status"} className={`notice ${msg.kind}`} style={{ marginBottom: 12 }}>{msg.text}</div>}
            <button className="tbtn primary" type="submit">저장</button>
          </form>

          <form className="panel" onSubmit={changePw} style={{ alignSelf: "start" }}>
            <h2 className="section-title">비밀번호 변경</h2>
            <label className="field">현재 비밀번호<input type="password" autoComplete="current-password" required value={pw.current} onChange={(e) => setPw({ ...pw, current: e.target.value })} /></label>
            <label className="field">새 비밀번호<input type="password" autoComplete="new-password" required minLength={10} value={pw.next} onChange={(e) => setPw({ ...pw, next: e.target.value })} /></label>
            <p style={{ fontSize: 12, color: "var(--ink-muted)", margin: "-6px 0 12px" }}>10자 이상으로 설정하세요.</p>
            {pwMsg && <div role={pwMsg.kind === "err" ? "alert" : "status"} className={`notice ${pwMsg.kind}`} style={{ marginBottom: 12 }}>{pwMsg.text}</div>}
            <button className="tbtn" type="submit">비밀번호 변경</button>
          </form>
        </div>
      )}
    </AppShell>
  );
}
