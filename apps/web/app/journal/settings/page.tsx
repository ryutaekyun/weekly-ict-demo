"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import AppShell from "@/components/AppShell";
import { jPatchSettings, jSettings } from "@/lib/journalApi";

const inp: React.CSSProperties = { padding: 8, borderRadius: 8, border: "1px solid var(--border)", fontSize: 13, minWidth: 0 };

export default function JournalSettingsPage() {
  const [cfg, setCfg] = useState<Record<string, unknown> | null>(null);
  const [holidays, setHolidays] = useState("");
  const [docs, setDocs] = useState("");
  const [wordMin, setWordMin] = useState("");
  const [wordMax, setWordMax] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const apply = (c: Record<string, unknown>) => {
    setCfg(c);
    setHolidays(((c.holidays as string[]) ?? []).join("\n"));
    setDocs(((c.required_docs as { key: string; label: string }[]) ?? []).map((d) => `${d.key}|${d.label}`).join("\n"));
    setWordMin(c.word_min == null ? "" : String(c.word_min));
    setWordMax(c.word_max == null ? "" : String(c.word_max));
  };
  useEffect(() => { jSettings().then(apply).catch((e) => setError(e instanceof Error ? e.message : "불러오기 실패")); }, []);

  async function save(patch: Record<string, unknown>, ok: string) {
    setError(null); setMessage(null);
    try { apply(await jPatchSettings(patch)); setMessage(ok); } catch (e) { setError(e instanceof Error ? e.message : "저장 실패(관리자만 변경할 수 있습니다)"); }
  }
  if (!cfg) return <AppShell>{error ? <p role="alert" style={{ color: "#b42318" }}>{error}</p> : <p>불러오는 중...</p>}</AppShell>;

  return (
    <AppShell>
      <div style={{ marginBottom: 8 }}><Link href="/journal" style={{ fontSize: 13 }}>← 주간기술동향지 편집 대시보드</Link></div>
      <h1 style={{ fontSize: 20, fontWeight: 700, marginBottom: 4 }}>주간기술동향지 운영 설정(관리자)</h1>
      <p style={{ color: "var(--ink-muted)", fontSize: 13, marginTop: 0 }}>
        분량·제출서류·표절률 기준은 해당 연도 IITP 공식 기준을 확인한 뒤 입력합니다. 과거 모집안내의 수치를 확정 요건처럼 미리 넣어 두지 않았습니다(미설정이면 &lsquo;기준 미설정&rsquo;으로 표시).
      </p>
      {error && <p role="alert" style={{ color: "#b42318", fontSize: 13 }}>{error}</p>}
      {message && <p role="status" style={{ color: "var(--ok)", fontSize: 13 }}>{message}</p>}

      <section className="panel" style={{ display: "grid", gap: 8, marginBottom: 12 }}>
        <b>편집 일정 계산</b>
        <label style={{ fontSize: 13 }}>D-n 기준{" "}
          <select aria-label="일정 기준" value={String(cfg.day_basis)} onChange={(e) => save({ day_basis: e.target.value }, "일정 기준을 바꾸고 모든 회차의 마감일을 다시 계산했습니다")} style={inp}>
            <option value="calendar">달력일</option><option value="business">영업일</option>
          </select></label>
        <label style={{ fontSize: 13 }}>휴일·주말에 걸린 마감일{" "}
          <select aria-label="휴일 조정" value={String(cfg.holiday_rule)} onChange={(e) => save({ holiday_rule: e.target.value }, "휴일 조정 방식을 바꿨습니다")} style={inp}>
            <option value="none">조정하지 않음</option><option value="prev">직전 영업일로 앞당김</option><option value="next">다음 영업일로 미룸</option>
          </select></label>
        <label style={{ fontSize: 13 }}>휴일 목록(한 줄에 YYYY-MM-DD)<textarea aria-label="휴일 목록" rows={3} value={holidays} onChange={(e) => setHolidays(e.target.value)} style={{ ...inp, display: "block", width: "100%" }} /></label>
        <div><button className="tbtn" onClick={() => save({ holidays: holidays.split(/\s+/).filter(Boolean) }, "휴일을 저장했습니다")}>휴일 저장</button></div>
      </section>

      <section className="panel" style={{ display: "grid", gap: 8, marginBottom: 12 }}>
        <b>원고 형식 점검 기준</b>
        <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
          <input aria-label="최소 단어 수" placeholder="최소 단어 수(미설정)" value={wordMin} onChange={(e) => setWordMin(e.target.value)} style={inp} />
          <input aria-label="최대 단어 수" placeholder="최대 단어 수(미설정)" value={wordMax} onChange={(e) => setWordMax(e.target.value)} style={inp} />
          <button className="tbtn" onClick={() => save({ ...(wordMin ? { word_min: Number(wordMin) } : {}), ...(wordMax ? { word_max: Number(wordMax) } : {}), clear: [...(wordMin ? [] : ["word_min"]), ...(wordMax ? [] : ["word_max"])] }, "분량 기준을 저장했습니다")}>분량 기준 저장</button>
        </div>
        <label style={{ fontSize: 13 }}>필수 제출서류(한 줄에 `키|이름`)<textarea aria-label="필수 제출서류" rows={3} value={docs} onChange={(e) => setDocs(e.target.value)} style={{ ...inp, display: "block", width: "100%" }} /></label>
        <div><button className="tbtn" onClick={() => save({ required_docs: docs.split("\n").map((l) => l.trim()).filter(Boolean).map((l) => { const [key, ...rest] = l.split("|"); return { key: key.trim(), label: (rest.join("|") || key).trim() }; }) }, "제출서류 기준을 저장했습니다")}>제출서류 저장</button></div>
      </section>

      <section className="panel" style={{ fontSize: 13 }}>
        <b>심의 결과 구분</b>
        <ul>{((cfg.decision_outcomes as { key: string; label: string; effect: string }[]) ?? []).map((o) => <li key={o.key}>{o.label} <span style={{ color: "var(--ink-muted)" }}>({o.key} → {o.effect})</span></li>)}</ul>
        <div style={{ color: "var(--ink-muted)" }}>업로드 제한 {String(cfg.max_upload_mb)}MB · 대폭 수정 판단 비율 {String(cfg.major_change_ratio)} · 개인정보 보존 기간 {cfg.retention_months ? `${cfg.retention_months}개월` : "미설정"}</div>
      </section>
    </AppShell>
  );
}
