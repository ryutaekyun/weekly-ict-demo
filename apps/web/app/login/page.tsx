"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { apiFetch, saveToken } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const res = await apiFetch<{ access_token: string }>("/auth/login", {
        method: "POST",
        body: JSON.stringify({ email, password }),
      });
      saveToken(res.access_token);
      router.push("/candidates");
    } catch (err) {
      setError(err instanceof Error ? err.message : "로그인에 실패했습니다");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center" }}>
      <form
        onSubmit={handleSubmit}
        className="panel"
        style={{ width: 360, display: "flex", flexDirection: "column", gap: 14 }}
      >
        <h1 style={{ fontSize: 19, fontWeight: 700, margin: 0 }}>TNP AI Platform</h1>
        <p style={{ color: "var(--ink-muted)", fontSize: 13.5, margin: 0 }}>내부 연구원 전용 — 로그인이 필요합니다</p>
        <label style={{ fontSize: 13, fontWeight: 700 }}>
          이메일
          <input
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            style={{ display: "block", width: "100%", marginTop: 6, padding: 9, borderRadius: 8, border: "1px solid var(--border)" }}
          />
        </label>
        <label style={{ fontSize: 13, fontWeight: 700 }}>
          비밀번호
          <input
            type="password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            style={{ display: "block", width: "100%", marginTop: 6, padding: 9, borderRadius: 8, border: "1px solid var(--border)" }}
          />
        </label>
        {error && <div style={{ color: "var(--bad)", fontSize: 13 }}>{error}</div>}
        <button type="submit" className="tbtn primary" disabled={loading}>
          {loading ? "로그인 중..." : "로그인"}
        </button>
      </form>
    </div>
  );
}
