"use client";

import { Suspense, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import AuthFrame from "@/components/AuthFrame";
import { registerUser } from "@/lib/api";

function RegisterForm() {
  const invite = useSearchParams().get("invite") ?? undefined;
  const [form, setForm] = useState({ email: "", display_name: "", job_title: "", password: "", password2: "" });
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<{ status: string; message: string } | null>(null);
  const [loading, setLoading] = useState(false);
  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, [k]: e.target.value });

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (form.password !== form.password2) { setError("비밀번호 확인이 일치하지 않습니다"); return; }
    setLoading(true);
    try {
      setDone(await registerUser({ email: form.email, display_name: form.display_name, job_title: form.job_title || undefined, password: form.password, invite_token: invite }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "가입에 실패했습니다");
    } finally {
      setLoading(false);
    }
  }

  if (done) {
    return (
      <AuthFrame title={done.status === "approved" ? "가입 완료" : "가입 신청 완료"} subtitle="">
        <div role="status" data-testid="register-done" className={`notice ${done.status === "approved" ? "ok" : "info"}`}>{done.message}</div>
        <p style={{ textAlign: "center", marginTop: 18 }}><Link href="/login" className="tbtn primary">로그인 화면으로</Link></p>
      </AuthFrame>
    );
  }

  return (
    <AuthFrame title="회원가입" subtitle={invite ? "관리자 초대 링크로 가입합니다. 초대받은 이메일 주소를 입력하세요." : "가입 후 관리자 승인이 완료되면 로그인할 수 있습니다."}>
      <form onSubmit={submit}>
        <label className="field">이름<input required minLength={2} maxLength={100} autoComplete="name" value={form.display_name} onChange={set("display_name")} /></label>
        <label className="field">이메일<input type="email" required autoComplete="email" value={form.email} onChange={set("email")} /></label>
        <label className="field">직함(선택)<input maxLength={100} value={form.job_title} onChange={set("job_title")} /></label>
        <label className="field">비밀번호<input type="password" required minLength={10} autoComplete="new-password" value={form.password} onChange={set("password")} />
          <span style={{ fontWeight: 400, fontSize: 12, color: "var(--ink-muted)" }}>10자 이상, 영문과 숫자를 모두 포함</span></label>
        <label className="field">비밀번호 확인<input type="password" required autoComplete="new-password" value={form.password2} onChange={set("password2")} /></label>
        {error && <div role="alert" className="notice err" style={{ marginBottom: 12 }}>{error}</div>}
        <button type="submit" className="tbtn primary" disabled={loading} style={{ width: "100%", padding: 11 }}>{loading ? "처리 중..." : "가입 신청"}</button>
      </form>
      <p style={{ fontSize: 13, textAlign: "center", margin: "16px 0 0" }}>이미 계정이 있으신가요? <Link href="/login">로그인</Link></p>
    </AuthFrame>
  );
}

export default function RegisterPage() {
  return (
    <Suspense fallback={null}>
      <RegisterForm />
    </Suspense>
  );
}
