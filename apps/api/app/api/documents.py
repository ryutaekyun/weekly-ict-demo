import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import log_action
from app.core.db import get_db
from app.core.deps import get_current_user, require_roles
from app.models.ai_analysis_run import AIAnalysisRun
from app.models.document_classification import DocumentClassification
from app.models.document_full_text import DocumentFullText
from app.models.document_structured_extract import DocumentStructuredExtract
from app.models.document_value_assessment import DocumentValueAssessment
from app.models.enums import FieldCode, UserRole
from app.models.source import Source
from app.models.source_document import SourceDocument
from app.models.user import User
from app.schemas.analysis import (
    ClassificationOut,
    ClassificationOverrideIn,
    DocumentAnalysisOut,
    FullTextOut,
    StructuredExtractOut,
    ValueAssessmentOut,
    ValueAssessmentOverrideIn,
)
from app.services.classification import override_classification
from app.services.pipeline import run_full_pipeline
from app.services.value_assessment import compute_recency_bucket, override_value_assessment

router = APIRouter(prefix="/documents", tags=["documents"])


def _get_document_or_404(db: Session, document_id: uuid.UUID) -> SourceDocument:
    doc = db.get(SourceDocument, document_id)
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="문서를 찾을 수 없습니다")
    return doc


def _classification_out(row: DocumentClassification) -> ClassificationOut:
    import json

    related = json.loads(row.related_field_codes_json) if row.related_field_codes_json else []
    data = ClassificationOut.model_validate(row).model_dump()
    data["related_field_codes"] = [FieldCode(r) for r in related]
    return ClassificationOut(**data)


def _value_assessment_out(row: DocumentValueAssessment, document: SourceDocument) -> ValueAssessmentOut:
    data = ValueAssessmentOut.model_validate(row).model_dump()
    data["recency_bucket"] = compute_recency_bucket(document.published_at)
    return ValueAssessmentOut(**data)


@router.post("/{document_id}/process", response_model=DocumentAnalysisOut)
def process_document(
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.APPROVER, UserRole.REVIEWER)),
):
    """전문추출 -> 분류 -> 가치판정 -> 구조화를 한 번에 실행(재실행 시 기존 결과를 갱신)."""
    document = _get_document_or_404(db, document_id)
    source = db.get(Source, document.source_id)
    result = run_full_pipeline(db, document, source, prefer_ai=True)

    log_action(
        db,
        actor_user_id=current_user.id,
        action="document.process",
        entity_type="source_document",
        entity_id=document.id,
        detail={
            "classification_method": result.classification.method.value,
            "relevance": result.classification.relevance.value,
            "value_rating": result.value_assessment.rating.value,
            "extraction_status": result.full_text.extraction_status.value,
            "used_summary_fallback": result.used_summary_fallback,
        },
    )
    db.commit()
    return get_document_analysis(document_id, db=db, _=current_user)


@router.get("/{document_id}/analysis", response_model=DocumentAnalysisOut)
def get_document_analysis(
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    document = _get_document_or_404(db, document_id)
    classification = db.query(DocumentClassification).filter_by(document_id=document_id).one_or_none()
    full_text = db.query(DocumentFullText).filter_by(document_id=document_id).one_or_none()
    value_assessment = db.query(DocumentValueAssessment).filter_by(document_id=document_id).one_or_none()
    structured = db.query(DocumentStructuredExtract).filter_by(document_id=document_id).one_or_none()
    ai_runs = db.scalars(
        select(AIAnalysisRun).where(AIAnalysisRun.document_id == document_id).order_by(AIAnalysisRun.started_at.desc())
    ).all()

    full_text_out = None
    if full_text is not None:
        full_text_out = FullTextOut.model_validate(full_text).model_dump()
        full_text_out["full_text"] = None  # 상세 전문은 /full-text 에서 별도 조회
        full_text_out = FullTextOut(**full_text_out)

    return DocumentAnalysisOut(
        document_id=document_id,
        classification=_classification_out(classification) if classification else None,
        full_text=full_text_out,
        value_assessment=_value_assessment_out(value_assessment, document) if value_assessment else None,
        structured_extract=StructuredExtractOut.model_validate(structured) if structured else None,
        ai_runs=list(ai_runs),
    )


@router.get("/{document_id}/full-text", response_model=FullTextOut)
def get_document_full_text(
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    _get_document_or_404(db, document_id)
    full_text = db.query(DocumentFullText).filter_by(document_id=document_id).one_or_none()
    if full_text is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="전문 추출 결과가 없습니다")
    return full_text


@router.patch("/{document_id}/classification", response_model=ClassificationOut)
def patch_classification(
    document_id: uuid.UUID,
    payload: ClassificationOverrideIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.APPROVER, UserRole.REVIEWER)),
):
    document = _get_document_or_404(db, document_id)
    updated = override_classification(
        db,
        document,
        user_id=current_user.id,
        primary_field_code=payload.primary_field_code,
        related_field_codes=payload.related_field_codes,
        relevance=payload.relevance,
        reason=payload.reason,
    )
    log_action(
        db,
        actor_user_id=current_user.id,
        action="document.classification.override",
        entity_type="source_document",
        entity_id=document.id,
        detail={"primary_field_code": payload.primary_field_code.value if payload.primary_field_code else None,
                "relevance": payload.relevance.value, "reason": payload.reason},
    )
    db.commit()
    return _classification_out(updated)


@router.patch("/{document_id}/value-assessment", response_model=ValueAssessmentOut)
def patch_value_assessment(
    document_id: uuid.UUID,
    payload: ValueAssessmentOverrideIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.APPROVER, UserRole.REVIEWER)),
):
    document = _get_document_or_404(db, document_id)
    updated = override_value_assessment(db, document, rating=payload.rating, reason=payload.reason)
    log_action(
        db,
        actor_user_id=current_user.id,
        action="document.value_assessment.override",
        entity_type="source_document",
        entity_id=document.id,
        detail={"rating": payload.rating.value, "reason": payload.reason},
    )
    db.commit()
    return _value_assessment_out(updated, document)
