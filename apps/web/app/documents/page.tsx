"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import AppShell from "@/components/AppShell";
import OriginalLink from "@/components/OriginalLink";
import { createCandidate, getCollectionStatus, getCurrentUser, getDocumentFacets, listDocuments, runAllCollection, type CollectionStatus, type DocumentFacets, type DocumentListItem } from "@/lib/api";
import { fmtDate } from "@/lib/labels";
import {
  CANDIDATE_STATUS_LABELS,
  DOCUMENT_TYPE_LABELS,
  EXTRACTION_STATUS_LABELS,
  FIELD_LABELS,
  RELEVANCE_LABELS,
  VALUE_RATING_LABELS,
  fmtDateOnly,
} from "@/lib/labels";

const PAGE_SIZES = [20, 50, 100, 300];
const LANG_LABELS: Record<string, string> = { en: "영어", ko: "한국어", ja: "일본어", zh: "중국어", und: "미상" };
const SORTS: Record<string, string> = { published_desc: "발표일 최신순", published_asc: "발표일 오래된순", title: "제목순", collected_desc: "수집일 최신순" };
// URL 검색 조건 이름 — 상세 화면에서 뒤로 돌아와도 같은 조건으로 다시 조회된다
const KEYS = ["field_code", "country_code", "source_id", "document_type", "relevance", "extraction_status", "has_full_text", "has_issue", "has_candidate", "candidate_status",
  "published_after", "published_before", "sort", "q", "language"] as const;
type Key = (typeof KEYS)[number];

function DocumentsList() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [filters, setFilters] = useState<Record<Key, string>>(() =>
    Object.fromEntries(KEYS.map((k) => [k, searchParams.get(k) ?? (k === "sort" ? "published_desc" : "")])) as Record<Key, string>);
  const [q, setQ] = useState(searchParams.get("q") ?? "");
  const [page, setPage] = useState(Number(searchParams.get("page") ?? 1));
  const [pageSize, setPageSize] = useState(Number(searchParams.get("page_size") ?? 20));
  const [facets, setFacets] = useState<DocumentFacets | null>(null);
  const [items, setItems] = useState<DocumentListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<CollectionStatus | null>(null);
  const [role, setRole] = useState("");
  const [note, setNote] = useState<{ kind: "ok" | "err"; text: string; href?: string } | null>(null);
  const [collecting, setCollecting] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);
  const canRun = ["admin", "source_admin", "approver", "reviewer"].includes(role);

  const refreshStatus = () => getCollectionStatus().then(setStatus).catch(() => undefined);
  useEffect(() => { getCurrentUser().then((u) => setRole(u.role)).catch(() => undefined); refreshStatus(); }, []);

  // '지금 수집' — 서버가 활성 정보원을 수집하는 동안 실제 작업 상태를 조회하고, 끝나면 목록을 다시 불러온다
  async function collectNow() {
    setNote(null);
    setCollecting(true);
    try {
      const r = await runAllCollection();
      setNote({ kind: "ok", text: r.started > 0 ? `${r.started}개 정보원의 수집을 시작했습니다. 완료되면 목록이 갱신됩니다.` : "이미 진행 중인 수집이 있습니다." });
      for (let i = 0; i < 600; i++) {
        const s = await getCollectionStatus();
        setStatus(s);
        if (s.running_jobs.length === 0) break;
        await new Promise((res) => setTimeout(res, 2000));
      }
      setReloadKey((k) => k + 1);
      setNote({ kind: "ok", text: "수집이 끝났습니다. 신규 자료가 목록에 반영되었습니다." });
    } catch (err) {
      setNote({ kind: "err", text: err instanceof Error ? err.message : "수집을 시작하지 못했습니다" });
    } finally { setCollecting(false); }
  }

  async function registerCandidate(d: DocumentListItem) {
    setNote(null);
    try {
      const c = await createCandidate({ field_code: d.primary_field_code ?? "ai", title: d.title, source_document_id: d.id, recommended_reason: "ICT 정보수집 화면에서 연구원이 직접 등록(내부 후보, IITP 공식 선정 아님)" });
      setNote({ kind: "ok", text: `후보주제로 등록했습니다: ${c.title}`, href: `/candidates/${c.id}` });
    } catch (err) { setNote({ kind: "err", text: err instanceof Error ? err.message : "후보 등록 실패" }); }
  }

  useEffect(() => { getDocumentFacets().then(setFacets).catch(() => undefined); }, []);
  useEffect(() => {
    setLoading(true);
    setError(null);
    const params: Record<string, string | number> = { page, page_size: pageSize };
    KEYS.forEach((k) => { if (filters[k]) params[k] = k === "published_after" ? `${filters[k]}T00:00:00` : k === "published_before" ? `${filters[k]}T23:59:59` : filters[k]; });
    let stale = false; // 먼저 보낸 요청의 응답이 늦게 도착해 최신 조건의 목록을 덮어쓰지 않도록 한다
    listDocuments(params)
      .then((res) => { if (!stale) { setItems(res.items); setTotal(res.total); } })
      .catch((err) => { if (!stale) setError(err instanceof Error ? err.message : "불러오기 실패"); })
      .finally(() => { if (!stale) setLoading(false); });
    return () => { stale = true; };
  }, [filters, page, pageSize, reloadKey]);

  function apply(next: Partial<Record<Key, string>>, extra: { page?: number; pageSize?: number } = {}) {
    const merged = { ...filters, ...next };
    const nextPage = extra.page ?? 1;
    const nextSize = extra.pageSize ?? pageSize;
    setFilters(merged);
    setPage(nextPage);
    setPageSize(nextSize);
    const params = new URLSearchParams();
    KEYS.forEach((k) => { if (merged[k] && !(k === "sort" && merged[k] === "published_desc")) params.set(k, merged[k]); });
    params.set("page", String(nextPage));
    params.set("page_size", String(nextSize));
    router.replace(`/documents?${params.toString()}`, { scroll: false });
  }

  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const activeFilterCount = KEYS.filter((k) => filters[k] && k !== "sort").length;
  const fieldLabel = filters.field_code ? FIELD_LABELS[filters.field_code] : null;
  const sel = (k: Key, label: string, options: [string, string][]) => (
    <select aria-label={label} value={filters[k]} onChange={(e) => apply({ [k]: e.target.value })} style={selectStyle}>
      <option value="">{label}</option>
      {options.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
    </select>
  );

  return (
    <AppShell>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, flexWrap: "wrap", marginBottom: 14 }}>
        <div>
          <h1 style={{ fontSize: 22, fontWeight: 700, margin: 0 }}>ICT 정보 수집</h1>
          <p style={{ color: "var(--ink-muted)", fontSize: 13, margin: "4px 0 0" }}>제목을 누르면 공식 원문이 새 탭에서 열리고, &lsquo;상세 분석&rsquo;은 분류·전문·이슈 화면으로 이동합니다.</p>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button className="tbtn" onClick={() => { setReloadKey((k) => k + 1); refreshStatus(); }} data-testid="refresh">새로고침</button>
          {canRun && <button className="tbtn primary" onClick={collectNow} disabled={collecting} data-testid="collect-all">{collecting ? "수집 중..." : "지금 수집"}</button>}
        </div>
      </div>
      {status && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, minmax(0, 1fr))", gap: 12, marginBottom: 14 }} data-testid="collection-status">
          <div className="kpi"><div className="l">최근 수집 시각</div><div style={{ fontSize: 15, fontWeight: 700, marginTop: 6 }}>{status.last_collected_at ? fmtDate(status.last_collected_at) : "수집 이력 없음"}</div></div>
          <div className="kpi"><div className="l">최근 24시간 신규 자료</div><div className="v" data-testid="status-new">{status.new_last_24h}</div></div>
          <div className="kpi"><div className="l">검토할 자료(7일)</div><div className="v">{status.to_review}</div></div>
          <div className="kpi"><div className="l">실패한 정보원</div><div className="v" style={status.failed_sources > 0 ? { color: "var(--warn)" } : undefined}>{status.failed_sources}</div></div>
        </div>
      )}
      {note && <div role={note.kind === "err" ? "alert" : "status"} className={`notice ${note.kind}`} style={{ marginBottom: 12 }} data-testid="doc-note">{note.text}{note.href && <> · <Link href={note.href}>후보주제 열기</Link></>}</div>}

      <div className="panel" style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 10, alignItems: "center" }}>
        {sel("field_code", "전체 분야", Object.entries(FIELD_LABELS))}
        {sel("country_code", "전체 국가·지역", (facets?.countries ?? []).map((c) => [c.code, `${c.code} (${c.count})`]))}
        {sel("source_id", "전체 발행기관", (facets?.sources ?? []).map((s) => [s.id, `${s.name} (${s.count})`]))}
        {sel("document_type", "전체 자료유형", Object.entries(DOCUMENT_TYPE_LABELS))}
        {sel("relevance", "전체 검토상태", Object.entries(RELEVANCE_LABELS))}
        {sel("has_full_text", "원문 확보 여부", [["true", "원문(전문) 확보"], ["false", "원문 미확보"]])}
        {sel("extraction_status", "전문 추출 상태", Object.entries(EXTRACTION_STATUS_LABELS))}
        {sel("has_issue", "이슈 연결", [["true", "이슈에 연결됨"], ["false", "이슈 미연결"]])}
        {sel("has_candidate", "후보주제 연결", [["true", "후보주제 있음"], ["false", "후보주제 없음"]])}
        {sel("candidate_status", "후보 검토 상태", Object.entries(CANDIDATE_STATUS_LABELS))}
        {sel("language", "원문 언어", (facets?.languages ?? []).map((l) => [l.code, `${LANG_LABELS[l.code] ?? l.code} (${l.count})`]))}
      </div>
      <div className="panel" style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 14, alignItems: "center" }}>
        <label style={{ fontSize: 13 }}>발표일{" "}
          <input aria-label="발표일 시작" type="date" value={filters.published_after} onChange={(e) => apply({ published_after: e.target.value })} style={selectStyle} />
          {" ~ "}<input aria-label="발표일 끝" type="date" value={filters.published_before} onChange={(e) => apply({ published_before: e.target.value })} style={selectStyle} /></label>
        <input aria-label="제목·본문 검색어" value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") apply({ q }); }}
          placeholder="제목·원문 키워드 검색" style={{ ...selectStyle, minWidth: 220 }} />
        <button className="tbtn" onClick={() => apply({ q })}>검색</button>
        <select aria-label="정렬" value={filters.sort} onChange={(e) => apply({ sort: e.target.value })} style={selectStyle}>
          {Object.entries(SORTS).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
        </select>
        <select aria-label="페이지 크기" value={pageSize} onChange={(e) => apply({}, { pageSize: Number(e.target.value) })} style={selectStyle}>
          {PAGE_SIZES.map((n) => <option key={n} value={n}>{n}건씩 보기</option>)}
        </select>
        {activeFilterCount > 0 && <button className="tbtn" onClick={() => { setQ(""); apply(Object.fromEntries(KEYS.map((k) => [k, k === "sort" ? filters.sort : ""]))); }}>조건 초기화</button>}
        <span style={{ marginLeft: "auto", fontSize: 13, color: "var(--ink-muted)" }} data-testid="result-count">총 {total}건</span>
      </div>

      {error && <p role="alert" style={{ color: "var(--bad)" }}>{error}</p>}
      {loading && <p style={{ color: "var(--ink-muted)" }}>불러오는 중...</p>}

      <div className="panel" style={{ padding: 0, overflow: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
          <thead>
            <tr style={{ textAlign: "left", background: "var(--panel-2)" }}>
              <th style={th}>제목(공식 원문 새 탭)</th><th style={th}>발행기관</th><th style={th}>국가</th><th style={th}>발표일</th><th style={th}>분야</th>
              <th style={th}>자료유형</th><th style={th}>실무활용성</th><th style={th}>원문확보</th><th style={th}>원문 언어</th><th style={th}>검토상태</th><th style={th}></th>
            </tr>
          </thead>
          <tbody>
            {items.map((d) => (
              <tr key={d.id} style={{ borderTop: "1px solid var(--border)" }} data-testid="news-row">
                <td style={td}>
                  <OriginalLink url={d.origin_url} state={d.link_state} blocked={d.link_blocked} note={d.link_note} isPdf={d.is_pdf} testId="news-link">{d.title}</OriginalLink>
                </td>
                <td style={td}>{d.source_org_name}</td>
                <td style={td}>{d.country_code ?? "-"}</td>
                <td style={td}>{fmtDateOnly(d.published_at)}</td>
                <td style={td}>{d.primary_field_code ? FIELD_LABELS[d.primary_field_code] ?? d.primary_field_code : "-"}</td>
                <td style={td}>{DOCUMENT_TYPE_LABELS[d.document_type] ?? d.document_type}</td>
                <td style={td}>{d.value_rating ? VALUE_RATING_LABELS[d.value_rating] ?? d.value_rating : "-"}</td>
                <td style={td}>{d.extraction_status ? EXTRACTION_STATUS_LABELS[d.extraction_status] ?? d.extraction_status : "미처리"}</td>
                <td style={td}>{d.language ? LANG_LABELS[d.language] ?? d.language : "-"}{(d.version_no ?? 1) > 1 && <span className="badge warn" style={{ marginLeft: 4 }}>v{d.version_no}</span>}</td>
                <td style={td}>
                  {d.relevance ? (
                    <span className={`pill ${d.relevance === "matched" ? "rec" : d.relevance === "pending_review" ? "hold" : "review"}`}>{RELEVANCE_LABELS[d.relevance] ?? d.relevance}</span>
                  ) : "-"}
                </td>
                <td style={{ ...td, display: "flex", gap: 6, flexWrap: "wrap", minWidth: 190 }}>
                  <Link className="tbtn" href={`/documents/${d.id}`} aria-label={`상세 분석: ${d.title}`}>상세 분석</Link>{" "}
                  <button className="tbtn" onClick={() => registerCandidate(d)} aria-label={`후보 등록: ${d.title}`} data-testid="register-candidate">후보 등록</button>{" "}
                  <button className="tbtn" disabled title="한글 번역 엔진은 Phase 4-3에서 연결됩니다 — 지금은 번역할 수 없습니다" aria-label="한글 번역(준비 중)">번역(준비 중)</button>
                </td>
              </tr>
            ))}
            {!loading && items.length === 0 && (
              <tr><td colSpan={11} style={{ padding: 20, textAlign: "center", color: "var(--ink-muted)" }} data-testid="empty-state">
                {fieldLabel && activeFilterCount === 1
                  ? `'${fieldLabel}' 분야로 분류된 수집 자료가 아직 없습니다 — 다른 분야 자료로 채우지 않았습니다(수집원 보강 필요).`
                  : "조건에 맞는 자료가 없습니다"}
              </td></tr>
            )}
          </tbody>
        </table>
      </div>

      <div style={{ display: "flex", justifyContent: "center", gap: 8, marginTop: 14 }}>
        <button className="tbtn" disabled={page <= 1} onClick={() => apply({}, { page: page - 1 })}>이전</button>
        <span style={{ fontSize: 13, display: "flex", alignItems: "center" }}>{page} / {totalPages}</span>
        <button className="tbtn" disabled={page >= totalPages} onClick={() => apply({}, { page: page + 1 })}>다음</button>
      </div>
    </AppShell>
  );
}

const selectStyle: React.CSSProperties = { padding: "7px 9px", borderRadius: 8, border: "1px solid var(--border)", fontSize: 13, minWidth: 0 };
const th: React.CSSProperties = { padding: "9px 12px", whiteSpace: "nowrap" };
const td: React.CSSProperties = { padding: "9px 12px" };

export default function DocumentsPage() {
  return (
    <Suspense fallback={<AppShell><p>불러오는 중...</p></AppShell>}>
      <DocumentsList />
    </Suspense>
  );
}
