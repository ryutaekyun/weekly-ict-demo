import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.audit import log_action
from app.core.db import get_db
from app.core.deps import get_current_user, require_roles
from app.models.ai_analysis_run import AIAnalysisRun
from app.models.document_classification import DocumentClassification
from app.models.document_full_text import DocumentFullText
from app.models.document_structured_extract import DocumentStructuredExtract
from app.models.document_value_assessment import DocumentValueAssessment
from app.models.candidate import Candidate
from app.models.enums import (
    CandidateStatus, ClassificationRelevance, DocumentType, ExtractionStatus, FieldCode, UsageValueRating, UserRole,
)
from app.models.issue_cluster_document import IssueClusterDocument
from app.models.source import Source
from app.models.source_document import SourceDocument
from app.models.user import User
from app.schemas.analysis import (
    ClassificationOut,
    ClassificationOverrideIn,
    DocumentAnalysisOut,
    DocumentListItemOut,
    DocumentListOut,
    FullTextOut,
    StructuredExtractOut,
    ValueAssessmentOut,
    ValueAssessmentOverrideIn,
)
from app.services.classification import override_classification
from app.services.link_quality import check_link, classify_url
from app.services.pipeline import run_full_pipeline
from app.services.value_assessment import compute_recency_bucket, override_value_assessment

router = APIRouter(prefix="/documents", tags=["documents"])


def _get_document_or_404(db: Session, document_id: uuid.UUID) -> SourceDocument:
    doc = db.get(SourceDocument, document_id)
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="문서를 찾을 수 없습니다")
    return doc


def _document_list_query():
    """목록·단건 메타 조회가 공유하는 조인 — 1:1(또는 1:0) 관계뿐이라 행이 불어나지 않는다."""
    return (
        select(SourceDocument, DocumentClassification, DocumentFullText, DocumentValueAssessment, Source, IssueClusterDocument)
        .outerjoin(DocumentClassification, DocumentClassification.document_id == SourceDocument.id)
        .outerjoin(DocumentFullText, DocumentFullText.document_id == SourceDocument.id)
        .outerjoin(DocumentValueAssessment, DocumentValueAssessment.document_id == SourceDocument.id)
        .outerjoin(Source, Source.id == SourceDocument.source_id)
        .outerjoin(IssueClusterDocument, IssueClusterDocument.document_id == SourceDocument.id)
    )


def _document_list_item(row) -> DocumentListItemOut:
    doc, classification, full_text, value_assessment, source, issue_membership = row
    link = classify_url(doc.origin_url)
    return DocumentListItemOut(
        link_state=link["state"], link_blocked=link["blocked"], link_note=link["note"], is_pdf=link["is_pdf"],
        id=doc.id,
        title=doc.title,
        origin_url=doc.origin_url,
        attachment_url=doc.attachment_url,
        source_id=doc.source_id,
        source_name=source.name if source else "",
        source_org_name=source.org_name if source else "",
        country_code=doc.country_code,
        published_at=doc.published_at,
        collected_at=doc.collected_at,
        document_type=doc.document_type,
        status=doc.status,
        primary_field_code=classification.primary_field_code if classification else None,
        relevance=classification.relevance if classification else None,
        classification_method=classification.method if classification else None,
        value_rating=value_assessment.rating if value_assessment else None,
        extraction_status=full_text.extraction_status if full_text else None,
        issue_cluster_id=issue_membership.issue_cluster_id if issue_membership else None,
        language=doc.language, version_no=doc.version_no or 1, is_latest=bool(doc.is_latest), external_id=doc.external_id,
    )


@router.get("", response_model=DocumentListOut)
def list_documents(
    field_code: FieldCode | None = None,
    country_code: str | None = None,
    document_type: DocumentType | None = None,
    source_id: uuid.UUID | None = None,
    relevance: ClassificationRelevance | None = None,
    value_rating: UsageValueRating | None = None,
    published_after: datetime | None = None,
    published_before: datetime | None = None,
    q: str | None = None,
    language: str | None = None,
    collected_after: datetime | None = None,
    extraction_status: ExtractionStatus | None = None,
    has_full_text: bool | None = None,
    has_issue: bool | None = None,
    has_candidate: bool | None = None,
    candidate_status: CandidateStatus | None = None,
    sort: Literal["published_desc", "published_asc", "title", "collected_desc"] = "published_desc",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=300),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """전체 수집자료 검색·필터·페이지네이션. 분야 필터는 출처 고정 분야(SourceDocument.field_code)가
    아니라 document_classifications.primary_field_code를 기준으로 한다."""
    stmt = _document_list_query().where(SourceDocument.is_latest.is_(True))  # 같은 문서의 개정판은 최신본만 목록에 보이고, 이전 버전은 상세의 버전 이력에 보존된다
    if language is not None:
        stmt = stmt.where(SourceDocument.language == language)
    if collected_after is not None:
        stmt = stmt.where(SourceDocument.collected_at >= collected_after)
    if field_code is not None:
        stmt = stmt.where(DocumentClassification.primary_field_code == field_code)
    if country_code is not None:
        stmt = stmt.where(SourceDocument.country_code == country_code)
    if document_type is not None:
        stmt = stmt.where(SourceDocument.document_type == document_type)
    if source_id is not None:
        stmt = stmt.where(SourceDocument.source_id == source_id)
    if relevance is not None:
        stmt = stmt.where(DocumentClassification.relevance == relevance)
    if value_rating is not None:
        stmt = stmt.where(DocumentValueAssessment.rating == value_rating)
    if published_after is not None:
        stmt = stmt.where(SourceDocument.published_at >= published_after)
    if published_before is not None:
        stmt = stmt.where(SourceDocument.published_at <= published_before)
    if q:
        like = f"%{q}%"  # 제목·원문(전문) 검색 — 전문은 확보된 자료만 대상이다
        full_text_hit = select(DocumentFullText.document_id).where(DocumentFullText.full_text.ilike(like))
        stmt = stmt.where(or_(SourceDocument.title.ilike(like), SourceDocument.id.in_(full_text_hit)))
    if extraction_status is not None:
        stmt = stmt.where(DocumentFullText.extraction_status == extraction_status)
    if has_full_text is True:  # 원문 확보 여부: 전문 또는 부분 추출이 있는 자료
        stmt = stmt.where(DocumentFullText.extraction_status.in_([ExtractionStatus.SUCCESS, ExtractionStatus.PARTIAL]))
    elif has_full_text is False:
        stmt = stmt.where(or_(DocumentFullText.extraction_status.is_(None),
                              DocumentFullText.extraction_status.notin_([ExtractionStatus.SUCCESS, ExtractionStatus.PARTIAL])))
    if has_issue is True:
        stmt = stmt.where(IssueClusterDocument.issue_cluster_id.is_not(None))
    elif has_issue is False:
        stmt = stmt.where(IssueClusterDocument.issue_cluster_id.is_(None))
    if has_candidate is not None or candidate_status is not None:
        cand = select(Candidate.issue_cluster_id).where(Candidate.issue_cluster_id.is_not(None))
        if candidate_status is not None:
            cand = cand.where(Candidate.status == candidate_status)
        if has_candidate is False:
            stmt = stmt.where(or_(IssueClusterDocument.issue_cluster_id.is_(None), IssueClusterDocument.issue_cluster_id.notin_(cand)))
        else:
            stmt = stmt.where(IssueClusterDocument.issue_cluster_id.in_(cand))

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0

    if sort == "published_asc":
        stmt = stmt.order_by(SourceDocument.published_at.asc().nulls_last(), SourceDocument.collected_at.desc())
    elif sort == "title":
        stmt = stmt.order_by(SourceDocument.title.asc())
    elif sort == "collected_desc":
        stmt = stmt.order_by(SourceDocument.collected_at.desc())
    else:
        stmt = stmt.order_by(SourceDocument.published_at.desc().nulls_last(), SourceDocument.collected_at.desc())
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    rows = db.execute(stmt).all()

    return DocumentListOut(items=[_document_list_item(r) for r in rows], total=total, page=page, page_size=page_size)


@router.get("/facets")
def document_facets(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """필터 선택지(국가·발행기관·발표 기간) — 실제 수집 자료에서 계산한다."""
    countries = db.execute(select(SourceDocument.country_code, func.count()).where(SourceDocument.country_code.is_not(None))
                           .group_by(SourceDocument.country_code).order_by(func.count().desc())).all()
    orgs = db.execute(select(Source.id, Source.org_name, func.count(SourceDocument.id)).join(SourceDocument, SourceDocument.source_id == Source.id)
                      .group_by(Source.id, Source.org_name).order_by(func.count(SourceDocument.id).desc())).all()
    lo, hi = db.execute(select(func.min(SourceDocument.published_at), func.max(SourceDocument.published_at))).one()
    langs = db.execute(select(SourceDocument.language, func.count()).where(SourceDocument.language.is_not(None)).group_by(SourceDocument.language).order_by(func.count().desc())).all()
    return {
        "languages": [{"code": c, "count": n} for c, n in langs],
        "countries": [{"code": c, "count": n} for c, n in countries], "sources": [{"id": str(i), "name": name, "count": n} for i, name, n in orgs],
        "published_min": lo.isoformat() if lo else None, "published_max": hi.isoformat() if hi else None,
    }


@router.post("/{document_id}/check-link")
def check_document_link(document_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """원문 링크를 실제로 접속해 점검한다(삭제·잘못된 주소와 접속 제한을 구분). 외부 사이트에는 조회 요청만 보낸다."""
    doc = _get_document_or_404(db, document_id)
    result = check_link(doc.origin_url)
    log_action(db, actor_user_id=user.id, action="document.check_link", entity_type="source_document", entity_id=doc.id,
               detail={"state": result["state"], "http_status": result["http_status"]})
    db.commit()
    return {**result, "origin_url": doc.origin_url, "classification": classify_url(doc.origin_url)}


@router.get("/{document_id}", response_model=DocumentListItemOut)
def get_document_meta(
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """목록과 동일한 형태의 단건 메타데이터 — 상세화면 헤더용(전문·분류 상세는 /analysis, /full-text 참고)."""
    stmt = _document_list_query().where(SourceDocument.id == document_id)
    row = db.execute(stmt).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="문서를 찾을 수 없습니다")
    return _document_list_item(row)


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
