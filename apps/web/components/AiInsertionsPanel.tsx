"use client";

import { useState } from "react";
import { aiReviewInsertion, aiUndoInsertion, type AiInsertionRow } from "@/lib/aiApi";

const RESOLUTIONS: { key: "updated" | "no_impact" | "needs_check" | "removed"; label: string }[] = [
  { key: "updated", label: "① 수정 반영 완료" },
  { key: "no_impact", label: "② 내용에 영향 없음(사유 기록)" },
  { key: "needs_check", label: "③ 추가 확인 필요" },
  { key: "removed", label: "④ 해당 문장 삭제·대체" },
];
const box: React.CSSProperties = { border: "1px solid var(--border)", borderRadius: 10, padding: 10, marginBottom: 8, background: "var(--panel)", fontSize: 13 };

/** 원고에 삽입된 AI 문장 목록 — 근거 원문이 바뀌면 '원문 변경·재검토 필요'와 변경 전후를 보여주고 연구원이 판단을 기록한다. */
export default function AiInsertionsPanel({ rows, getLockVersion, onChanged }: { rows: AiInsertionRow[]; getLockVersion: () => Promise<number>; onChanged: () => void }) {
  const [res, setRes] = useState<Record<string, string>>({});
  const [note, setNote] = useState<Record<string, string>>({});
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  async function review(r: AiInsertionRow) {
    setErr(null); setMsg(null);
    const choice = res[r.id] as "updated" | "no_impact" | "needs_check" | "removed" | undefined;
    if (!choice) { setErr("판단(①~④)을 선택하세요."); return; }
    try {
      await aiReviewInsertion(r.id, choice, note[r.id] ?? "");
      setMsg("재검토 판단을 기록했습니다(검토자·일시·사유·확인한 원문 버전 저장).");
      onChanged();
    } catch (e) { setErr(e instanceof Error ? e.message : "저장 실패"); }
  }

  async function undo(r: AiInsertionRow) {
    setErr(null); setMsg(null);
    try {
      await aiUndoInsertion(r.id, await getLockVersion());
      setMsg("AI 삽입을 취소했습니다(미검증 각주 포함).");
      onChanged();
    } catch (e) { setErr(e instanceof Error ? e.message : "취소 실패"); }
  }

  const active = rows.filter((r) => r.status === "active");
  if (rows.length === 0) return <p style={{ fontSize: 12.5, color: "var(--ink-muted)" }}>이 원고에 삽입된 AI 문장이 없습니다.</p>;
  return (
    <div data-testid="ai-insertions">
      <b style={{ fontSize: 13 }}>삽입된 AI 문장 ({active.length}건 활성)</b>
      {err && <p role="alert" data-testid="ai-insertion-error" style={{ color: "var(--bad)", fontSize: 12.5 }}>{err}</p>}
      {msg && <p role="status" style={{ color: "var(--ok)", fontSize: 12.5 }}>{msg}</p>}
      {rows.map((r) => (
        <div key={r.id} style={{ ...box, borderColor: r.needs_review ? "var(--bad)" : "var(--border)" }} data-testid="ai-insertion" data-needs-review={r.needs_review} data-status={r.status}>
          <div>{r.final_text}</div>
          <div style={{ marginTop: 4 }}>
            <span className="pill hold">AI 제안</span>
            {r.edited_by_researcher && <span className="pill">연구원이 수정함</span>}
            {r.status !== "active" && <span className="pill">{r.status === "undone" ? "삽입 취소됨" : "삭제·대체됨"}</span>}
            {r.needs_review && <span className="pill review" data-testid="ai-needs-review">원문 변경·재검토 필요</span>}
          </div>
          {r.edited_by_researcher && <div style={{ fontSize: 12, color: "var(--ink-muted)", marginTop: 4 }}>AI 원문: {r.ai_text}</div>}
          {r.needs_review && r.change && (
            <div style={{ marginTop: 6, fontSize: 12.5 }} data-testid="ai-change-detail">
              <div><b>삽입 당시 근거 발췌</b>: “{r.change.old_quote}”</div>
              {r.change.old_quote_still_in_source
                ? <div style={{ color: "var(--ink-muted)" }}>인용 문장은 현재 원문에도 그대로 있습니다(원문의 다른 부분이 바뀜).</div>
                : <div><b>현재 원문의 가장 비슷한 문장</b>: {r.change.new_sentence ? `“${r.change.new_sentence}” (유사도 ${r.change.similarity})` : "찾지 못함 — 문장이 삭제됐을 수 있음"}</div>}
              {r.change.removed_facts.length > 0 && <div style={{ color: "var(--bad)" }}>원문에서 사라진 값: {r.change.removed_facts.join(", ")}</div>}
              {r.change.added_facts.length > 0 && <div style={{ color: "var(--ok)" }}>새로 나타난 값: {r.change.added_facts.join(", ")}</div>}
              {r.change.stale_in_sentence.length > 0 && <div role="alert" style={{ color: "var(--bad)" }}>원고 문장에 이전 원문 기준 날짜가 남아 있습니다: {r.change.stale_in_sentence.join(", ")}</div>}
              {r.change.last_review && <div style={{ color: "var(--ink-muted)" }}>직전 판단: {r.change.last_review.resolution} — {r.change.last_review.note}</div>}
              <div style={{ marginTop: 6 }}>
                {RESOLUTIONS.map((o) => (
                  <label key={o.key} style={{ display: "block" }}><input type="radio" name={`res-${r.id}`} checked={res[r.id] === o.key} onChange={() => setRes({ ...res, [r.id]: o.key })} /> {o.label}</label>
                ))}
                <input aria-label="재검토 판단 사유" placeholder="판단 사유(필수)" value={note[r.id] ?? ""} onChange={(e) => setNote({ ...note, [r.id]: e.target.value })}
                  style={{ padding: 7, borderRadius: 8, border: "1px solid var(--border)", width: "100%", margin: "6px 0" }} />
                <button className="tbtn primary" data-testid="ai-insertion-review" onClick={() => review(r)}>판단 기록</button>
              </div>
            </div>
          )}
          {r.history.length > 0 && (
            <details style={{ marginTop: 6, fontSize: 12 }}>
              <summary>재검토 이력 {r.history.length}건</summary>
              {r.history.map((h, i) => <div key={i}>{h.reviewed_at.slice(0, 16).replace("T", " ")} · {h.label} · {h.note} · 확인한 원문 버전 {h.reviewed_source_hash?.slice(0, 8) ?? "-"}</div>)}
            </details>
          )}
          {r.status === "active" && <button className="tbtn" style={{ marginTop: 6 }} data-testid="ai-insertion-undo" onClick={() => undo(r)}>삽입 취소</button>}
        </div>
      ))}
    </div>
  );
}
