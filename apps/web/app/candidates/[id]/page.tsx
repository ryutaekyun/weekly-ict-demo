"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { apiFetch, getToken, type CandidateDetail } from "@/lib/api";

export default function CandidateDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const [candidate, setCandidate] = useState<CandidateDetail | null>(null);
  const [comment, setComment] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  function load() {
    apiFetch<CandidateDetail>(`/candidates/${params.id}`)
      .then(setCandidate)
      .catch((err) => setError(err instanceof Error ? err.message : "불러오기 실패"));
  }

  useEffect(() => {
    if (!getToken()) {
      router.push("/login");
      return;
    }
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params.id, router]);

  async function submitComment(e: React.FormEvent) {
    e.preventDefault();
    if (!comment.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      await apiFetch(`/candidates/${params.id}/reviews`, {
        method: "POST",
        body: JSON.stringify({ comment_text: comment }),
      });
      setComment("");
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "의견 등록 실패");
    } finally {
      setSubmitting(false);
    }
  }

  if (!candidate) return <div style={{ padding: 32 }}>불러오는 중...</div>;

  return (
    <div style={{ maxWidth: 720, margin: "0 auto", padding: 32 }}>
      <h1 style={{ fontSize: 20, fontWeight: 700 }}>{candidate.title}</h1>
      <p style={{ color: "var(--ink-muted)" }}>{candidate.summary}</p>
      <span className={`pill ${candidate.status}`}>{candidate.status}</span>

      <h2 style={{ fontSize: 15, marginTop: 24 }}>검토의견</h2>
      <div style={{ display: "flex", flexDirection: "column", gap: 8, marginBottom: 16 }}>
        {candidate.reviews.map((r) => (
          <div
            key={r.id}
            className="panel"
            style={{ padding: 10, background: r.is_final_approval ? "var(--navy-soft)" : "var(--panel-2)" }}
          >
            <div style={{ fontSize: 12, color: "var(--ink-muted)" }}>
              {r.is_final_approval ? "[최종승인] " : ""}
              {new Date(r.created_at).toLocaleString("ko-KR")}
            </div>
            <div>{r.comment_text}</div>
          </div>
        ))}
        {candidate.reviews.length === 0 && <p style={{ color: "var(--ink-muted)" }}>아직 검토의견이 없습니다</p>}
      </div>

      <form onSubmit={submitComment} style={{ display: "flex", gap: 8 }}>
        <input
          value={comment}
          onChange={(e) => setComment(e.target.value)}
          placeholder="검토 의견을 입력하세요"
          style={{ flex: 1, padding: 9, borderRadius: 8, border: "1px solid var(--border)" }}
        />
        <button className="tbtn primary" type="submit" disabled={submitting}>
          등록
        </button>
      </form>
      {error && <p style={{ color: "var(--bad)" }}>{error}</p>}
    </div>
  );
}
