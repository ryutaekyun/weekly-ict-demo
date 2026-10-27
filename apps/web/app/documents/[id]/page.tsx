"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import AppShell from "@/components/AppShell";
import OriginalLink from "@/components/OriginalLink";
import AiPanel from "@/components/AiPanel";
import {
  checkDocumentLink,
  getDocumentAnalysis,
  getDocumentFullText,
  getDocumentMeta,
  overrideClassification,
  overrideValueAssessment,
  UnauthorizedError,
  type DocumentAnalysis,
  type DocumentListItem,
  type LinkCheckResult,
} from "@/lib/api";
import {
  DOCUMENT_TYPE_LABELS,
  FIELD_LABELS,
  METHOD_LABELS,
  RELEVANCE_LABELS,
  VALUE_RATING_LABELS,
  fmtDate,
} from "@/lib/labels";

const CHUNK_SIZE = 1200;

export default function DocumentDetailPage() {
  const [linkCheck, setLinkCheck] = useState<LinkCheckResult | null>(null);
  const [checking, setChecking] = useState(false);
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const [meta, setMeta] = useState<DocumentListItem | null>(null);
  const [analysis, setAnalysis] = useState<DocumentAnalysis | null>(null);
  const [fullText, setFullText] = useState<string | null>(null);
  const [fullTextError, setFullTextError] = useState<string | null>(null);
  const [chunkIndex, setChunkIndex] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [saveMsg, setSaveMsg] = useState<string | null>(null);

  const [editField, setEditField] = useState("");
  const [editRelevance, setEditRelevance] = useState("matched");
  const [editReason, setEditReason] = useState("");
  const [editRating, setEditRating] = useState("general");

  function load() {
    const id = params.id;
    getDocumentMeta(id)
      .then((m) => {
        setMeta(m);
        setEditField(m.primary_field_code ?? "");
        setEditRelevance(m.relevance ?? "matched");
        setEditRating(m.value_rating ?? "general");
      })
      .catch((err) => {
        if (err instanceof UnauthorizedError) { router.push("/login"); return; }
        setError(err instanceof Error ? err.message : "불러오기 실패");
      });
    getDocumentAnalysis(id).then(setAnalysis).catch(() => {});
    getDocumentFullText(id)
      .then((ft) => setFullText(ft.full_text))
      .catch((err) => setFullTextError(err instanceof Error ? err.message : "전문을 확보하지 못했습니다"));
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params.id]);

  async function saveClassification(e: React.FormEvent) {
    e.preventDefault();
    setSaveMsg(null);
    try {
      await overrideClassification(params.id, {
        primary_field_code: editField || null,
        related_field_codes: [],
        relevance: editRelevance,
        reason: editReason || undefined,
      });
      setSaveMsg("분류가 저장되었습니다");
      setEditReason("");
      load();
    } catch (err) {
      setSaveMsg(err instanceof Error ? `저장 실패: ${err.message}` : "저장 실패");
    }
  }

  async function saveValueAssessment(e: React.FormEvent) {
    e.preventDefault();
    setSaveMsg(null);
    try {
      await overrideValueAssessment(params.id, { rating: editRating, reason: editReason || undefined });
      setSaveMsg("실무 활용성 평가가 저장되었습니다");
      load();
    } catch (err) {
      setSaveMsg(err instanceof Error ? `저장 실패: ${err.message}` : "저장 실패");
    }
  }

  async function checkLink() {
    setChecking(true);
    setLinkCheck(null);
    try { setLinkCheck(await checkDocumentLink(params.id)); } catch (err) { setLinkCheck({ state: "unreachable", http_status: null, final_url: null, origin_url: "", note: err instanceof Error ? err.message : "점검 실패" }); }
    finally { setChecking(false); }
  }

  if (error) return <AppShell><p style={{ color: "var(--bad)" }}>{error}</p></AppShell>;
  if (!meta) return <AppShell><p>불러오는 중...</p></AppShell>;

  const chunks: string[] = fullText ? fullText.match(new RegExp(`.{1,${CHUNK_SIZE}}`, "gs")) ?? [fullText] : [];

  return (
    <AppShell>
      <div style={{ marginBottom: 10 }}>
        <Link href="/documents" style={{ fontSize: 13 }}>← 목록으로</Link>
      </div>
      <h1 style={{ fontSize: 19, fontWeight: 700, marginBottom: 6 }}>{meta.title}</h1>
      <div style={{ display: "flex", gap: 14, flexWrap: "wrap", fontSize: 13, color: "var(--ink-muted)", marginBottom: 14 }}>
        <span>{meta.source_org_name}</span>
        <span>{meta.country_code ?? "-"}</span>
        <span>발표 {fmtDate(meta.published_at)}</span>
        <span>수집 {fmtDate(meta.collected_at)}</span>
        <span>{DOCUMENT_TYPE_LABELS[meta.document_type] ?? meta.document_type}</span>
        <OriginalLink url={meta.origin_url} state={meta.link_state} blocked={meta.link_blocked} note={meta.link_note} isPdf={meta.is_pdf} testId="detail-origin-link">원문 링크 열기 ↗</OriginalLink>
        {meta.attachment_url && <a href={meta.attachment_url} target="_blank" rel="noopener noreferrer">첨부 PDF 열기 ↗</a>}
        <button className="tbtn" onClick={checkLink} disabled={meta.link_blocked || checking}>{checking ? "점검 중..." : "원문 링크 접속 점검"}</button>
      </div>
      {linkCheck && (
        <p role="status" style={{ fontSize: 12.5, margin: "-6px 0 10px", color: linkCheck.state === "reachable" ? "var(--ok)" : "#9a4b00" }}>
          {({ reachable: "접속 확인됨", not_found: "문서를 찾을 수 없음(삭제되었거나 주소 오류 가능)", restricted: "서버가 접속을 제한함(주소 오류와 구분)", server_error: "서버 응답 오류", unreachable: "접속하지 못함(네트워크 제한일 수 있음)" } as Record<string, string>)[linkCheck.state] ?? linkCheck.state}
          {linkCheck.http_status ? ` · HTTP ${linkCheck.http_status}` : ""}{linkCheck.note ? ` — ${linkCheck.note}` : ""}
        </p>
      )}

      {meta.issue_cluster_id && (
        <div className="panel" style={{ marginBottom: 14, background: "var(--navy-soft)" }}>
          이 문서는 이슈 클러스터에 연결되어 있습니다. <Link href={`/issues/${meta.issue_cluster_id}`}>관련 이슈 분석 보기 →</Link>
        </div>
      )}

      {saveMsg && <p style={{ fontSize: 13, color: saveMsg.includes("실패") ? "var(--bad)" : "var(--ok)" }}>{saveMsg}</p>}

      <section style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginBottom: 16 }}>
        <form className="panel" onSubmit={saveClassification} style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <h2 style={{ fontSize: 14, margin: 0 }}>분야 분류</h2>
          <div style={{ fontSize: 12, color: "var(--ink-muted)" }}>
            현재: {meta.classification_method ? METHOD_LABELS[meta.classification_method] ?? meta.classification_method : "미분류"}
            {analysis?.classification?.is_researcher_overridden && " · 연구원 수정됨"}
          </div>
          <label style={lbl}>주 분야
            <select value={editField} onChange={(e) => setEditField(e.target.value)} style={inp}>
              <option value="">미지정</option>
              {Object.entries(FIELD_LABELS).map(([c, l]) => <option key={c} value={c}>{l}</option>)}
            </select>
          </label>
          <label style={lbl}>검토 상태
            <select value={editRelevance} onChange={(e) => setEditRelevance(e.target.value)} style={inp}>
              {Object.entries(RELEVANCE_LABELS).map(([c, l]) => <option key={c} value={c}>{l}</option>)}
            </select>
          </label>
          <label style={lbl}>수정 사유
            <input value={editReason} onChange={(e) => setEditReason(e.target.value)} style={inp} placeholder="수정 사유(선택)" />
          </label>
          <button className="tbtn primary" type="submit" style={{ alignSelf: "flex-start" }}>분류 저장</button>
          {analysis?.classification?.reasoning && (
            <p style={{ fontSize: 12, color: "var(--ink-muted)", marginTop: 4 }}>자동분류 근거: {analysis.classification.reasoning}</p>
          )}
        </form>

        <form className="panel" onSubmit={saveValueAssessment} style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <h2 style={{ fontSize: 14, margin: 0 }}>실무 활용성 평가</h2>
          <div style={{ fontSize: 12, color: "var(--ink-muted)" }}>
            현재: {meta.value_rating ? VALUE_RATING_LABELS[meta.value_rating] : "미평가"}
            {analysis?.value_assessment?.is_researcher_overridden && " · 연구원 수정됨"}
          </div>
          <label style={lbl}>평가
            <select value={editRating} onChange={(e) => setEditRating(e.target.value)} style={inp}>
              {Object.entries(VALUE_RATING_LABELS).map(([c, l]) => <option key={c} value={c}>{l}</option>)}
            </select>
          </label>
          <button className="tbtn primary" type="submit" style={{ alignSelf: "flex-start" }}>평가 저장</button>
          {analysis?.value_assessment?.evidence_quote && (
            <p style={{ fontSize: 12, color: "var(--ink-muted)", marginTop: 4 }}>근거 인용: &ldquo;{analysis.value_assessment.evidence_quote}&rdquo;</p>
          )}
        </form>
      </section>

      <AiPanel kind="document" targetId={params.id} title="AI 분석 (원문 근거 기반 · 규칙 기반 결과와 별도 보존)" buttonLabel="AI 분석 요청" testId="ai-panel-document" />

      {analysis?.structured_extract && (
        <section className="panel" style={{ marginBottom: 16 }}>
          <h2 style={{ fontSize: 14, margin: "0 0 10px" }}>구조화된 핵심 내용</h2>
          <dl style={{ fontSize: 13, margin: 0 }}>
            {analysis.structured_extract.key_content && <><dt style={dt}>핵심 내용</dt><dd style={dd}>{analysis.structured_extract.key_content}</dd></>}
            {analysis.structured_extract.background_purpose && <><dt style={dt}>배경·목적</dt><dd style={dd}>{analysis.structured_extract.background_purpose}</dd></>}
            {analysis.structured_extract.policy_tech_change && <><dt style={dt}>정책·기술 변경사항</dt><dd style={dd}>{analysis.structured_extract.policy_tech_change}</dd></>}
            {analysis.structured_extract.contested_points && <><dt style={dt}>쟁점</dt><dd style={dd}>{analysis.structured_extract.contested_points}</dd></>}
          </dl>
        </section>
      )}

      <section className="panel">
        <h2 style={{ fontSize: 14, margin: "0 0 10px" }}>원문 전문</h2>
        {fullTextError && <p style={{ color: "var(--ink-muted)", fontSize: 13 }}>전문 확보 실패: {fullTextError}</p>}
        {!fullTextError && chunks.length === 0 && <p style={{ color: "var(--ink-muted)", fontSize: 13 }}>불러오는 중...</p>}
        {chunks.length > 0 && (
          <>
            <div style={{ whiteSpace: "pre-wrap", fontSize: 13.5, lineHeight: 1.6, maxHeight: 420, overflow: "auto", padding: 10, background: "var(--panel-2)", borderRadius: 8 }}>
              {chunks[chunkIndex]}
            </div>
            {chunks.length > 1 && (
              <div style={{ display: "flex", justifyContent: "center", gap: 8, marginTop: 10 }}>
                <button className="tbtn" disabled={chunkIndex === 0} onClick={() => setChunkIndex((i) => i - 1)}>이전 구간</button>
                <span style={{ fontSize: 13, display: "flex", alignItems: "center" }}>{chunkIndex + 1} / {chunks.length}</span>
                <button className="tbtn" disabled={chunkIndex >= chunks.length - 1} onClick={() => setChunkIndex((i) => i + 1)}>다음 구간</button>
              </div>
            )}
          </>
        )}
      </section>
    </AppShell>
  );
}

const lbl: React.CSSProperties = { fontSize: 12.5, fontWeight: 700, display: "flex", flexDirection: "column", gap: 4 };
const inp: React.CSSProperties = { padding: 8, borderRadius: 8, border: "1px solid var(--border)", fontWeight: 400, fontSize: 13 };
const dt: React.CSSProperties = { fontWeight: 700, marginTop: 8 };
const dd: React.CSSProperties = { margin: "2px 0 0" };
