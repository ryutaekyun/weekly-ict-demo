"use client";

import { Suspense, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import AuthFrame from "@/components/AuthFrame";
import { apiFetch, getCurrentUser } from "@/lib/api";

function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await apiFetch("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) });
      const next = searchParams.get("next");
      const me = await getCurrentUser();
      const external = me.role === "author" || me.role === "ext_reviewer"; // 외부 전문가는 원고 포털만 사용한다
      const fallback = external ? "/portal" : "/dashboard";
      router.push(next && next.startsWith("/") && (!external || next.startsWith("/portal")) ? next : fallback);
    } catch (err) {
      setError(err instanceof Error ? err.message : "로그인에 실패했습니다");
    } finally {
      setLoading(false);
    }
  }

  return (
    <AuthFrame title="로그인" subtitle="연구원 계정으로 로그인하세요.">
      <form onSubmit={handleSubmit}>
        <label className="field">이메일<input type="email" required autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} /></label>
        <label className="field">비밀번호<input type="password" required autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} /></label>
        {error && <div role="alert" className="notice err" style={{ marginBottom: 12 }}>{error}</div>}
        <button type="submit" className="tbtn primary" disabled={loading} style={{ width: "100%", padding: 11 }}>{loading ? "로그인 중..." : "로그인"}</button>
      </form>
      <p style={{ fontSize: 13, textAlign: "center", margin: "16px 0 0" }}>계정이 없으신가요? <Link href="/register">회원가입</Link></p>
    </AuthFrame>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={null}>
      <LoginForm />
    </Suspense>
  );
}
