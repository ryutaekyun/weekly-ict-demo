"""AI 분석 API — 연구원이 명시적으로 요청하고, 결과를 검토·수정한 뒤 후보주제·원고에 반영한다.

AI는 후보주제의 상태(선정·확정)나 기존 원고·승인·각주를 바꾸지 못한다. 원고 삽입도 연구원이 고른 문장만, 현재 원고 버전(lock_version)을 확인하고
끝에 덧붙이며, 삽입된 각주는 항상 '미검증'으로 시작한다.
"""

import json
import uuid
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import log_action
from app.core.db import get_db
from app.core.deps import get_current_user, require_roles
from app.models.ai_analysis import AIAnalysis, AIClaim
from app.models.candidate import Candidate
from app.models.enums import FieldCode, UserRole
from app.models.issue_cluster import IssueCluster
from app.models.manuscript import Manuscript
from app.models.manuscript_footnote import ManuscriptFootnote
from app.models.source_document import SourceDocument
from app.models.user import User
from app.services import ai_analysis_service as svc
from app.services import manuscript_footnote_service, manuscript_service
from app.services.manuscript_service import ManuscriptConflictError

router = APIRouter(prefix="/ai", tags=["ai"])
APPROVER_ROLES = (UserRole.ADMIN, UserRole.APPROVER)


class RunIn(BaseModel):
    kind: str
    target_id: uuid.UUID
    document_ids: list[uuid.UUID] | None = None
    force: bool = False
    confirm_cost: bool = False


class ClaimReviewIn(BaseModel):
    action: str  # verify | reject | reset
    note: str | None = None


class CandidateFromAIIn(BaseModel):
    title: str = Field(min_length=2, max_length=500)
    summary: str | None = None
    recommended_reason: str | None = None
    attach_to_candidate_id: uuid.UUID | None = None  # 중복이면 새로 만들지 않고 기존 후보주제에 분석을 연결


class InsertIn(BaseModel):
    manuscript_id: uuid.UUID
    claim_ids: list[uuid.UUID] = Field(min_length=1)
    lock_version: int
    edited_texts: dict[str, str] = {}  # claim_id → 연구원이 고친 문장(없으면 AI 원문 그대로)


def _aware(dt: datetime | None) -> datetime | None:
    return dt.replace(tzinfo=timezone.utc) if dt and dt.tzinfo is None else dt


def _claim_out(c: AIClaim) -> dict:
    return {
        "id": str(c.id), "section_key": c.section_key, "seq": c.seq, "text": c.text, "claim_type": c.claim_type,
        "evidence": json.loads(c.evidence_json or "[]"), "evidence_status": c.evidence_status, "check_note": c.check_note,
        "researcher_status": c.researcher_status, "researcher_note": c.researcher_note,
        "verified_at": c.verified_at.isoformat() if c.verified_at else None, "inserted_manuscript_id": str(c.inserted_manuscript_id) if c.inserted_manuscript_id else None,
    }


def _analysis_out(db: Session, a: AIAnalysis, *, detail: bool = True, reused: bool = False) -> dict:
    result = json.loads(a.result_json) if a.result_json else {}
    out = {
        "id": str(a.id), "kind": a.kind, "target_type": a.target_type, "target_id": str(a.target_id), "status": a.status,
        "verification_status": a.verification_status, "provider": a.provider, "model": a.model, "is_mock": a.is_mock,
        "prompt_version": a.prompt_version, "source_fingerprint": a.source_fingerprint,
        "input_documents": json.loads(a.input_documents_json or "[]"), "input_tokens": a.input_tokens, "output_tokens": a.output_tokens,
        "est_input_tokens": a.est_input_tokens, "est_cost_usd": a.est_cost_usd, "actual_cost_usd": a.actual_cost_usd,
        "error_message": a.error_message, "notes": json.loads(a.notes_json or "[]"), "started_at": _aware(a.started_at).isoformat(),
        "finished_at": _aware(a.finished_at).isoformat() if a.finished_at else None, "reused": reused,
        "hold_reason": result.get("hold_reason"), "linked_candidate_id": str(a.linked_candidate_id) if a.linked_candidate_id else None,
        "public_approved_at": _aware(a.public_approved_at).isoformat() if a.public_approved_at else None,
        "stats": svc.claim_stats(db, a.id),
        "notice": "AI 생성 결과입니다. 연구원이 원문 근거를 확인하기 전에는 검증 완료가 아니며, 실제 발간 승인본이 아닌 검토용 초안입니다."
                  + (" (모의 응답 — 개발·테스트용, 실제 AI 분석이 아닙니다)" if a.is_mock else ""),
    }
    if detail:
        claims = {str(c.id): _claim_out(c) for c in db.scalars(select(AIClaim).where(AIClaim.analysis_id == a.id).order_by(AIClaim.section_key, AIClaim.seq)).all()}
        out["sections"] = [{**s, "claims": [claims[i] for i in s.get("claim_ids", []) if i in claims]} for s in result.get("sections", [])]
        out["model_notes"] = result.get("model_notes", [])
    return out


@router.get("/status")
def ai_status(_: User = Depends(get_current_user)):
    return svc.ai_status()


@router.post("/estimate")
def estimate(payload: RunIn, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    try:
        return svc.estimate(db, payload.kind, payload.target_id, payload.document_ids)
    except svc.AIRequestError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.post("/analyses")
def run(payload: RunIn, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    try:
        analysis, reused = svc.run_analysis(db, current_user, payload.kind, payload.target_id, document_ids=payload.document_ids,
                                            force=payload.force, confirm_cost=payload.confirm_cost)
    except svc.AIConfigError as exc:  # 키 미설정 — 가짜 결과를 만들지 않는다
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": "ai_not_configured", "message": str(exc)}) from exc
    except svc.AIRequestError as exc:
        detail = {"code": exc.code, "message": exc.detail} if exc.code else exc.detail
        raise HTTPException(status_code=exc.status_code, detail=detail) from exc
    if not reused:
        log_action(db, actor_user_id=current_user.id, action="ai.analysis", entity_type="ai_analysis", entity_id=analysis.id,
                   detail={"kind": payload.kind, "target_id": str(payload.target_id), "status": analysis.status, "provider": analysis.provider, "model": analysis.model,
                           "tokens": [analysis.input_tokens, analysis.output_tokens], "docs": len(json.loads(analysis.input_documents_json or "[]"))})
    db.commit()
    return _analysis_out(db, analysis, reused=reused)


@router.get("/analyses")
def list_analyses(
    target_id: uuid.UUID | None = None, kind: str | None = None, limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db), _: User = Depends(get_current_user),
):
    q = select(AIAnalysis).order_by(AIAnalysis.created_at.desc()).limit(limit)
    if target_id:
        q = q.where(AIAnalysis.target_id == target_id)
    if kind:
        q = q.where(AIAnalysis.kind == kind)
    return [_analysis_out(db, a, detail=False) for a in db.scalars(q).all()]


def _get_analysis(db: Session, analysis_id: uuid.UUID) -> AIAnalysis:
    a = db.get(AIAnalysis, analysis_id)
    if a is None:
        raise HTTPException(status_code=404, detail="AI 분석 결과를 찾을 수 없습니다")
    return a


@router.get("/analyses/{analysis_id}")
def get_analysis(analysis_id: uuid.UUID, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return _analysis_out(db, _get_analysis(db, analysis_id))


@router.post("/analyses/{analysis_id}/cancel")
def cancel(analysis_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    a = _get_analysis(db, analysis_id)
    if a.requested_by_user_id != current_user.id and current_user.role not in APPROVER_ROLES:
        raise HTTPException(status_code=403, detail="요청한 사용자만 취소할 수 있습니다")
    if a.status != "running":
        raise HTTPException(status_code=409, detail="진행 중인 분석만 취소할 수 있습니다")
    a.cancelled = True
    log_action(db, actor_user_id=current_user.id, action="ai.cancel", entity_type="ai_analysis", entity_id=a.id)
    db.commit()
    return _analysis_out(db, a, detail=False)


@router.post("/claims/{claim_id}/review")
def review_claim(claim_id: uuid.UUID, payload: ClaimReviewIn, db: Session = Depends(get_db), current_user: User = Depends(require_roles(*svc.ALLOWED_ROLES))):
    claim = db.get(AIClaim, claim_id)
    if claim is None:
        raise HTTPException(status_code=404, detail="문장을 찾을 수 없습니다")
    try:
        svc.review_claim(db, claim, current_user, payload.action, payload.note)
    except svc.AIRequestError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    log_action(db, actor_user_id=current_user.id, action=f"ai.claim.{payload.action}", entity_type="ai_claim", entity_id=claim.id, detail={"note": payload.note})
    db.commit()
    a = db.get(AIAnalysis, claim.analysis_id)
    return {"claim": _claim_out(claim), "verification_status": a.verification_status, "stats": svc.claim_stats(db, a.id)}


@router.post("/analyses/{analysis_id}/public-approval")
def approve_public(analysis_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(require_roles(*APPROVER_ROLES))):
    """연구원이 검토를 마친 결과만 정적 공개 스냅샷에 넣을 수 있게 승인한다(개인정보·내부정보는 내보내기에서 다시 걸러낸다)."""
    a = _get_analysis(db, analysis_id)
    if a.is_mock:
        raise HTTPException(status_code=409, detail="모의 응답은 공개할 수 없습니다")
    if a.verification_status != "researcher_verified":
        raise HTTPException(status_code=409, detail="사실 문장을 모두 연구원이 검증한 결과만 공개 승인할 수 있습니다")
    a.public_approved_at, a.public_approved_by_user_id = datetime.now(timezone.utc), current_user.id
    log_action(db, actor_user_id=current_user.id, action="ai.public_approve", entity_type="ai_analysis", entity_id=a.id)
    db.commit()
    return _analysis_out(db, a, detail=False)


# ------------------------------------------------------------ 후보주제 반영 ----
@router.post("/analyses/{analysis_id}/candidate")
def candidate_from_analysis(analysis_id: uuid.UUID, payload: CandidateFromAIIn, db: Session = Depends(get_db), current_user: User = Depends(require_roles(*svc.ALLOWED_ROLES))):
    """AI 후보주제 제안을 연구원이 고친 내용으로 후보로 등록하거나, 이미 있는 후보주제에 분석을 연결한다. 후보 상태는 AI가 정하지 않는다."""
    a = _get_analysis(db, analysis_id)
    if a.kind != "candidate":
        raise HTTPException(status_code=422, detail="후보주제 제안 분석만 후보로 등록할 수 있습니다")
    if payload.attach_to_candidate_id:
        cand = db.get(Candidate, payload.attach_to_candidate_id)
        if cand is None or cand.issue_cluster_id != a.target_id:
            raise HTTPException(status_code=422, detail="같은 이슈의 기존 후보주제에만 연결할 수 있습니다")
        a.linked_candidate_id = cand.id
        created = False
    else:
        cluster = db.get(IssueCluster, a.target_id)
        docs = json.loads(a.input_documents_json or "[]")
        first = db.get(SourceDocument, uuid.UUID(docs[0]["id"])) if docs else None
        cand = Candidate(
            issue_cluster_id=cluster.id, field_code=cluster.field_code if isinstance(cluster.field_code, FieldCode) else FieldCode(cluster.field_code),
            title=payload.title.strip(), summary=payload.summary, source_document_id=first.id if first else None,
            announced_date=first.published_at.date() if first and first.published_at else None,
            recommended_reason=(payload.recommended_reason or "") + "\n[AI 제안을 연구원이 검토·수정해 등록 — 근거 검증은 별도 확인 필요]",
            created_by_user_id=current_user.id,
        )
        db.add(cand)
        db.flush()
        a.linked_candidate_id = cand.id
        created = True
    log_action(db, actor_user_id=current_user.id, action="ai.candidate_link", entity_type="candidate", entity_id=cand.id,
               detail={"analysis_id": str(a.id), "created": created, "title": cand.title})
    db.commit()
    return {"candidate_id": str(cand.id), "created": created}


# ------------------------------------------------------------ 원고 삽입 ----
@router.post("/analyses/{analysis_id}/insert")
def insert_into_manuscript(analysis_id: uuid.UUID, payload: InsertIn, db: Session = Depends(get_db), current_user: User = Depends(require_roles(*svc.ALLOWED_ROLES))):
    """연구원이 고른 문장만 원고 끝에 덧붙인다. 기존 본문·승인·각주는 바꾸지 않고, 삽입 각주는 미검증으로 시작한다."""
    a = _get_analysis(db, analysis_id)
    if a.kind not in ("draft", "outline"):
        raise HTTPException(status_code=422, detail="초안·목차 제안만 원고에 삽입할 수 있습니다")
    manuscript = db.get(Manuscript, payload.manuscript_id)
    if manuscript is None:
        raise HTTPException(status_code=404, detail="원고를 찾을 수 없습니다")
    if manuscript.author_user_id != current_user.id and current_user.role not in (*APPROVER_ROLES, UserRole.RESEARCHER):
        raise HTTPException(status_code=403, detail="원고를 수정할 권한이 없습니다")
    claims = [c for c in db.scalars(select(AIClaim).where(AIClaim.analysis_id == a.id, AIClaim.id.in_(payload.claim_ids))).all()]
    if len(claims) != len(set(payload.claim_ids)):
        raise HTTPException(status_code=422, detail="선택한 문장이 이 분석에 속하지 않습니다")
    by_id = {str(c.id): c for c in claims}
    try:
        body = json.loads(manuscript.body_json) if manuscript.body_json else {"type": "doc", "content": []}
    except json.JSONDecodeError:
        body = {"type": "doc", "content": []}
    body.setdefault("content", [])
    plain_add: list[str] = []
    footnote_count = 0
    for cid in payload.claim_ids:
        c = by_id[str(cid)]
        text = (payload.edited_texts.get(str(cid)) or c.text).strip()
        marks: list[dict] = []
        evs = [e for e in json.loads(c.evidence_json or "[]") if e.get("document_id") and e.get("quote")]
        if c.claim_type == "fact" and evs and c.evidence_status != "not_found":
            ev = evs[0]
            mark_id = f"fn-{uuid.uuid4().hex[:12]}"
            doc = db.get(SourceDocument, uuid.UUID(ev["document_id"]))
            manuscript_footnote_service.create_footnote(
                db, manuscript_id=manuscript.id, created_by_user_id=current_user.id, mark_id=mark_id, anchor_text=text[:500],
                source_url=(doc.origin_url if doc and doc.origin_url else ev.get("url") or ""), source_document_id=doc.id if doc else None,
                source_org=None, excerpt=ev["quote"][:1500], location_label=ev.get("location"), published_at=doc.published_at if doc else None,
            )
            marks = [{"type": "footnoteMark", "attrs": {"footnoteId": mark_id}}]
            footnote_count += 1
        node = {"type": "paragraph", "content": [{"type": "text", "text": text, **({"marks": marks} if marks else {})}]}
        body["content"].append(node)
        plain_add.append(text)
        c.inserted_manuscript_id = manuscript.id
    try:
        manuscript_service.update_manuscript_body(
            db, manuscript, title=None, title_en=None, body_json=json.dumps(body, ensure_ascii=False),
            body=((manuscript.body or "") + "\n" + "\n".join(plain_add)).strip(), lock_version=payload.lock_version,
            actor_user_id=current_user.id, change_note=f"AI 제안 {len(claims)}문장 삽입(연구원 선택·미검증)", is_milestone=False,
        )
    except ManuscriptConflictError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    log_action(db, actor_user_id=current_user.id, action="ai.insert", entity_type="manuscript", entity_id=manuscript.id,
               detail={"analysis_id": str(a.id), "claims": len(claims), "footnotes": footnote_count})
    db.commit()
    return {"manuscript_id": str(manuscript.id), "lock_version": manuscript.lock_version, "inserted": len(claims), "footnotes_created": footnote_count,
            "note": "삽입된 문장과 각주는 자동으로 검증 완료가 되지 않습니다. 원고 작업실에서 근거를 확인하세요."}
