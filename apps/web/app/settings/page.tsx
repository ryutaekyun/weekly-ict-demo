"use client";

import { useEffect, useState } from "react";
import AppShell from "@/components/AppShell";
import { apiFetch, getCurrentUser, UnauthorizedError, type CurrentUser } from "@/lib/api";
import { ROLE_LABELS } from "@/lib/labels";
import { useRouter } from "next/navigation";

export default function SettingsPage() {
  const router = useRouter();
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    getCurrentUser()
      .then(setUser)
      .catch((err) => { if (err instanceof UnauthorizedError) router.push("/login"); });
  }, [router]);

  async function changePassword(e: React.FormEvent) {
    e.preventDefault();
    setMsg(null);
    setSubmitting(true);
    try {
      await apiFetch("/auth/password", {
        method: "PATCH",
        body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
      });
      setMsg("비밀번호가 변경되었습니다");
      setCurrentPassword("");
      setNewPassword("");
    } catch (err) {
      setMsg(err instanceof Error ? err.message : "비밀번호 변경 실패");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AppShell>
      <h1 style={{ fontSize: 20, fontWeight: 700, marginBottom: 16 }}>사용자 및 운영 설정</h1>

      {user && (
        <section className="panel" style={{ marginBottom: 16 }}>
          <h2 style={{ fontSize: 14, margin: "0 0 10px" }}>내 계정 정보</h2>
          <table style={{ fontSize: 13 }}>
            <tbody>
              <tr><td style={{ padding: "4px 12px 4px 0", color: "var(--ink-muted)" }}>이름</td><td>{user.display_name}</td></tr>
              <tr><td style={{ padding: "4px 12px 4px 0", color: "var(--ink-muted)" }}>이메일</td><td>{user.email}</td></tr>
              <tr><td style={{ padding: "4px 12px 4px 0", color: "var(--ink-muted)" }}>역할</td><td>{ROLE_LABELS[user.role] ?? user.role}</td></tr>
              <tr><td style={{ padding: "4px 12px 4px 0", color: "var(--ink-muted)" }}>직함</td><td>{user.job_title ?? "-"}</td></tr>
            </tbody>
          </table>
        </section>
      )}

      <section className="panel" style={{ marginBottom: 16 }}>
        <h2 style={{ fontSize: 14, margin: "0 0 10px" }}>비밀번호 변경</h2>
        <form onSubmit={changePassword} style={{ display: "flex", flexDirection: "column", gap: 8, maxWidth: 320 }}>
          <input type="password" required placeholder="현재 비밀번호" value={currentPassword} onChange={(e) => setCurrentPassword(e.target.value)} style={inp} />
          <input type="password" required placeholder="새 비밀번호" value={newPassword} onChange={(e) => setNewPassword(e.target.value)} style={inp} />
          <button className="tbtn primary" type="submit" disabled={submitting} style={{ alignSelf: "flex-start" }}>변경</button>
          {msg && <span style={{ fontSize: 12.5, color: msg.includes("변경되었습니다") ? "var(--ok)" : "var(--bad)" }}>{msg}</span>}
        </form>
      </section>

      <section className="panel">
        <h2 style={{ fontSize: 14, margin: "0 0 10px" }}>추후 개발 예정 메뉴</h2>
        <p style={{ fontSize: 13, color: "var(--ink-muted)", margin: 0 }}>
          보고서 집필, 카드뉴스 생성, 주간기술동향지 제작·발간 관리는 Phase 3에서 순차적으로 개발됩니다.
          이번 단계(Phase 2-4)는 수집·분석·후보추천 기능을 실제 웹사이트에서 사용할 수 있도록 하는 데 집중했습니다.
        </p>
      </section>
    </AppShell>
  );
}

const inp: React.CSSProperties = { padding: 9, borderRadius: 8, border: "1px solid var(--border)", fontSize: 13 };
