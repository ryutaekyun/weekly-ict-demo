"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import AppShell from "@/components/AppShell";
import { getCurrentUser, type CurrentUser } from "@/lib/api";
import { pCommissions, pManuscripts, pReviews, type PCommission, type PReview } from "@/lib/journalApi";

export default function PortalHome() {
  const [me, setMe] = useState<CurrentUser | null>(null);
  const [commissions, setCommissions] = useState<PCommission[]>([]);
  const [manuscripts, setManuscripts] = useState<{ id: string; title: string; issue_label: string; status_label: string; version_count: number }[]>([]);
  const [reviews, setReviews] = useState<PReview[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getCurrentUser().then(async (u) => {
      setMe(u);
      try {
        if (u.role === "author") { setCommissions(await pCommissions()); setManuscripts(await pManuscripts()); }
        else if (u.role === "reviewer" || u.role === "ext_reviewer") setReviews(await pReviews());
      } catch (e) { setError(e instanceof Error ? e.message : "불러오기 실패"); }
    }).catch(() => undefined);
  }, []);

  return (
    <AppShell>
      <h1 style={{ fontSize: 20, fontWeight: 700, marginBottom: 4 }}>{me?.role === "author" ? "원고 집필 포털" : "원고 검토 포털"}</h1>
      <p style={{ color: "var(--ink-muted)", fontSize: 13, marginTop: 0 }}>
        {me?.role === "author" ? "나에게 의뢰된 원고와 제출한 원고만 표시됩니다. 제출한 파일은 덮어쓰지 않고 버전으로 보관됩니다." : "나에게 배정된 원고만 표시됩니다. 검토 의견은 심의 담당자의 참고 의견이며 게재 여부는 심의 담당자가 확정합니다."}
      </p>
      {error && <p role="alert" style={{ color: "#b42318", fontSize: 13 }}>{error}</p>}
      {me && !["author", "reviewer", "ext_reviewer"].includes(me.role) && <p>편집 담당자는 <Link href="/journal">주간기술동향지 편집</Link>을 사용하세요.</p>}

      {me?.role === "author" && (
        <>
          <section className="panel" style={{ marginBottom: 12 }}>
            <b>집필 의뢰</b>
            {commissions.map((c) => (
              <div key={c.id} style={{ borderTop: "1px solid var(--border)", padding: "8px 0", fontSize: 13 }}>
                <Link href={`/portal/commissions/${c.id}`}>{c.topic}</Link> · {c.issue_label} · 제출 기한 {c.due_date ?? "미정"} · <span className="pill hold">{c.status_label}</span>
                {c.manuscript_status && <span> · 원고 상태: {c.manuscript_status}</span>}
              </div>
            ))}
            {commissions.length === 0 && <p style={{ fontSize: 12.5, color: "var(--ink-muted)" }}>의뢰받은 건이 없습니다.</p>}
          </section>
          <section className="panel">
            <b>내 원고</b>
            {manuscripts.map((m) => (
              <div key={m.id} style={{ borderTop: "1px solid var(--border)", padding: "8px 0", fontSize: 13 }}>
                <Link href={`/portal/manuscripts/${m.id}`}>{m.title}</Link> · {m.issue_label} · <span className="pill hold">{m.status_label}</span> · 제출 버전 {m.version_count}건
              </div>
            ))}
            {manuscripts.length === 0 && <p style={{ fontSize: 12.5, color: "var(--ink-muted)" }}>제출한 원고가 없습니다.</p>}
          </section>
        </>
      )}

      {(me?.role === "reviewer" || me?.role === "ext_reviewer") && (
        <section className="panel">
          <b>내 검토 배정</b>
          {reviews.map((r) => (
            <div key={r.id} style={{ borderTop: "1px solid var(--border)", padding: "8px 0", fontSize: 13 }}>
              <Link href={`/portal/reviews/${r.id}`}>{r.title}</Link> · {r.issue_label} · {r.round}차 · 기한 {r.due_date ?? "-"}{r.overdue ? " (지연)" : ""} ·{" "}
              <span className="pill hold">{{ assigned: "배정됨", in_progress: "검토 중", completed: "검토 완료" }[r.status]}</span>
            </div>
          ))}
          {reviews.length === 0 && <p style={{ fontSize: 12.5, color: "var(--ink-muted)" }}>배정된 원고가 없습니다.</p>}
        </section>
      )}
    </AppShell>
  );
}
