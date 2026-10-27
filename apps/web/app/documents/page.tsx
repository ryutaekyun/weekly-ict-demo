"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import AppShell from "@/components/AppShell";
import OriginalLink from "@/components/OriginalLink";
import { getDocumentFacets, listDocuments, type DocumentFacets, type DocumentListItem } from "@/lib/api";
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
const SORTS: Record<string, string> = { published_desc: "발표일 최신순", published_asc: "발표일 오래된순", title: "제목순", collected_desc: "수집일 최신순" };
// URL 검색 조건 이름 — 상세 화면에서 뒤로 돌아와도 같은 조건으로 다시 조회된다
const KEYS = ["field_code", "country_code", "source_id", "document_type", "relevance", "extraction_status", "has_full_text", "has_issue", "has_candidate", "candidate_status",
  "published_after", "published_before", "sort", "q"] as const;
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
  }, [filters, page, pageSize]);

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
      <h1 style={{ fontSize: 20, fontWeight: 700, marginBottom: 4 }}>ICT 정보 수집</h1>
      <p style={{ color: "var(--ink-muted)", fontSize: 13, marginTop: 0 }}>
        분야 필터는 출처 고정분야가 아니라 실제 분류 결과(document_classifications.primary_field_code)를 기준으로 합니다.
        제목을 누르면 공식 원문이 새 탭에서 열리고, &lsquo;상세 분석&rsquo;은 플랫폼 안의 분류·전문·이슈 화면으로 이동합니다.
      </p>

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
              <th style={th}>자료유형</th><th style={th}>실무활용성</th><th style={th}>원문확보</th><th style={th}>검토상태</th><th style={th}></th>
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
                <td style={td}>
                  {d.relevance ? (
                    <span className={`pill ${d.relevance === "matched" ? "rec" : d.relevance === "pending_review" ? "hold" : "review"}`}>{RELEVANCE_LABELS[d.relevance] ?? d.relevance}</span>
                  ) : "-"}
                </td>
                <td style={td}><Link className="tbtn" href={`/documents/${d.id}`} aria-label={`상세 분석: ${d.title}`}>상세 분석</Link></td>
              </tr>
            ))}
            {!loading && items.length === 0 && (
              <tr><td colSpan={10} style={{ padding: 20, textAlign: "center", color: "var(--ink-muted)" }} data-testid="empty-state">
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
