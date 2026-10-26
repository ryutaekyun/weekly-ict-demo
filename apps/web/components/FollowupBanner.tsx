"use client";

import { useCallback, useEffect, useState } from "react";
import { ackFollowup, followupsFor, type FollowupEntity, type FollowupNotice } from "@/lib/followupApi";

/** 후속 규정 발견·재검토 필요 배너 — 근거 원문을 바꾸는 후속 공식 문서가 등록된 산출물에만 표시된다.
 *  내용·검증 상태는 자동으로 바뀌지 않으며, 연구원이 수정(또는 영향 없음 확인) 후 사유와 함께 확인해야 사라진다. */
export default function FollowupBanner({ entityType, entityId, canAck, onChanged }: {
  entityType: FollowupEntity; entityId: string; canAck: boolean; onChanged?: () => void;
}) {
  const [open, setOpen] = useState<FollowupNotice[]>([]);
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    followupsFor(entityType, entityId).then((r) => setOpen(r.open)).catch(() => setOpen([]));
  }, [entityType, entityId]);
  useEffect(() => { load(); }, [load]);

  async function ack(n: FollowupNotice, resolution: "updated" | "no_change") {
    const note = (notes[n.id] ?? "").trim();
    if (note.length < 3) { setError("확인 사유를 3자 이상 입력하세요"); return; }
    setError(null);
    try {
      await ackFollowup(n.id, { entity_type: entityType, entity_id: entityId, resolution, note });
      setNotes((s) => ({ ...s, [n.id]: "" }));
      load();
      onChanged?.();
    } catch (e) {
      setError(e instanceof Error ? e.message : "확인 처리에 실패했습니다");
    }
  }

  if (!open.length) return null;
  return (
    <div role="region" aria-label="후속 규정 발견·재검토 필요" className="panel" style={{ background: "#FFF4D6", border: "1px solid #E5C77A", marginBottom: 10, fontSize: 13 }}>
      <b>후속 규정 발견 · 재검토 필요</b>
      <span style={{ marginLeft: 6, color: "#6B5200" }}>— 근거로 쓰인 원문을 바꾸는 후속 문서가 있습니다. 내용과 검증 상태는 자동으로 바뀌지 않았습니다.</span>
      {open.map((n) => (
        <div key={n.id} style={{ marginTop: 8, paddingTop: 8, borderTop: "1px solid #E5C77A" }}>
          <div style={{ fontWeight: 600 }}>{n.title}</div>
          <div style={{ margin: "2px 0" }}>{n.change_summary}</div>
          {n.changes.map((c, i) => (
            <div key={i} style={{ fontSize: 12.5 }}>· {c.item}: <s>{c.old}</s> → <b>{c.new}</b></div>
          ))}
          <div style={{ fontSize: 12.5, margin: "2px 0" }}>
            후속 문서: <a href={n.followup_url} target="_blank" rel="noreferrer">{n.followup_org ?? ""} {n.followup_doc_number ?? n.followup_url}</a>
            {n.followup_effective_on ? ` · 시행일 ${n.followup_effective_on}` : ""}
          </div>
          {canAck ? (
            <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap", marginTop: 4 }}>
              <input aria-label={`확인 사유 ${n.followup_doc_number ?? n.id}`} placeholder="수정한 내용 또는 영향 없음 사유" value={notes[n.id] ?? ""}
                onChange={(e) => { const v = e.target.value; setNotes((s) => ({ ...s, [n.id]: v })); }}
                style={{ flex: 1, minWidth: 220, padding: 6, borderRadius: 8, border: "1px solid var(--border)" }} />
              <button className="tbtn" onClick={() => ack(n, "updated")}>수정 반영 확인</button>
              <button className="tbtn" onClick={() => ack(n, "no_change")}>영향 없음 확인</button>
            </div>
          ) : (
            <div style={{ fontSize: 12.5, color: "#6B5200" }}>작성자 또는 검토자 이상만 확인할 수 있습니다.</div>
          )}
        </div>
      ))}
      {error && <p role="alert" style={{ color: "#b42318", margin: "6px 0 0" }}>{error}</p>}
    </div>
  );
}
