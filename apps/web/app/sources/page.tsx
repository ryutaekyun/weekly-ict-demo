"use client";

import { useEffect, useState } from "react";
import AppShell from "@/components/AppShell";
import { listSourceRuns, listSources, triggerCollection, UnauthorizedError, type CollectionRunOut, type SourceOut } from "@/lib/api";
import { FIELD_LABELS, fmtDate } from "@/lib/labels";
import { useRouter } from "next/navigation";

export default function SourcesPage() {
  const router = useRouter();
  const [sources, setSources] = useState<SourceOut[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [fieldCode, setFieldCode] = useState("");
  const [expanded, setExpanded] = useState<string | null>(null);
  const [runs, setRuns] = useState<CollectionRunOut[]>([]);
  const [collecting, setCollecting] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  function load() {
    setLoading(true);
    listSources({ field_code: fieldCode || undefined })
      .then(setSources)
      .catch((err) => {
        if (err instanceof UnauthorizedError) { router.push("/login"); return; }
        setError(err instanceof Error ? err.message : "불러오기 실패");
      })
      .finally(() => setLoading(false));
  }

  useEffect(load, [fieldCode]); // eslint-disable-line react-hooks/exhaustive-deps

  async function toggleRuns(sourceId: string) {
    if (expanded === sourceId) { setExpanded(null); return; }
    setExpanded(sourceId);
    try {
      setRuns(await listSourceRuns(sourceId));
    } catch (err) {
      setRuns([]);
    }
  }

  async function handleCollect(sourceId: string) {
    setCollecting(sourceId);
    setMsg(null);
    try {
      const run = await triggerCollection(sourceId);
      setMsg(`수집 완료: 신규 ${run.items_new}건 · 중복 ${run.items_duplicate}건 · 개정 ${run.items_updated}건 (상태: ${run.status})`);
      load();
      if (expanded === sourceId) setRuns(await listSourceRuns(sourceId));
    } catch (err) {
      setMsg(err instanceof Error ? `수집 실패: ${err.message}` : "수집 실패");
    } finally {
      setCollecting(null);
    }
  }

  return (
    <AppShell>
      <h1 style={{ fontSize: 20, fontWeight: 700, marginBottom: 4 }}>출처·수집 관리</h1>
      <p style={{ color: "var(--ink-muted)", fontSize: 13, marginTop: 0 }}>
        등록된 출처의 상태를 확인하고, 관리자·검토자·승인자 권한으로 수동 수집을 실행할 수 있습니다.
      </p>

      <div className="panel" style={{ display: "flex", gap: 10, marginBottom: 14, alignItems: "center" }}>
        <select value={fieldCode} onChange={(e) => setFieldCode(e.target.value)} style={selectStyle}>
          <option value="">전체 분야</option>
          {Object.entries(FIELD_LABELS).map(([c, l]) => <option key={c} value={c}>{l}</option>)}
        </select>
        <span style={{ marginLeft: "auto", fontSize: 13, color: "var(--ink-muted)" }}>총 {sources.length}곳</span>
      </div>

      {msg && <p style={{ fontSize: 13, color: msg.includes("실패") ? "var(--bad)" : "var(--ok)" }}>{msg}</p>}
      {error && <p style={{ color: "var(--bad)" }}>{error}</p>}
      {loading && <p style={{ color: "var(--ink-muted)" }}>불러오는 중...</p>}

      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        {sources.map((s) => (
          <div key={s.id} className="panel">
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
              <div>
                <div style={{ fontWeight: 700, fontSize: 14 }}>
                  {s.name}
                  {s.needs_review && <span className="pill hold" style={{ marginLeft: 8 }}>관리자 확인 필요</span>}
                  {!s.is_active && <span className="pill" style={{ marginLeft: 8, background: "var(--idle-soft)", color: "var(--idle)" }}>비활성</span>}
                </div>
                <div style={{ fontSize: 12.5, color: "var(--ink-muted)" }}>
                  {s.org_name} · {FIELD_LABELS[s.field_code] ?? s.field_code} · {s.country_code ?? "-"} · {s.source_type.toUpperCase()}
                </div>
                <div style={{ fontSize: 12, color: "var(--ink-muted)" }}>
                  최근 성공 수집: {fmtDate(s.last_successful_collection_at)} · 연속 실패 {s.consecutive_failures}회
                </div>
              </div>
              <div style={{ display: "flex", gap: 8 }}>
                <button className="tbtn" onClick={() => toggleRuns(s.id)}>{expanded === s.id ? "이력 접기" : "수집 이력"}</button>
                <button className="tbtn primary" disabled={!s.is_active || collecting === s.id} onClick={() => handleCollect(s.id)}>
                  {collecting === s.id ? "수집 중..." : "수동 수집 실행"}
                </button>
              </div>
            </div>
            {expanded === s.id && (
              <table style={{ width: "100%", fontSize: 12.5, borderCollapse: "collapse", marginTop: 10 }}>
                <thead>
                  <tr style={{ textAlign: "left", background: "var(--panel-2)" }}>
                    <th style={{ padding: 6 }}>시작</th><th style={{ padding: 6 }}>상태</th><th style={{ padding: 6 }}>신규</th><th style={{ padding: 6 }}>중복</th><th style={{ padding: 6 }}>개정</th><th style={{ padding: 6 }}>오류</th>
                  </tr>
                </thead>
                <tbody>
                  {runs.map((r) => (
                    <tr key={r.id} style={{ borderTop: "1px solid var(--border)" }}>
                      <td style={{ padding: 6 }}>{fmtDate(r.started_at)}</td>
                      <td style={{ padding: 6 }}>{r.status}</td>
                      <td style={{ padding: 6 }}>{r.items_new}</td>
                      <td style={{ padding: 6 }}>{r.items_duplicate}</td>
                      <td style={{ padding: 6 }}>{r.items_updated}</td>
                      <td style={{ padding: 6, color: "var(--bad)" }}>{r.error_message ?? "-"}</td>
                    </tr>
                  ))}
                  {runs.length === 0 && <tr><td colSpan={6} style={{ padding: 10, textAlign: "center", color: "var(--ink-muted)" }}>수집 이력이 없습니다</td></tr>}
                </tbody>
              </table>
            )}
          </div>
        ))}
        {!loading && sources.length === 0 && <p style={{ color: "var(--ink-muted)", fontSize: 13 }}>등록된 출처가 없습니다</p>}
      </div>
    </AppShell>
  );
}

const selectStyle: React.CSSProperties = { padding: "7px 9px", borderRadius: 8, border: "1px solid var(--border)", fontSize: 13 };
