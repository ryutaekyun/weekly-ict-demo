"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import AppShell from "@/components/AppShell";
import { listDocuments, type DocumentListItem } from "@/lib/api";
import {
  DOCUMENT_TYPE_LABELS,
  EXTRACTION_STATUS_LABELS,
  FIELD_LABELS,
  RELEVANCE_LABELS,
  VALUE_RATING_LABELS,
  fmtDateOnly,
} from "@/lib/labels";

const PAGE_SIZES = [20, 50, 100, 300];

function DocumentsList() {
  const router = useRouter();
  const searchParams = useSearchParams();

  const [fieldCode, setFieldCode] = useState(searchParams.get("field_code") ?? "");
  const [relevance, setRelevance] = useState(searchParams.get("relevance") ?? "");
  const [documentType, setDocumentType] = useState(searchParams.get("document_type") ?? "");
  const [q, setQ] = useState(searchParams.get("q") ?? "");
  const [page, setPage] = useState(Number(searchParams.get("page") ?? 1));
  const [pageSize, setPageSize] = useState(Number(searchParams.get("page_size") ?? 20));

  const [items, setItems] = useState<DocumentListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    listDocuments({
      field_code: fieldCode || undefined,
      relevance: relevance || undefined,
      document_type: documentType || undefined,
      q: q || undefined,
      page,
      page_size: pageSize,
    })
      .then((res) => {
        setItems(res.items);
        setTotal(res.total);
      })
      .catch((err) => setError(err instanceof Error ? err.message : "불러오기 실패"))
      .finally(() => setLoading(false));
  }, [fieldCode, relevance, documentType, q, page, pageSize]);

  function applyFilters(next: Partial<{ fieldCode: string; relevance: string; documentType: string; q: string; page: number; pageSize: number }>) {
    const merged = { fieldCode, relevance, documentType, q, page, pageSize, ...next };
    if (!("page" in next)) merged.page = 1;
    setFieldCode(merged.fieldCode);
    setRelevance(merged.relevance);
    setDocumentType(merged.documentType);
    setQ(merged.q);
    setPage(merged.page);
    setPageSize(merged.pageSize);
    const params = new URLSearchParams();
    if (merged.fieldCode) params.set("field_code", merged.fieldCode);
    if (merged.relevance) params.set("relevance", merged.relevance);
    if (merged.documentType) params.set("document_type", merged.documentType);
    if (merged.q) params.set("q", merged.q);
    params.set("page", String(merged.page));
    params.set("page_size", String(merged.pageSize));
    router.replace(`/documents?${params.toString()}`, { scroll: false });
  }

  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  return (
    <AppShell>
      <h1 style={{ fontSize: 20, fontWeight: 700, marginBottom: 4 }}>ICT 정보 수집</h1>
      <p style={{ color: "var(--ink-muted)", fontSize: 13, marginTop: 0 }}>
        분야 필터는 출처 고정분야가 아니라 실제 분류 결과(document_classifications.primary_field_code)를 기준으로 합니다.
      </p>

      <div className="panel" style={{ display: "flex", flexWrap: "wrap", gap: 10, marginBottom: 14, alignItems: "center" }}>
        <select value={fieldCode} onChange={(e) => applyFilters({ fieldCode: e.target.value })} style={selectStyle}>
          <option value="">전체 분야</option>
          {Object.entries(FIELD_LABELS).map(([code, label]) => (
            <option key={code} value={code}>{label}</option>
          ))}
        </select>
        <select value={relevance} onChange={(e) => applyFilters({ relevance: e.target.value })} style={selectStyle}>
          <option value="">전체 검토상태</option>
          {Object.entries(RELEVANCE_LABELS).map(([code, label]) => (
            <option key={code} value={code}>{label}</option>
          ))}
        </select>
        <select value={documentType} onChange={(e) => applyFilters({ documentType: e.target.value })} style={selectStyle}>
          <option value="">전체 자료유형</option>
          {Object.entries(DOCUMENT_TYPE_LABELS).map(([code, label]) => (
            <option key={code} value={code}>{label}</option>
          ))}
        </select>
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") applyFilters({ q }); }}
          placeholder="제목 키워드 검색"
          style={{ ...selectStyle, minWidth: 200 }}
        />
        <button className="tbtn" onClick={() => applyFilters({ q })}>검색</button>
        <select value={pageSize} onChange={(e) => applyFilters({ pageSize: Number(e.target.value) })} style={selectStyle}>
          {PAGE_SIZES.map((n) => (
            <option key={n} value={n}>{n}건씩 보기</option>
          ))}
        </select>
        <span style={{ marginLeft: "auto", fontSize: 13, color: "var(--ink-muted)" }}>총 {total}건</span>
      </div>

      {error && <p style={{ color: "var(--bad)" }}>{error}</p>}
      {loading && <p style={{ color: "var(--ink-muted)" }}>불러오는 중...</p>}

      <div className="panel" style={{ padding: 0, overflow: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
          <thead>
            <tr style={{ textAlign: "left", background: "var(--panel-2)" }}>
              <th style={th}>제목</th>
              <th style={th}>발행기관</th>
              <th style={th}>국가</th>
              <th style={th}>발표일</th>
              <th style={th}>분야</th>
              <th style={th}>자료유형</th>
              <th style={th}>실무활용성</th>
              <th style={th}>원문확보</th>
              <th style={th}>검토상태</th>
            </tr>
          </thead>
          <tbody>
            {items.map((d) => (
              <tr key={d.id} style={{ borderTop: "1px solid var(--border)" }}>
                <td style={td}><Link href={`/documents/${d.id}`}>{d.title}</Link></td>
                <td style={td}>{d.source_org_name}</td>
                <td style={td}>{d.country_code ?? "-"}</td>
                <td style={td}>{fmtDateOnly(d.published_at)}</td>
                <td style={td}>{d.primary_field_code ? FIELD_LABELS[d.primary_field_code] ?? d.primary_field_code : "-"}</td>
                <td style={td}>{DOCUMENT_TYPE_LABELS[d.document_type] ?? d.document_type}</td>
                <td style={td}>{d.value_rating ? VALUE_RATING_LABELS[d.value_rating] ?? d.value_rating : "-"}</td>
                <td style={td}>{d.extraction_status ? EXTRACTION_STATUS_LABELS[d.extraction_status] ?? d.extraction_status : "미처리"}</td>
                <td style={td}>
                  {d.relevance ? (
                    <span className={`pill ${d.relevance === "matched" ? "rec" : d.relevance === "pending_review" ? "hold" : "review"}`}>
                      {RELEVANCE_LABELS[d.relevance] ?? d.relevance}
                    </span>
                  ) : "-"}
                </td>
              </tr>
            ))}
            {!loading && items.length === 0 && (
              <tr><td colSpan={9} style={{ padding: 20, textAlign: "center", color: "var(--ink-muted)" }}>조건에 맞는 자료가 없습니다</td></tr>
            )}
          </tbody>
        </table>
      </div>

      <div style={{ display: "flex", justifyContent: "center", gap: 8, marginTop: 14 }}>
        <button className="tbtn" disabled={page <= 1} onClick={() => applyFilters({ page: page - 1 })}>이전</button>
        <span style={{ fontSize: 13, display: "flex", alignItems: "center" }}>{page} / {totalPages}</span>
        <button className="tbtn" disabled={page >= totalPages} onClick={() => applyFilters({ page: page + 1 })}>다음</button>
      </div>
    </AppShell>
  );
}

const selectStyle: React.CSSProperties = { padding: "7px 9px", borderRadius: 8, border: "1px solid var(--border)", fontSize: 13 };
const th: React.CSSProperties = { padding: "9px 12px", whiteSpace: "nowrap" };
const td: React.CSSProperties = { padding: "9px 12px" };

export default function DocumentsPage() {
  return (
    <Suspense fallback={<AppShell><p>불러오는 중...</p></AppShell>}>
      <DocumentsList />
    </Suspense>
  );
}
