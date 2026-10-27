"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import AppShell from "@/components/AppShell";
import {
  approveUser, createInvite, getCurrentUser, listAdminUsers, listInvites, patchAdminUser, rejectUser, UnauthorizedError,
  type AdminUser,
} from "@/lib/api";
import { fmtDate, ROLE_LABELS } from "@/lib/labels";

const ASSIGNABLE = ["researcher", "reviewer", "approver", "source_admin", "admin"];
const STATUS_LABEL: Record<string, string> = { pending: "승인 대기", approved: "승인됨", rejected: "거절됨" };

export default function AdminUsersPage() {
  const router = useRouter();
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [invites, setInvites] = useState<{ id: string; email: string; role: string; expires_at: string; used: boolean }[]>([]);
  const [allowed, setAllowed] = useState<boolean | null>(null);
  const [msg, setMsg] = useState<{ kind: "ok" | "err"; text: string } | null>(null);
  const [inv, setInv] = useState({ email: "", role: "researcher" });
  const [link, setLink] = useState<string | null>(null);
  const [roleFor, setRoleFor] = useState<Record<string, string>>({});

  const load = useCallback(async () => {
    try {
      const me = await getCurrentUser();
      if (me.role !== "admin") { setAllowed(false); return; }
      setAllowed(true);
      setUsers(await listAdminUsers());
      setInvites(await listInvites());
    } catch (err) {
      if (err instanceof UnauthorizedError) router.replace("/login");
      else setMsg({ kind: "err", text: err instanceof Error ? err.message : "불러오기 실패" });
    }
  }, [router]);
  useEffect(() => { load(); }, [load]);

  async function run(fn: () => Promise<unknown>, ok: string) {
    setMsg(null);
    try { await fn(); setMsg({ kind: "ok", text: ok }); await load(); }
    catch (err) { setMsg({ kind: "err", text: err instanceof Error ? err.message : "처리 실패" }); }
  }

  async function invite(e: React.FormEvent) {
    e.preventDefault();
    setMsg(null); setLink(null);
    try {
      const r = await createInvite({ email: inv.email, role: inv.role });
      setLink(`${window.location.origin}${r.register_path}`);
      setInv({ email: "", role: inv.role });
      setInvites(await listInvites());
    } catch (err) { setMsg({ kind: "err", text: err instanceof Error ? err.message : "초대 실패" }); }
  }

  if (allowed === false) return <AppShell><div role="alert" className="notice err">시스템 관리자만 사용할 수 있는 화면입니다.</div></AppShell>;
  const pending = users.filter((u) => u.approval_status === "pending");

  return (
    <AppShell>
      <h1 style={{ fontSize: 22, fontWeight: 700, margin: "0 0 4px" }}>사용자 관리</h1>
      <p style={{ color: "var(--ink-muted)", fontSize: 13, margin: "0 0 20px" }}>가입 신청 승인, 역할 지정, 계정 비활성화, 초대 링크 발급을 처리합니다.</p>
      {msg && <div role={msg.kind === "err" ? "alert" : "status"} className={`notice ${msg.kind}`} style={{ marginBottom: 14 }}>{msg.text}</div>}

      <section className="panel" style={{ marginBottom: 20 }} data-testid="pending-box">
        <h2 className="section-title">가입 승인 대기 <span className="badge warn">{pending.length}명</span></h2>
        {pending.length === 0 && <p style={{ color: "var(--ink-muted)", fontSize: 13, margin: 0 }}>승인을 기다리는 가입 신청이 없습니다.</p>}
        {pending.map((u) => (
          <div key={u.id} className="list-row" data-testid="pending-row">
            <span className="t"><b>{u.display_name}</b> · {u.email}{u.job_title ? ` · ${u.job_title}` : ""}</span>
            <select aria-label={`${u.display_name} 역할`} value={roleFor[u.id] ?? "researcher"} onChange={(e) => setRoleFor({ ...roleFor, [u.id]: e.target.value })} style={{ padding: 6, borderRadius: 6 }}>
              {ASSIGNABLE.map((r) => <option key={r} value={r}>{ROLE_LABELS[r]}</option>)}
            </select>
            <button className="tbtn primary" onClick={() => run(() => approveUser(u.id, roleFor[u.id] ?? "researcher"), `${u.display_name}님의 가입을 승인했습니다`)}>승인</button>
            <button className="tbtn" onClick={() => run(() => rejectUser(u.id), `${u.display_name}님의 가입을 거절했습니다`)}>거절</button>
          </div>
        ))}
      </section>

      <section className="panel" style={{ marginBottom: 20 }}>
        <h2 className="section-title">초대 링크 발급</h2>
        <p style={{ fontSize: 12.5, color: "var(--ink-muted)", margin: "0 0 10px" }}>이메일 발송 시스템이 연결되기 전이므로 링크를 복사해 직접 전달하세요. 초대받은 이메일로만 가입할 수 있고 7일 뒤 만료됩니다.</p>
        <form onSubmit={invite} style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <input type="email" required aria-label="초대할 이메일" placeholder="초대할 이메일" value={inv.email} onChange={(e) => setInv({ ...inv, email: e.target.value })} style={{ flex: 1, minWidth: 240, padding: 9, borderRadius: 8, border: "1px solid var(--border)" }} />
          <select aria-label="초대 역할" value={inv.role} onChange={(e) => setInv({ ...inv, role: e.target.value })} style={{ padding: 9, borderRadius: 8 }}>
            {ASSIGNABLE.map((r) => <option key={r} value={r}>{ROLE_LABELS[r]}</option>)}
          </select>
          <button className="tbtn primary" type="submit">초대 링크 만들기</button>
        </form>
        {link && <div className="notice info" style={{ marginTop: 10, wordBreak: "break-all" }} data-testid="invite-link">지금만 표시됩니다: {link}</div>}
        {invites.length > 0 && <div style={{ marginTop: 10, fontSize: 12.5, color: "var(--ink-muted)" }}>최근 초대 {invites.length}건 — 사용됨 {invites.filter((i) => i.used).length}건</div>}
      </section>

      <section className="panel">
        <h2 className="section-title">전체 사용자 <span style={{ fontSize: 12, fontWeight: 400, color: "var(--ink-muted)" }}>{users.length}명</span></h2>
        <table style={{ width: "100%", fontSize: 13, borderCollapse: "collapse" }}>
          <thead><tr style={{ textAlign: "left", color: "var(--ink-muted)" }}><th style={{ padding: 6 }}>이름</th><th>이메일</th><th>역할</th><th>상태</th><th>최근 로그인</th><th /></tr></thead>
          <tbody>
            {users.map((u) => (
              <tr key={u.id} style={{ borderTop: "1px solid var(--border)" }} data-testid="user-row">
                <td style={{ padding: 8 }}>{u.display_name}</td>
                <td>{u.email}</td>
                <td>
                  {u.approval_status === "approved" ? (
                    <select aria-label={`${u.display_name} 역할 변경`} value={u.role} onChange={(e) => run(() => patchAdminUser(u.id, { role: e.target.value }), `${u.display_name}님의 역할을 변경했습니다`)} style={{ padding: 5, borderRadius: 6 }}>
                      {(ASSIGNABLE.includes(u.role) ? ASSIGNABLE : [...ASSIGNABLE, u.role]).map((r) => <option key={r} value={r}>{ROLE_LABELS[r] ?? r}</option>)}
                    </select>
                  ) : (ROLE_LABELS[u.role] ?? u.role)}
                </td>
                <td><span className={`badge ${u.approval_status === "approved" ? (u.is_active ? "green" : "bad") : u.approval_status === "pending" ? "warn" : "bad"}`}>{u.approval_status === "approved" && !u.is_active ? "비활성" : STATUS_LABEL[u.approval_status] ?? u.approval_status}</span></td>
                <td style={{ color: "var(--ink-muted)" }}>{u.last_login_at ? fmtDate(u.last_login_at) : "-"}</td>
                <td style={{ textAlign: "right" }}>
                  {u.approval_status === "approved" && (
                    <button className="tbtn" onClick={() => run(() => patchAdminUser(u.id, { is_active: !u.is_active }), u.is_active ? `${u.display_name}님의 계정을 비활성화했습니다` : `${u.display_name}님의 계정을 다시 활성화했습니다`)}>{u.is_active ? "비활성화" : "활성화"}</button>
                  )}
                  {u.approval_status === "rejected" && <button className="tbtn" onClick={() => run(() => approveUser(u.id), `${u.display_name}님의 가입을 승인했습니다`)}>승인</button>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </AppShell>
  );
}
