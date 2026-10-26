"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import AppShell from "@/components/AppShell";
import { getCurrentUser, type CurrentUser } from "@/lib/api";
import { jDashboard, jPlanYear, type JDash } from "@/lib/journalApi";

const CSTAT: Record<string, string> = { draft: "작성 중", ready: "발송 대기", requested: "의뢰함", accepted: "수락", declined: "거절", no_response: "미응답" };
const MSTAT: Record<string, string> = {
  received: "접수 완료", format_fix_needed: "형식 보완 필요", review_pending: "내용 검토 대기", in_review: "검토 진행 중", revision_requested: "수정 요청",
  revision_received: "수정본 접수", deliberated: "심의 완료", accepted: "게재 확정", held: "게재 보류", rejected: "게재 부적합",
};
const inp: React.CSSProperties = { padding: 8, borderRadius: 8, border: "1px solid var(--border)", fontSize: 13 };

export default function JournalHome() {
  const [me, setMe] = useState<CurrentUser | null>(null);
  const [year, setYear] = useState(2027);
  const [mine, setMine] = useState(false);
  const [dash, setDash] = useState<JDash | null>(null);
  const [status, setStatus] = useState("");
  const [text, setText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const load = useCallback(() => {
    jDashboard(year, mine).then(setDash).catch((e) => setError(e instanceof Error ? e.message : "불러오기 실패"));
  }, [year, mine]);
  useEffect(() => { getCurrentUser().then(setMe).catch(() => undefined); }, []);
  useEffect(() => { load(); }, [load]);

  const issues = useMemo(() => (dash?.issues ?? []).filter((i) => (!status || i.status === status) && (!text || `${i.label} ${i.topic ?? ""} ${i.tech_field ?? ""}`.includes(text))), [dash, status, text]);

  async function plan() {
    setError(null); setMessage(null);
    try {
      const r = await jPlanYear(year, 25);
      setMessage(`${year}년 회차 ${r.created}건을 새로 등록했습니다(전체 ${r.total}건). 발간일은 자동으로 정하지 않았습니다 — 관리자가 실제 발간일을 입력하세요.`);
      load();
    } catch (e) { setError(e instanceof Error ? e.message : "등록 실패"); }
  }

  const cardStyle: React.CSSProperties = { flex: 1, minWidth: 150, textAlign: "center" };
  return (
    <AppShell>
      <h1 style={{ fontSize: 20, fontWeight: 700, marginBottom: 4 }}>주간기술동향지 편집</h1>
      <p style={{ color: "var(--ink-muted)", fontSize: 13, marginTop: 0 }}>
        외부 전문가 원고의 의뢰·접수·검토·저자 수정·심의·교정·발간본 제작을 관리합니다. 날짜·분량·제출서류 기준은 해당 연도 IITP 기준을 확인해 관리자가 설정하며,
        이메일 발송과 IITP 업로드는 이 단계에서 하지 않습니다.
      </p>
      <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", marginBottom: 10 }}>
        <label style={{ fontSize: 13 }}>연도 <input aria-label="연도" type="number" value={year} onChange={(e) => setYear(Number(e.target.value))} style={{ ...inp, width: 90 }} /></label>
        <label style={{ fontSize: 13 }}><input type="checkbox" checked={mine} onChange={(e) => setMine(e.target.checked)} /> 내가 담당하는 회차만</label>
        <button className="tbtn" onClick={plan}>{year}년 연간 25회 계획 등록</button>
        <Link href="/journal/experts" className="tbtn">집필진 DB</Link>
        {me?.role === "admin" && <Link href="/journal/settings" className="tbtn">운영 설정</Link>}
      </div>
      {error && <p role="alert" style={{ color: "#b42318", fontSize: 13 }}>{error}</p>}
      {message && <p role="status" style={{ color: "var(--ok)", fontSize: 13 }}>{message}</p>}

      {dash && (
        <>
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginBottom: 12 }}>
            <div className="panel" style={cardStyle}><div style={{ fontSize: 12 }}>계획 회차</div><b style={{ fontSize: 22 }} data-testid="planned-count">{dash.plan.planned_issues}</b>
              <div style={{ fontSize: 11.5, color: "var(--ink-muted)" }}>발간일 입력 {dash.plan.with_publish_date}건</div></div>
            <div className="panel" style={cardStyle}><div style={{ fontSize: 12 }}>발간 기록</div><b style={{ fontSize: 22 }} data-testid="published-count">{dash.plan.published_records}</b>
              <div style={{ fontSize: 11.5, color: "var(--ink-muted)" }}>IITP 확인 {dash.plan.iitp_confirmed}건</div></div>
            <div className="panel" style={cardStyle}><div style={{ fontSize: 12 }}>집필 의뢰</div>
              <div style={{ fontSize: 12.5 }}>{Object.keys(CSTAT).map((k) => `${CSTAT[k]} ${dash.commission_status[k] ?? 0}`).join(" · ")}</div></div>
            <div className="panel" style={cardStyle}><div style={{ fontSize: 12 }}>검토 배정</div>
              <div style={{ fontSize: 12.5 }}>진행 {dash.review.assigned} · 완료 {dash.review.completed}</div></div>
          </div>
          {dash.unresolved_comments.length > 0 && (
            <div className="panel" role="region" aria-label="미해결 심의의견" style={{ marginBottom: 12, fontSize: 12.5, background: "#FFF4D6" }}>
              <b>미해결 필수 수정 의견</b> — 저자 답변만 있고 해결 확인이 없는 의견입니다.
              {dash.unresolved_comments.map((u) => <div key={u.manuscript_id}><Link href={`/journal/manuscripts/${u.manuscript_id}`}>{u.title}</Link> · {u.count}건</div>)}
            </div>
          )}
          <div className="panel" style={{ marginBottom: 12, fontSize: 12.5 }}>
            <b>원고 현황</b>: {Object.keys(MSTAT).map((k) => `${MSTAT[k]} ${dash.manuscript_status[k] ?? 0}`).join(" · ")}
            <div style={{ color: "var(--ink-muted)", marginTop: 4 }}>{dash.plan.note}</div>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))", gap: 12, marginBottom: 12 }}>
            <div className="panel">
              <b>기한 초과·지연</b> <span className="pill review">{dash.delayed.length}</span>
              {dash.delayed.length === 0 && <p style={{ color: "var(--ink-muted)", fontSize: 12.5 }}>지연된 업무가 없습니다.</p>}
              {dash.delayed.slice(0, 8).map((d, i) => (
                <div key={i} style={{ fontSize: 12.5, marginTop: 4 }}><Link href={`/journal/issues/${d.issue_id}`}>{d.issue_label}</Link> · {d.label} · 마감 {d.due_date} ({-d.days}일 지연)</div>
              ))}
            </div>
            <div className="panel">
              <b>마감 임박</b> <span className="pill hold">{dash.upcoming.length}</span>
              {dash.upcoming.length === 0 && <p style={{ color: "var(--ink-muted)", fontSize: 12.5 }}>임박한 마감이 없습니다.</p>}
              {dash.upcoming.slice(0, 8).map((d, i) => (
                <div key={i} style={{ fontSize: 12.5, marginTop: 4 }}><Link href={`/journal/issues/${d.issue_id}`}>{d.issue_label}</Link> · {d.label} · 마감 {d.due_date} ({d.days}일 남음)</div>
              ))}
            </div>
          </div>
          <div style={{ display: "flex", gap: 8, marginBottom: 8, flexWrap: "wrap" }}>
            <select aria-label="진행 상태 필터" value={status} onChange={(e) => setStatus(e.target.value)} style={inp}>
              <option value="">전체 상태</option>
              {["planning", "recruiting", "receiving", "reviewing", "editing", "iitp_check", "published"].map((s) => <option key={s} value={s}>{{ planning: "기획", recruiting: "집필진 확보", receiving: "원고 접수", reviewing: "검토·심의", editing: "편집·교정", iitp_check: "IITP 확인 대기", published: "발간 기록" }[s]}</option>)}
            </select>
            <input aria-label="회차·주제 검색" placeholder="회차·주제·분야 검색" value={text} onChange={(e) => setText(e.target.value)} style={{ ...inp, minWidth: 220 }} />
          </div>
          <div className="panel" style={{ padding: 0, overflow: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
              <thead><tr style={{ textAlign: "left", background: "var(--panel-2)" }}>
                {["회차", "발간 예정일", "상태", "주제·분야", "의뢰/수락", "원고/게재 확정", "지연", "미해결 의견", "IITP 확인"].map((h) => <th key={h} style={{ padding: "9px 12px" }}>{h}</th>)}
              </tr></thead>
              <tbody>
                {issues.map((i) => (
                  <tr key={i.id} style={{ borderTop: "1px solid var(--border)" }}>
                    <td style={{ padding: "8px 12px" }}><Link href={`/journal/issues/${i.id}`}>{i.label}</Link></td>
                    <td style={{ padding: "8px 12px" }}>{i.publish_date ?? <span style={{ color: "var(--ink-muted)" }}>미정</span>}</td>
                    <td style={{ padding: "8px 12px" }}>{i.status_label}</td>
                    <td style={{ padding: "8px 12px" }}>{i.topic ?? "-"}{i.tech_field ? ` · ${i.tech_field}` : ""}</td>
                    <td style={{ padding: "8px 12px" }}>{i.commissions}/{i.accepted}</td>
                    <td style={{ padding: "8px 12px" }}>{i.manuscripts}/{i.accepted_manuscripts}</td>
                    <td style={{ padding: "8px 12px", color: i.delayed_steps ? "#b42318" : undefined }}>{i.delayed_steps ? `${i.delayed_steps}단계` : "-"}</td>
                    <td style={{ padding: "8px 12px", color: i.unresolved_comments ? "#b42318" : undefined }}>{i.unresolved_comments ? `${i.unresolved_comments}건` : "-"}{i.exception_decisions ? ` (예외 확정 ${i.exception_decisions})` : ""}</td>
                    <td style={{ padding: "8px 12px" }}>{i.iitp_confirmed ? "확인 완료" : "확인 전"}</td>
                  </tr>
                ))}
                {issues.length === 0 && <tr><td colSpan={9} style={{ padding: 14, color: "var(--ink-muted)" }}>등록된 회차가 없습니다. 위의 &lsquo;연간 계획 등록&rsquo;을 눌러 시작하세요.</td></tr>}
              </tbody>
            </table>
          </div>
        </>
      )}
    </AppShell>
  );
}
