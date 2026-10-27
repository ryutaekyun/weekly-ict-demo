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
from app.models.ai_analysis import AIAnalysis, AIClaim, AIInsertion, AIPriceSetting
from app.models.candidate import Candidate
from app.models.enums import FieldCode, UserRole
from app.models.issue_cluster import IssueCluster
from app.models.manuscript import Manuscript
from app.models.manuscript_footnote import ManuscriptFootnote
from app.models.source_document import SourceDocument
from app.models.user import User
from app.services import ai_analysis_service as svc
from app.services import ai_insertion_service, ai_service

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
    position: dict | None = None  # {"mode": "end"} | {"mode": "after_index", "index": n} | {"mode": "after_heading", "heading_text": "..."}


class InsertionReviewIn(BaseModel):
    resolution: str  # updated | no_impact | needs_check | removed
    note: str


class UndoIn(BaseModel):
    lock_version: int


class PriceIn(BaseModel):
    provider: str
    model: str = Field(min_length=2, max_length=80)
    input_per_mtok: float = Field(ge=0)
    output_per_mtok: float = Field(ge=0)
    effective_date: date
    source_note: str | None = None


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
        "error_message": a.error_message, "error_code": a.error_code, "provider_request_sent": a.provider_request_sent, "pricing_version": a.pricing_version,
        "cancel_note": a.cancel_note, "source_changed_during_run": a.source_changed_during_run, "notes": json.loads(a.notes_json or "[]"), "started_at": _aware(a.started_at).isoformat(),
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


@router.get("/usage")
def usage(days: int = Query(1, ge=1, le=90), scope: str = "me", db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    svc.expire_stale(db)
    if scope == "all":
        if current_user.role not in APPROVER_ROLES:
            raise HTTPException(status_code=403, detail="전체 사용량은 승인권자·관리자만 볼 수 있습니다")
        return svc.usage_summary(db, None, days)
    return svc.usage_summary(db, current_user, days)


@router.get("/pricing")
def list_pricing(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    rows = db.scalars(select(AIPriceSetting).order_by(AIPriceSetting.provider, AIPriceSetting.model, AIPriceSetting.version.desc())).all()
    return [{"id": str(r.id), "provider": r.provider, "model": r.model, "input_per_mtok": r.input_per_mtok, "output_per_mtok": r.output_per_mtok,
             "effective_date": r.effective_date.isoformat(), "source_note": r.source_note, "version": r.version, "is_active": r.is_active} for r in rows]


@router.put("/pricing")
def set_pricing(payload: PriceIn, db: Session = Depends(get_db), current_user: User = Depends(require_roles(UserRole.ADMIN))):
    """관리자가 제공자·모델별 단가를 갱신한다. 이전 단가는 보존(비활성)하고 새 버전을 만든다 — 과거 분석의 비용 기준이 바뀌지 않는다."""
    prev = db.scalars(select(AIPriceSetting).where(AIPriceSetting.provider == payload.provider, AIPriceSetting.model == payload.model)).all()
    for r in prev:
        r.is_active = False
    row = AIPriceSetting(provider=payload.provider, model=payload.model, input_per_mtok=payload.input_per_mtok, output_per_mtok=payload.output_per_mtok,
                         effective_date=payload.effective_date, source_note=payload.source_note, version=max((r.version for r in prev), default=0) + 1,
                         is_active=True, updated_by_user_id=current_user.id)
    db.add(row)
    db.flush()
    log_action(db, actor_user_id=current_user.id, action="ai.pricing_update", entity_type="ai_price_setting", entity_id=row.id,
               detail={"provider": row.provider, "model": row.model, "version": row.version, "in": row.input_per_mtok, "out": row.output_per_mtok})
    db.commit()
    return {"id": str(row.id), "version": row.version}


@router.post("/diagnostics")
def diagnostics(current_user: User = Depends(require_roles(UserRole.ADMIN))):
    """관리자 전용 연결 진단 — 키가 있을 때만 모델 목록 조회(토큰을 쓰지 않는 호출)로 설정한 모델이 실제 사용 가능한지 확인한다.
    키가 없으면 '연결 미검증'으로 돌려주며 성공으로 보고하지 않는다."""
    provider = ai_service.get_ai_provider()
    if provider is None:
        return {"connection": "not_configured", "verified": False, "message": "연결 미검증 — " + "; ".join(ai_service.configuration_gaps() or ["설정 없음"])}
    if provider.name == "mock":
        return {"connection": "mock", "verified": False, "message": "모의 공급자입니다 — 실제 연결을 검증하지 않았습니다(연결 미검증)", "model": provider.model}
    try:
        models = provider.list_models()  # type: ignore[attr-defined]
    except ai_service.AIServiceError as exc:
        return {"connection": "failed", "verified": False, "error_code": exc.code, "message": f"{exc.user_message} | {str(exc)[:300]}", "model": provider.model}
    available = provider.model in models
    return {"connection": "ok" if available else "model_unavailable", "verified": available, "model": provider.model, "available_models": models[:60],
            "message": "키로 조회한 모델 목록에 설정한 모델이 있습니다(모델 목록 조회만 확인했고 분석 호출은 하지 않았습니다)" if available else
            f"설정한 모델 '{provider.model}'이(가) 이 키로 조회되는 목록에 없습니다 — AI_MODEL을 확인하세요"}


class ApprovalIn(BaseModel):
    kind: str
    target_id: uuid.UUID
    max_cost_usd: float = Field(gt=0, le=50)
    valid_minutes: int = Field(60, ge=5, le=1440)
    note: str | None = Field(None, max_length=300)


class EvaluationIn(BaseModel):
    scores: dict[str, str]
    semantic_mismatch_cases: int = 0
    insufficient_evidence_cases: int = 0
    wrong_source_cases: int = 0
    notes: str | None = None


@router.post("/approvals")
def create_approval(payload: ApprovalIn, db: Session = Depends(get_db), current_user: User = Depends(require_roles(UserRole.ADMIN))):
    """관리자가 실제(비모의) AI 호출 1건을 승인한다 — 대상·모델·예산 상한을 지정하며 한 번 쓰면 소멸한다."""
    try:
        a = svc.create_approval(db, current_user, payload.kind, payload.target_id, payload.max_cost_usd, payload.valid_minutes, payload.note)
    except svc.AIRequestError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.detail} if exc.code else exc.detail) from exc
    log_action(db, actor_user_id=current_user.id, action="ai.approval_create", entity_type="ai_call_approval", entity_id=a.id,
               detail={"kind": a.kind, "target_id": str(a.target_id), "model": a.model, "max_cost_usd": a.max_cost_usd})
    db.commit()
    return svc.approval_out(a)


@router.get("/approvals")
def list_approvals(db: Session = Depends(get_db), _: User = Depends(require_roles(UserRole.ADMIN))):
    from app.models.ai_analysis import AICallApproval

    return [svc.approval_out(a) for a in db.scalars(select(AICallApproval).order_by(AICallApproval.created_at.desc()).limit(50)).all()]


@router.delete("/approvals/{approval_id}")
def revoke_approval(approval_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(require_roles(UserRole.ADMIN))):
    from app.models.ai_analysis import AICallApproval

    a = db.get(AICallApproval, approval_id)
    if a is None or a.used_at is not None:
        raise HTTPException(status_code=404, detail="취소할 수 있는 미사용 승인이 없습니다")
    a.revoked = True
    log_action(db, actor_user_id=current_user.id, action="ai.approval_revoke", entity_type="ai_call_approval", entity_id=a.id)
    db.commit()
    return svc.approval_out(a)


@router.get("/evaluation-criteria")
def evaluation_criteria(_: User = Depends(get_current_user)):
    return svc.EVAL_CRITERIA


@router.get("/evaluation-summary")
def evaluation_summary(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return svc.evaluation_summary(db)


@router.post("/analyses/{analysis_id}/evaluation")
def save_evaluation(analysis_id: uuid.UUID, payload: EvaluationIn, db: Session = Depends(get_db), current_user: User = Depends(require_roles(*svc.ALLOWED_ROLES))):
    a = _get_analysis(db, analysis_id)
    try:
        ev = svc.save_evaluation(db, a, current_user, payload.scores, {"semantic_mismatch_cases": payload.semantic_mismatch_cases,
                                                                      "insufficient_evidence_cases": payload.insufficient_evidence_cases, "wrong_source_cases": payload.wrong_source_cases}, payload.notes)
    except svc.AIRequestError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    log_action(db, actor_user_id=current_user.id, action="ai.evaluation", entity_type="ai_analysis", entity_id=a.id, detail={"is_mock": a.is_mock})
    db.commit()
    return {"id": str(ev.id), "is_mock": ev.is_mock}


@router.get("/analyses/{analysis_id}/evaluations")
def list_evaluations(analysis_id: uuid.UUID, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    from app.models.ai_analysis import AIEvaluation

    return [{"id": str(e.id), "is_mock": e.is_mock, "scores": json.loads(e.scores_json), "semantic_mismatch_cases": e.semantic_mismatch_cases,
             "insufficient_evidence_cases": e.insufficient_evidence_cases, "wrong_source_cases": e.wrong_source_cases, "notes": e.notes, "created_at": e.created_at.isoformat()}
            for e in db.scalars(select(AIEvaluation).where(AIEvaluation.analysis_id == analysis_id).order_by(AIEvaluation.created_at)).all()]


@router.post("/preflight")
def preflight(payload: RunIn, db: Session = Depends(get_db), _: User = Depends(require_roles(UserRole.ADMIN))):
    """관리자 전용 첫 호출 사전 점검 — 유료 생성 호출 없이 전달 데이터·실측 토큰(키가 있을 때, 무료 Token Counting)·최대 비용·권장 승인 상한을 확인한다."""
    try:
        return svc.preflight(db, payload.kind, payload.target_id, payload.document_ids)
    except svc.AIRequestError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


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
    svc.expire_stale(db)
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
    svc.expire_stale(db)
    return _analysis_out(db, _get_analysis(db, analysis_id))


@router.post("/analyses/{analysis_id}/cancel")
def cancel(analysis_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    a = _get_analysis(db, analysis_id)
    if a.requested_by_user_id != current_user.id and current_user.role not in APPROVER_ROLES:
        raise HTTPException(status_code=403, detail="요청한 사용자만 취소할 수 있습니다")
    if a.status != "running":
        raise HTTPException(status_code=409, detail="진행 중인 분석만 취소할 수 있습니다")
    a.cancelled = True
    a.cancel_note = ("DB 상태만 취소합니다 — 외부 제공자에게 요청이 이미 전달되었으므로 호출을 중단할 수 없고 비용이 발생할 수 있습니다. 응답이 오면 결과는 저장하지 않습니다."
                     if a.provider_request_sent else "제공자 호출 전에 취소되었습니다")
    log_action(db, actor_user_id=current_user.id, action="ai.cancel", entity_type="ai_analysis", entity_id=a.id, detail={"provider_request_sent": a.provider_request_sent})
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


# ------------------------------------------------------------ 원고 삽입·삽입 취소·원문 변경 재검토 ----
def _get_manuscript(db: Session, manuscript_id: uuid.UUID, user: User) -> Manuscript:
    manuscript = db.get(Manuscript, manuscript_id)
    if manuscript is None:
        raise HTTPException(status_code=404, detail="원고를 찾을 수 없습니다")
    if manuscript.author_user_id != user.id and user.role not in (*APPROVER_ROLES, UserRole.RESEARCHER):
        raise HTTPException(status_code=403, detail="원고를 수정할 권한이 없습니다")
    return manuscript


@router.post("/analyses/{analysis_id}/insert")
def insert_into_manuscript(analysis_id: uuid.UUID, payload: InsertIn, db: Session = Depends(get_db), current_user: User = Depends(require_roles(*svc.ALLOWED_ROLES))):
    """연구원이 고른 문장만 원하는 위치(커서 문단 뒤·소제목 아래·원고 끝)에 덧붙인다. 기존 본문·승인·각주는 바꾸지 않고(현재 lock_version 확인),
    삽입 문장은 AI 표시와 미검증 각주로 시작하며 삽입 기록(AI 원문·연구원 최종 문장·원문 버전)을 남긴다."""
    a = _get_analysis(db, analysis_id)
    if a.kind not in ("draft", "outline"):
        raise HTTPException(status_code=422, detail="초안·목차 제안만 원고에 삽입할 수 있습니다")
    manuscript = _get_manuscript(db, payload.manuscript_id, current_user)
    found = {c.id: c for c in db.scalars(select(AIClaim).where(AIClaim.analysis_id == a.id, AIClaim.id.in_(payload.claim_ids))).all()}
    if len(found) != len(set(payload.claim_ids)):
        raise HTTPException(status_code=422, detail="선택한 문장이 이 분석에 속하지 않습니다")
    claims = [found[i] for i in payload.claim_ids]
    out = ai_insertion_service.insert_claims(db, a, manuscript, current_user, claims, lock_version=payload.lock_version,
                                             edited_texts=payload.edited_texts, position=payload.position)
    log_action(db, actor_user_id=current_user.id, action="ai.insert", entity_type="manuscript", entity_id=manuscript.id,
               detail={"analysis_id": str(a.id), "claims": len(claims), "footnotes": out["footnotes_created"], "position": payload.position or {"mode": "end"}})
    db.commit()
    return {**out, "manuscript_id": str(manuscript.id), "lock_version": manuscript.lock_version,
            "note": "삽입된 문장과 각주는 자동으로 검증 완료가 되지 않습니다. 원고 작업실에서 근거를 확인하세요."}


@router.get("/manuscripts/{manuscript_id}/insertions")
def list_insertions(manuscript_id: uuid.UUID, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    if db.get(Manuscript, manuscript_id) is None:
        raise HTTPException(status_code=404, detail="원고를 찾을 수 없습니다")
    return ai_insertion_service.list_for_manuscript(db, manuscript_id)


def _get_insertion(db: Session, insertion_id: uuid.UUID) -> AIInsertion:
    ins = db.get(AIInsertion, insertion_id)
    if ins is None:
        raise HTTPException(status_code=404, detail="AI 삽입 기록을 찾을 수 없습니다")
    return ins


@router.post("/insertions/{insertion_id}/undo")
def undo_insertion(insertion_id: uuid.UUID, payload: UndoIn, db: Session = Depends(get_db), current_user: User = Depends(require_roles(*svc.ALLOWED_ROLES))):
    ins = _get_insertion(db, insertion_id)
    manuscript = _get_manuscript(db, ins.manuscript_id, current_user)
    out = ai_insertion_service.undo_insertion(db, ins, manuscript, current_user, payload.lock_version)
    log_action(db, actor_user_id=current_user.id, action="ai.insert_undo", entity_type="manuscript", entity_id=manuscript.id, detail={"insertion_id": str(ins.id)})
    db.commit()
    return {**out, "lock_version": manuscript.lock_version}


@router.post("/insertions/{insertion_id}/review")
def review_insertion(insertion_id: uuid.UUID, payload: InsertionReviewIn, db: Session = Depends(get_db), current_user: User = Depends(require_roles(*svc.ALLOWED_ROLES))):
    """원문 변경 후 연구원의 재검토 판단(수정 반영 완료·영향 없음·추가 확인 필요·문장 삭제/대체)을 검토자·일시·사유·확인한 원문 버전과 함께 기록한다."""
    ins = _get_insertion(db, insertion_id)
    manuscript = _get_manuscript(db, ins.manuscript_id, current_user)
    ai_insertion_service.review_insertion(db, ins, manuscript, current_user, payload.resolution, payload.note)
    log_action(db, actor_user_id=current_user.id, action="ai.insertion_review", entity_type="ai_insertion", entity_id=ins.id,
               detail={"resolution": payload.resolution, "note": payload.note, "manuscript_id": str(manuscript.id)})
    db.commit()
    return ai_insertion_service.insertion_out(db, ins)
