"use client";

import AiPanel from "@/components/AiPanel";
import AiInsertionsPanel from "@/components/AiInsertionsPanel";
import { aiListInsertions, type AiInsertionRow } from "@/lib/aiApi";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import type { Editor } from "@tiptap/react";
import AppShell from "@/components/AppShell";
import FollowupBanner from "@/components/FollowupBanner";
import ManuscriptEditor from "@/components/ManuscriptEditor";
import { collectFootnoteOrder } from "@/lib/footnoteMark";
import {
  approveManuscript,
  createFootnote,
  createManuscriptComment,
  getCurrentUser,
  getManuscript,
  getManuscriptContext,
  getManuscriptVersion,
  listFootnotes,
  listManuscriptComments,
  listManuscriptVersions,
  listUsers,
  reopenManuscript,
  requestManuscriptChanges,
  requestManuscriptReview,
  resolveManuscriptComment,
  restoreManuscriptVersion,
  updateIitpSelection,
  updateManuscriptBody,
  verifyFootnote,
  UnauthorizedError,
  type CurrentUser,
  type FootnoteOut,
  type ManuscriptCommentOut,
  type ManuscriptDetail,
  type ManuscriptVersionDetail,
  type ManuscriptVersionListItem,
  type UserSummary,
} from "@/lib/api";
import { FIELD_LABELS, fmtDate } from "@/lib/labels";

const STATUS_LABELS: Record<string, string> = {
  draft: "초안",
  review: "검토중",
  review_requested: "검토 요청됨",
  changes_requested: "수정 요청됨",
  approved: "내부 확정",
  final: "최종",
};

const IITP_LABELS: Record<string, string> = {
  not_submitted: "미제출",
  pending: "IITP 검토중",
  selected: "IITP 선정",
  not_selected: "IITP 미선정",
};

type RightTab = "context" | "footnotes" | "comments" | "versions" | "ai";

export default function ManuscriptWorkspacePage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const [me, setMe] = useState<CurrentUser | null>(null);
  const [manuscript, setManuscript] = useState<ManuscriptDetail | null>(null);
  const [context, setContext] = useState<{ candidate: any; issue: any } | null>(null);
  const [footnotes, setFootnotes] = useState<FootnoteOut[]>([]);
  const [comments, setComments] = useState<ManuscriptCommentOut[]>([]);
  const [versions, setVersions] = useState<ManuscriptVersionListItem[]>([]);
  const [reviewers, setReviewers] = useState<UserSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [saveStatus, setSaveStatus] = useState<"idle" | "saving" | "saved" | "conflict" | "error">("idle");
  const [rightTab, setRightTab] = useState<RightTab>("context");
  const [insertions, setInsertions] = useState<AiInsertionRow[]>([]);
  const [footnoteDraft, setFootnoteDraft] = useState<{ text: string; from: number; to: number } | null>(null);
  const [footnoteForm, setFootnoteForm] = useState({ source_url: "", source_org: "", excerpt: "", location_label: "", source_document_id: "" });
  const [commentText, setCommentText] = useState("");
  const [reviewerChoice, setReviewerChoice] = useState("");
  const [diffVersion, setDiffVersion] = useState<ManuscriptVersionDetail | null>(null);
  const [changesPrompt, setChangesPrompt] = useState(false);
  const [changesText, setChangesText] = useState("");
  const [milestonePrompt, setMilestonePrompt] = useState(false);
  const [milestoneNote, setMilestoneNote] = useState("");
  const [iitpPrompt, setIitpPrompt] = useState<"selected" | "not_selected" | null>(null);
  const [iitpNote, setIitpNote] = useState("");
  const [actionMsg, setActionMsg] = useState<string | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [activeFootnote, setActiveFootnote] = useState<string | null>(null);

  const editorRef = useRef<Editor | null>(null);
  const saveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const titleRef = useRef<HTMLInputElement | null>(null);
  const manuscriptRef = useRef<ManuscriptDetail | null>(null);
  const saveInFlightRef = useRef(false);
  const queuedSaveRef = useRef<{ json: string; text: string; opts: { milestone?: boolean; changeNote?: string } } | null>(null);

  useEffect(() => { manuscriptRef.current = manuscript; }, [manuscript]);

  const load = useCallback(() => {
    const id = params.id;
    getManuscript(id)
      .then(setManuscript)
      .catch((err) => {
        if (err instanceof UnauthorizedError) { router.push("/login"); return; }
        setError(err instanceof Error ? err.message : "불러오기 실패");
      });
    getManuscriptContext(id).then(setContext).catch(() => setContext({ candidate: null, issue: null }));
    listFootnotes(id).then(setFootnotes).catch(() => {});
    listManuscriptComments(id).then(setComments).catch(() => {});
    listManuscriptVersions(id).then(setVersions).catch(() => {});
    aiListInsertions(id).then(setInsertions).catch(() => setInsertions([]));
  }, [params.id, router]);

  useEffect(() => {
    getCurrentUser().then(setMe).catch(() => {});
    load();
  }, [load]);

  useEffect(() => {
    listUsers().then(setReviewers).catch(() => {});
  }, []);

  const footnoteOrder = useMemo(() => {
    if (!editorRef.current) return [] as string[];
    return collectFootnoteOrder(editorRef.current.state.doc);
  }, [footnotes, manuscript]);

  async function ensureSavedLock(): Promise<number> {
    // 저장 대기 중인 연구원 수정이 있으면 먼저 저장하고, 서버의 최신 lock_version을 돌려준다(AI 삽입이 연구원 수정을 덮어쓰지 않도록)
    if (saveTimerRef.current && editorRef.current) {
      clearTimeout(saveTimerRef.current);
      saveTimerRef.current = null;
      await doSave(JSON.stringify(editorRef.current.getJSON()), editorRef.current.getText());
    }
    const fresh = await getManuscript(params.id);
    return fresh.lock_version;
  }

  const aiTarget = {
    id: params.id, getLockVersion: ensureSavedLock, onInserted: reloadAfterAiInsert,
    // 편집기 커서가 있는 최상위 문단의 인덱스와 소제목 목록 — 현재 커서·소제목 아래 삽입에 쓴다
    getCursorIndex: () => (editorRef.current ? editorRef.current.state.selection.$from.index(0) : null),
    getHeadings: () => {
      const out: string[] = [];
      editorRef.current?.state.doc.forEach((n) => { if (n.type.name === "heading") out.push(n.textContent); });
      return out;
    },
  };

  async function reloadAfterAiInsert() {
    const fresh = await getManuscript(params.id);
    setManuscript(fresh);
    if (editorRef.current && fresh.body_json) editorRef.current.commands.setContent(JSON.parse(fresh.body_json), { emitUpdate: false });
    listFootnotes(params.id).then(setFootnotes).catch(() => {});
    listManuscriptVersions(params.id).then(setVersions).catch(() => {});
    aiListInsertions(params.id).then(setInsertions).catch(() => {});
  }

  function scheduleSave(json: string, text: string) {
    if (!manuscript) return;
    if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
    saveTimerRef.current = setTimeout(() => doSave(json, text), 1500);
  }

  async function doSave(json: string, text: string, opts: { milestone?: boolean; changeNote?: string } = {}) {
    // 예약된 타이머가 만들어질 때의(오래된) 렌더 값이 아니라 항상 최신 원고(ref)를 기준으로 저장한다.
    const current = manuscriptRef.current;
    if (!current) return;
    // 디바운스 자동저장과 명시적 저장(버전저장·각주연결 등)이 겹치면 둘 다 같은(오래된)
    // lock_version으로 요청을 보내 서로 충돌로 보이는 409가 날 수 있다 — 어느 경로로 저장이
    // 들어오든 대기 중인 예약 저장은 항상 취소한다.
    if (saveTimerRef.current) {
      clearTimeout(saveTimerRef.current);
      saveTimerRef.current = null;
    }
    // 앞선 저장이 진행 중이면 최신 내용만 대기열에 두고, 끝난 뒤 갱신된 lock_version으로 이어서 저장한다
    // (진행 중인 요청과 동시에 보내면 스스로 만든 409 충돌이 난다).
    if (saveInFlightRef.current) {
      queuedSaveRef.current = { json, text, opts };
      return;
    }
    saveInFlightRef.current = true;
    setSaveStatus("saving");
    let succeeded = false;
    try {
      const updated = await updateManuscriptBody(current.id, {
        title: titleRef.current?.value.trim() || undefined,  // 제목 입력란 수정도 함께 저장한다
        body_json: json, body: text, lock_version: current.lock_version,
        is_milestone: opts.milestone, change_note: opts.changeNote,
      });
      manuscriptRef.current = updated;
      setManuscript(updated);
      setSaveStatus("saved");
      succeeded = true;
      listManuscriptVersions(current.id).then(setVersions).catch(() => {});
    } catch (err) {
      if (err instanceof Error && err.message.includes("다른 사용자가")) {
        setSaveStatus("conflict");
      } else {
        setSaveStatus("error");
      }
    } finally {
      saveInFlightRef.current = false;
      const queued = queuedSaveRef.current;
      queuedSaveRef.current = null;
      if (queued && succeeded) void doSave(queued.json, queued.text, queued.opts);
    }
  }

  function handleEditorUpdate(json: string, text: string) {
    scheduleSave(json, text);
  }

  function handleReloadAfterConflict() {
    load();
    setSaveStatus("idle");
  }

  function handleSelectForFootnote() {
    const editor = editorRef.current;
    if (!editor) return;
    const { from, to } = editor.state.selection;
    if (from === to) {
      setErrorMsg("먼저 본문에서 근거를 연결할 문장을 선택하세요");
      return;
    }
    setErrorMsg(null);
    const text = editor.state.doc.textBetween(from, to, " ");
    setFootnoteDraft({ text, from, to });
    setRightTab("footnotes");
  }

  async function submitFootnote() {
    if (!manuscript || !footnoteDraft || !editorRef.current) return;
    if (!footnoteForm.source_url.trim()) {
      setErrorMsg("원문 URL을 입력하세요");
      return;
    }
    const markId = crypto.randomUUID();
    try {
      const created = await createFootnote(manuscript.id, {
        mark_id: markId, anchor_text: footnoteDraft.text, source_url: footnoteForm.source_url,
        source_org: footnoteForm.source_org || undefined, excerpt: footnoteForm.excerpt || undefined,
        location_label: footnoteForm.location_label || undefined,
        source_document_id: footnoteForm.source_document_id || undefined,
      });
      editorRef.current
        .chain()
        .focus()
        .setTextSelection({ from: footnoteDraft.from, to: footnoteDraft.to })
        .setFootnoteMark(markId)
        .run();
      setFootnotes((prev) => [...prev, created]);
      setFootnoteDraft(null);
      setFootnoteForm({ source_url: "", source_org: "", excerpt: "", location_label: "", source_document_id: "" });
      // 마크 삽입이 onUpdate를 거쳐 예약해 둔 디바운스 자동저장과 중복 저장되면
      // 둘 다 같은(오래된) lock_version을 들고 있어 서로 충돌로 보이는 409가 난다 —
      // 예약된 자동저장을 취소하고 이 저장 하나만 즉시 실행한다.
      if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
      doSave(JSON.stringify(editorRef.current.getJSON()), editorRef.current.getText());
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "근거 연결 실패");
    }
  }

  async function handleVerify(footnoteId: string, matched: boolean) {
    if (!manuscript) return;
    const updated = await verifyFootnote(manuscript.id, footnoteId, matched);
    setFootnotes((prev) => prev.map((f) => (f.id === footnoteId ? updated : f)));
  }

  async function submitComment() {
    if (!manuscript || !commentText.trim()) return;
    const created = await createManuscriptComment(manuscript.id, { comment_text: commentText });
    setComments((prev) => [...prev, created]);
    setCommentText("");
  }

  async function handleResolveComment(id: string) {
    if (!manuscript) return;
    const updated = await resolveManuscriptComment(manuscript.id, id);
    setComments((prev) => prev.map((c) => (c.id === id ? updated : c)));
  }

  async function handleRequestReview() {
    if (!manuscript || !reviewerChoice) return;
    const updated = await requestManuscriptReview(manuscript.id, reviewerChoice);
    setManuscript(updated);
  }

  function openRequestChanges() {
    setChangesText("");
    setChangesPrompt(true);
    setRightTab("comments");
  }

  async function submitRequestChanges() {
    if (!manuscript || !changesText.trim()) return;
    try {
      const updated = await requestManuscriptChanges(manuscript.id, changesText);
      setManuscript(updated);
      setChangesPrompt(false);
      setChangesText("");
      listManuscriptComments(manuscript.id).then(setComments);
    } catch (err) {
      setActionMsg(err instanceof Error ? err.message : "수정 요청 실패");
    }
  }

  async function handleApprove() {
    if (!manuscript) return;
    try {
      const updated = await approveManuscript(manuscript.id);
      setManuscript(updated);
    } catch (err) {
      setActionMsg(err instanceof Error ? err.message : "승인 실패");
    }
  }

  async function handleReopen() {
    if (!manuscript) return;
    const updated = await reopenManuscript(manuscript.id);
    setManuscript(updated);
  }

  function openIitpPrompt(status: "selected" | "not_selected") {
    setIitpNote("");
    setIitpPrompt(status);
  }

  async function submitIitpSelection() {
    if (!manuscript || !iitpPrompt) return;
    try {
      const updated = await updateIitpSelection(manuscript.id, { iitp_selection_status: iitpPrompt, iitp_selection_note: iitpNote || undefined });
      setManuscript(updated);
      setIitpPrompt(null);
    } catch (err) {
      setActionMsg(err instanceof Error ? err.message : "기록 실패");
    }
  }

  async function handleViewVersion(versionId: string) {
    if (!manuscript) return;
    const v = await getManuscriptVersion(manuscript.id, versionId);
    setDiffVersion(v);
  }

  async function handleRestore(versionId: string) {
    // 복원해도 현재 내용이 새 버전으로 먼저 저장되므로(백엔드에서 처리) 데이터 손실이 없다 —
    // 별도 확인창 없이 바로 진행해도 안전하다.
    if (!manuscript) return;
    const updated = await restoreManuscriptVersion(manuscript.id, versionId);
    setManuscript(updated);
    setDiffVersion(null);
    listManuscriptVersions(manuscript.id).then(setVersions).catch(() => {});
    // 복원 결과를 편집기에도 즉시 반영한다(재마운트 없이 명령으로 내용만 교체).
    if (editorRef.current && updated.body_json) {
      try {
        editorRef.current.commands.setContent(JSON.parse(updated.body_json));
      } catch {
        // JSON 파싱 실패 시 조용히 건너뛴다 — 서버 값은 이미 올바르게 저장되어 있다
      }
    }
    setActionMsg("이전 버전으로 복원되었습니다");
  }

  if (error) return <AppShell><p style={{ color: "var(--bad)" }}>{error}</p></AppShell>;
  if (!manuscript) return <AppShell><p>불러오는 중...</p></AppShell>;

  const isAuthor = me?.id === manuscript.author_user_id;
  const isPrivileged = me ? ["admin", "approver", "reviewer"].includes(me.role) : false;
  const isApprover = me ? ["admin", "approver"].includes(me.role) : false;
  const canEdit = (isAuthor || isPrivileged) && manuscript.status !== "approved";

  return (
    <AppShell>
      <div style={{ marginBottom: 8 }}>
        <Link href="/manuscripts" style={{ fontSize: 13 }}>← 연구·집필 작업실 목록으로</Link>
      </div>

      <FollowupBanner entityType="manuscript" entityId={manuscript.id} canAck={isAuthor || isPrivileged} />
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10, gap: 10, flexWrap: "wrap" }}>
        <input
          ref={titleRef}
          defaultValue={manuscript.title}
          disabled={!canEdit}
          onBlur={(e) => {
            if (editorRef.current && e.target.value !== manuscript.title) {
              doSave(JSON.stringify(editorRef.current.getJSON()), editorRef.current.getText());
            }
          }}
          style={{ fontSize: 18, fontWeight: 700, border: "none", borderBottom: "1px solid var(--border)", padding: "4px 2px", flex: 1, minWidth: 240 }}
        />
        <span className="pill review">{STATUS_LABELS[manuscript.status] ?? manuscript.status}</span>
        <span className="pill" style={{ background: "var(--idle-soft)", color: "var(--idle)" }}>IITP: {IITP_LABELS[manuscript.iitp_selection_status]}</span>
        {manuscript.is_pilot && <span className="pill hold">시범 작성 원고</span>}
      </div>

      {manuscript.needs_reexamination.flagged && (
        <div className="panel" style={{ marginBottom: 10, background: "var(--warn-soft)", color: "var(--warn)", fontSize: 13 }}>
          확인 필요: {manuscript.needs_reexamination.reason}
        </div>
      )}

      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 12, alignItems: "center", fontSize: 13 }}>
        <span style={{ color: "var(--ink-muted)" }}>
          저장 상태: {saveStatus === "saving" ? "저장 중..." : saveStatus === "saved" ? "저장 완료" : saveStatus === "conflict" ? "충돌 발생" : saveStatus === "error" ? "저장 실패" : "대기"}
        </span>
        {saveStatus === "conflict" && (
          <span style={{ color: "var(--bad)" }}>
            다른 사용자가 먼저 저장했습니다. <button className="tbtn" onClick={handleReloadAfterConflict}>최신 내용 다시 불러오기</button>
          </span>
        )}
        {actionMsg && <span style={{ color: "var(--ok)" }}>{actionMsg}</span>}
        {errorMsg && <span role="alert" style={{ color: "var(--danger, #b42318)" }}>{errorMsg}</span>}
        <button className="tbtn" disabled={!canEdit || !editorRef.current} onClick={() => setMilestonePrompt(true)}>
          주요 버전 저장
        </button>
        <button className="tbtn" disabled={!canEdit} onClick={handleSelectForFootnote}>선택 영역에 근거 연결</button>

        {manuscript.status === "draft" || manuscript.status === "changes_requested" ? (
          <>
            <select value={reviewerChoice} onChange={(e) => setReviewerChoice(e.target.value)} style={{ padding: 6, borderRadius: 6, border: "1px solid var(--border)" }}>
              <option value="">검토자 선택</option>
              {reviewers.filter((r) => r.role !== "researcher").map((r) => <option key={r.id} value={r.id}>{r.display_name}({r.role})</option>)}
            </select>
            <button className="tbtn primary" disabled={!reviewerChoice} onClick={handleRequestReview}>검토 요청</button>
          </>
        ) : null}

        {manuscript.status === "review_requested" && isPrivileged && manuscript.reviewer_user_id === me?.id && (
          <button className="tbtn" onClick={openRequestChanges}>수정 요청</button>
        )}
        {manuscript.status === "review_requested" && isApprover && (
          <button className="tbtn primary" onClick={handleApprove}>내부 최종 승인</button>
        )}
        {manuscript.status === "approved" && isApprover && (
          <button className="tbtn" onClick={handleReopen}>재검토로 되돌리기</button>
        )}
        {isApprover && (
          <>
            <button className="tbtn" onClick={() => openIitpPrompt("selected")}>IITP 선정 기록</button>
            <button className="tbtn" onClick={() => openIitpPrompt("not_selected")}>IITP 미선정 기록</button>
          </>
        )}
      </div>

      {milestonePrompt && (
        <div className="panel" style={{ marginBottom: 12, background: "var(--navy-soft)", display: "flex", gap: 8, alignItems: "center" }}>
          <span style={{ fontSize: 13, fontWeight: 700 }}>버전 저장 사유</span>
          <input
            autoFocus value={milestoneNote} onChange={(e) => setMilestoneNote(e.target.value)}
            placeholder="예: 1차 초안 완료" style={{ flex: 1, padding: 7, borderRadius: 6, border: "1px solid var(--border)" }}
          />
          <button
            className="tbtn primary"
            onClick={() => {
              if (milestoneNote.trim() && editorRef.current) {
                doSave(JSON.stringify(editorRef.current.getJSON()), editorRef.current.getText(), { milestone: true, changeNote: milestoneNote });
              }
              setMilestonePrompt(false);
              setMilestoneNote("");
            }}
          >
            저장
          </button>
          <button className="tbtn" onClick={() => setMilestonePrompt(false)}>취소</button>
        </div>
      )}

      {iitpPrompt && (
        <div className="panel" style={{ marginBottom: 12, background: "var(--navy-soft)", display: "flex", gap: 8, alignItems: "center" }}>
          <span style={{ fontSize: 13, fontWeight: 700 }}>IITP {iitpPrompt === "selected" ? "선정" : "미선정"} 확인 메모</span>
          <input
            autoFocus value={iitpNote} onChange={(e) => setIitpNote(e.target.value)}
            placeholder="선택 입력" style={{ flex: 1, padding: 7, borderRadius: 6, border: "1px solid var(--border)" }}
          />
          <button className="tbtn primary" onClick={submitIitpSelection}>기록</button>
          <button className="tbtn" onClick={() => setIitpPrompt(null)}>취소</button>
        </div>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "220px 1fr 340px", gap: 16, alignItems: "start" }}>
        {/* 왼쪽: 목차 */}
        <div className="panel">
          <h2 style={{ fontSize: 13, margin: "0 0 8px" }}>원고 정보</h2>
          <dl style={{ fontSize: 12.5, margin: 0 }}>
            <dt style={{ color: "var(--ink-muted)" }}>유형</dt>
            <dd style={{ margin: "2px 0 8px" }}>{manuscript.manuscript_type}</dd>
            <dt style={{ color: "var(--ink-muted)" }}>근거 검증</dt>
            <dd style={{ margin: "2px 0 8px" }}>{footnotes.filter((f) => f.verification_status === "matched").length} / {footnotes.length}건 확인</dd>
            <dt style={{ color: "var(--ink-muted)" }}>검토자</dt>
            <dd style={{ margin: "2px 0 8px" }}>{reviewers.find((r) => r.id === manuscript.reviewer_user_id)?.display_name ?? "미지정"}</dd>
          </dl>
          <h2 style={{ fontSize: 13, margin: "12px 0 8px" }}>목차(본문 제목 기준)</h2>
          <TocList editor={editorRef.current} />
        </div>

        {/* 가운데: 편집기 */}
        <div className="panel">
          <ManuscriptEditor
            initialJson={manuscript.body_json}
            editable={canEdit}
            onUpdate={handleEditorUpdate}
            onEditorReady={(editor) => { editorRef.current = editor; }}
            onFootnoteClick={(markId) => { setActiveFootnote(markId); setRightTab("footnotes"); }}
          />
        </div>

        {/* 오른쪽: 원문·근거·검토 패널 */}
        <div className="panel">
          <div style={{ display: "flex", gap: 6, marginBottom: 10, flexWrap: "wrap" }}>
            <button className="tbtn" style={tabStyle(rightTab === "context")} onClick={() => setRightTab("context")}>원문·근거자료</button>
            <button className="tbtn" style={tabStyle(rightTab === "footnotes")} onClick={() => setRightTab("footnotes")}>각주({footnoteOrder.length || footnotes.length})</button>
            <button className="tbtn" style={tabStyle(rightTab === "comments")} onClick={() => setRightTab("comments")}>검토의견({comments.filter((c) => c.status === "open").length})</button>
            <button className="tbtn" style={tabStyle(rightTab === "versions")} onClick={() => setRightTab("versions")}>버전({versions.length})</button>
            {(manuscript.candidate_id || insertions.length > 0) && (
              <button className="tbtn" style={tabStyle(rightTab === "ai")} onClick={() => setRightTab("ai")} data-testid="tab-ai">
                AI 제안{insertions.some((i) => i.needs_review) ? " ⚠ 재검토" : ""}
              </button>
            )}
          </div>

          {rightTab === "context" && <ContextPanel context={context} />}
          {rightTab === "ai" && (
            <>
              <AiInsertionsPanel rows={insertions} getLockVersion={ensureSavedLock} onChanged={reloadAfterAiInsert} />
              {manuscript.candidate_id && (
                <>
                  <AiPanel kind="outline" targetId={manuscript.candidate_id} title="AI 목차 제안" buttonLabel="AI 목차 제안" testId="ai-panel-outline" manuscript={aiTarget} />
                  <AiPanel kind="draft" targetId={manuscript.candidate_id} title="AI 초안 제안 (연구원 검토용 초안 · 선택한 문장만 삽입)" buttonLabel="AI 초안 제안" testId="ai-panel-draft" manuscript={aiTarget} />
                </>
              )}
            </>
          )}

          {rightTab === "footnotes" && (
            <div>
              {footnoteDraft && (
                <div className="panel" style={{ background: "var(--navy-soft)", marginBottom: 10, fontSize: 12.5 }}>
                  <div style={{ fontWeight: 700, marginBottom: 6 }}>선택한 문장: &ldquo;{footnoteDraft.text.slice(0, 80)}&rdquo;</div>
                  <input placeholder="원문 URL(필수)" value={footnoteForm.source_url} onChange={(e) => setFootnoteForm({ ...footnoteForm, source_url: e.target.value })} style={inpStyle} />
                  <input placeholder="발표 기관" value={footnoteForm.source_org} onChange={(e) => setFootnoteForm({ ...footnoteForm, source_org: e.target.value })} style={inpStyle} />
                  <textarea placeholder="근거 원문 발췌" value={footnoteForm.excerpt} onChange={(e) => setFootnoteForm({ ...footnoteForm, excerpt: e.target.value })} style={{ ...inpStyle, minHeight: 50 }} />
                  <input placeholder="문단·페이지 위치(모르면 비워두면 '위치 미확인')" value={footnoteForm.location_label} onChange={(e) => setFootnoteForm({ ...footnoteForm, location_label: e.target.value })} style={inpStyle} />
                  <div style={{ display: "flex", gap: 6, marginTop: 6 }}>
                    <button className="tbtn primary" onClick={submitFootnote}>각주 생성</button>
                    <button className="tbtn" onClick={() => setFootnoteDraft(null)}>취소</button>
                  </div>
                </div>
              )}
              {footnotes.length === 0 && <p style={{ color: "var(--ink-muted)", fontSize: 12.5 }}>연결된 각주가 없습니다. 본문에서 문장을 선택하고 &ldquo;선택 영역에 근거 연결&rdquo;을 눌러보세요.</p>}
              {footnoteOrder.map((fid, idx) => {
                const f = footnotes.find((x) => x.mark_id === fid);
                if (!f) return null;
                return <FootnoteCard key={f.id} index={idx + 1} footnote={f} onVerify={handleVerify} active={activeFootnote === f.mark_id} />;
              })}
              {footnotes.filter((f) => !footnoteOrder.includes(f.mark_id)).map((f) => (
                <FootnoteCard key={f.id} index={null} footnote={f} onVerify={handleVerify} />
              ))}
            </div>
          )}

          {rightTab === "comments" && (
            <div>
              {changesPrompt && (
                <div className="panel" style={{ background: "var(--warn-soft)", marginBottom: 10, fontSize: 12.5 }}>
                  <div style={{ fontWeight: 700, marginBottom: 6 }}>수정 요청 의견</div>
                  <textarea autoFocus value={changesText} onChange={(e) => setChangesText(e.target.value)} placeholder="구체적인 수정 요청 사항을 입력하세요" style={{ ...inpStyle, minHeight: 60 }} />
                  <div style={{ display: "flex", gap: 6 }}>
                    <button className="tbtn primary" disabled={!changesText.trim()} onClick={submitRequestChanges}>수정 요청 보내기</button>
                    <button className="tbtn" onClick={() => setChangesPrompt(false)}>취소</button>
                  </div>
                </div>
              )}
              <div style={{ display: "flex", flexDirection: "column", gap: 8, marginBottom: 10 }}>
                {comments.map((c) => (
                  <div key={c.id} className="panel" style={{ background: c.status === "resolved" ? "var(--panel-2)" : "var(--warn-soft)", fontSize: 12.5 }}>
                    {c.anchor_text && <div style={{ fontStyle: "italic", color: "var(--ink-muted)", marginBottom: 4 }}>&ldquo;{c.anchor_text.slice(0, 60)}&rdquo;</div>}
                    <div>{c.comment_text}</div>
                    <div style={{ marginTop: 4, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                      <span style={{ color: "var(--ink-muted)" }}>{fmtDate(c.created_at)} · {c.status === "resolved" ? "해결됨" : "미해결"}</span>
                      {c.status === "open" && <button className="tbtn" onClick={() => handleResolveComment(c.id)}>해결 처리</button>}
                    </div>
                  </div>
                ))}
                {comments.length === 0 && <p style={{ color: "var(--ink-muted)", fontSize: 12.5 }}>검토의견이 없습니다</p>}
              </div>
              <textarea value={commentText} onChange={(e) => setCommentText(e.target.value)} placeholder="검토의견을 입력하세요" style={{ ...inpStyle, minHeight: 60 }} />
              <button className="tbtn primary" onClick={submitComment} style={{ marginTop: 6 }}>의견 등록</button>
            </div>
          )}

          {rightTab === "versions" && (
            <div>
              {diffVersion && (
                <div className="panel" style={{ background: "var(--panel-2)", marginBottom: 10, fontSize: 12 }}>
                  <div style={{ fontWeight: 700 }}>버전 {diffVersion.version_no} 미리보기</div>
                  <div style={{ whiteSpace: "pre-wrap", maxHeight: 160, overflow: "auto", marginTop: 6 }}>{diffVersion.body_snapshot}</div>
                  <button className="tbtn primary" style={{ marginTop: 6 }} onClick={() => handleRestore(diffVersion.id)}>이 버전으로 복원</button>
                </div>
              )}
              <ul style={{ listStyle: "none", padding: 0, margin: 0, fontSize: 12.5 }}>
                {versions.map((v) => (
                  <li key={v.id} style={{ padding: "6px 0", borderTop: "1px solid var(--border)" }}>
                    <div style={{ fontWeight: v.is_milestone ? 700 : 400 }}>
                      v{v.version_no} {v.is_milestone && <span className="pill rec" style={{ marginLeft: 4 }}>주요</span>}
                    </div>
                    <div style={{ color: "var(--ink-muted)" }}>{fmtDate(v.created_at)}{v.change_note ? ` · ${v.change_note}` : ""}</div>
                    <button className="tbtn" style={{ marginTop: 4 }} onClick={() => handleViewVersion(v.id)}>보기·복원</button>
                  </li>
                ))}
                {versions.length === 0 && <p style={{ color: "var(--ink-muted)" }}>저장된 버전이 없습니다</p>}
              </ul>
            </div>
          )}
        </div>
      </div>
    </AppShell>
  );
}

function tabStyle(active: boolean): React.CSSProperties {
  return active ? { background: "var(--navy)", color: "#fff", borderColor: "var(--navy)" } : {};
}

const inpStyle: React.CSSProperties = { display: "block", width: "100%", padding: 7, borderRadius: 6, border: "1px solid var(--border)", fontSize: 12.5, marginBottom: 6, fontFamily: "inherit" };

function TocList({ editor }: { editor: Editor | null }) {
  if (!editor) return null;
  const headings: { level: number; text: string }[] = [];
  editor.state.doc.descendants((node) => {
    if (node.type.name === "heading") headings.push({ level: node.attrs.level, text: node.textContent });
  });
  if (headings.length === 0) return <p style={{ color: "var(--ink-muted)", fontSize: 12 }}>본문에 제목(H1~H3)을 추가하면 여기 목차가 표시됩니다</p>;
  return (
    <ul style={{ listStyle: "none", padding: 0, margin: 0, fontSize: 12.5 }}>
      {headings.map((h, i) => (
        <li key={i} style={{ paddingLeft: (h.level - 1) * 10, padding: "3px 0" }}>{h.text || "(제목 없음)"}</li>
      ))}
    </ul>
  );
}

function ContextPanel({ context }: { context: { candidate: any; issue: any } | null }) {
  if (!context || !context.candidate) {
    return <p style={{ color: "var(--ink-muted)", fontSize: 12.5 }}>연결된 후보주제가 없는 원고입니다</p>;
  }
  const { candidate, issue } = context;
  return (
    <div style={{ fontSize: 12.5 }}>
      <div style={{ fontWeight: 700, marginBottom: 4 }}>{candidate.title}</div>
      <div style={{ color: "var(--ink-muted)", marginBottom: 8 }}>{FIELD_LABELS[candidate.field_code] ?? candidate.field_code}</div>
      {candidate.recommended_reason && <p>{candidate.recommended_reason}</p>}
      {issue?.analysis?.key_summary && (
        <div className="panel" style={{ background: "var(--panel-2)", marginBottom: 8 }}>
          <div style={{ fontWeight: 700, marginBottom: 4 }}>핵심 이슈 요약</div>
          {issue.analysis.key_summary}
        </div>
      )}
      <div style={{ fontWeight: 700, marginTop: 10, marginBottom: 4 }}>관련 원문</div>
      <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
        {(issue?.members ?? []).map((m: any) => (
          <li key={m.document_id} style={{ padding: "4px 0", borderTop: "1px solid var(--border)" }}>
            <a href={m.origin_url} target="_blank" rel="noreferrer">{m.title}</a>
          </li>
        ))}
        {(!issue || issue.members.length === 0) && <li style={{ color: "var(--ink-muted)" }}>연결된 원문이 없습니다</li>}
      </ul>
    </div>
  );
}

function FootnoteCard({ index, footnote, onVerify, active }: { index: number | null; footnote: FootnoteOut; onVerify: (id: string, matched: boolean) => void; active?: boolean }) {
  return (
    <div className="panel" id={`fn-${footnote.mark_id}`} style={{ marginBottom: 8, fontSize: 12, outline: active ? "2px solid var(--navy)" : undefined }}>
      <div style={{ fontWeight: 700 }}>{index ? `[${index}] ` : ""}{footnote.source_org ?? "출처 미상"}</div>
      <div style={{ color: "var(--ink-muted)", margin: "2px 0" }}>&ldquo;{footnote.anchor_text.slice(0, 60)}&rdquo;</div>
      <a href={footnote.source_url} target="_blank" rel="noreferrer" style={{ fontSize: 11.5 }}>{footnote.source_url}</a>
      {footnote.excerpt && <p style={{ margin: "4px 0", color: "var(--ink-muted)" }}>{footnote.excerpt}</p>}
      <div style={{ color: "var(--ink-muted)" }}>위치: {footnote.location_label ?? "위치 미확인"}</div>
      <div style={{ marginTop: 6, display: "flex", gap: 6, alignItems: "center" }}>
        <span className={`pill ${footnote.verification_status === "matched" ? "rec" : footnote.verification_status === "mismatched" ? "hold" : "review"}`}>
          {footnote.verification_status === "matched" ? "검증완료" : footnote.verification_status === "mismatched" ? "근거불일치" : "미검증"}
        </span>
        {footnote.verification_status !== "matched" && <button className="tbtn" onClick={() => onVerify(footnote.id, true)}>검증 완료로 표시</button>}
        {footnote.verification_status === "not_verified" && <button className="tbtn" onClick={() => onVerify(footnote.id, false)}>근거 불일치로 표시</button>}
      </div>
    </div>
  );
}
