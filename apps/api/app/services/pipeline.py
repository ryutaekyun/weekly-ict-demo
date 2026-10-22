"""문서 1건에 대한 Phase 2-2 파이프라인 전체(전문추출 -> 분류 -> 가치판정 -> 구조화) 실행.

API 엔드포인트와 일괄 재처리 스크립트(app/reprocess_documents.py)가 공통으로 쓴다.
"""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models.document_full_text import DocumentFullText
from app.models.document_structured_extract import DocumentStructuredExtract
from app.models.document_value_assessment import DocumentValueAssessment
from app.models.enums import ClassificationRelevance, ExtractionStatus, UsageValueRating
from app.models.source import Source
from app.models.source_document import SourceDocument
from app.services.classification import DocumentClassification, run_classification
from app.services.extraction import run_extraction
from app.services.structured_extract import run_structured_extract
from app.services.value_assessment import run_value_assessment


@dataclass
class PipelineResult:
    full_text: DocumentFullText
    classification: DocumentClassification
    value_assessment: DocumentValueAssessment
    structured_extract: DocumentStructuredExtract | None
    used_summary_fallback: bool


def run_full_pipeline(db: Session, document: SourceDocument, source: Source, *, prefer_ai: bool = True) -> PipelineResult:
    full_text_record = run_extraction(db, document)

    used_summary_fallback = True
    text_for_analysis = ""
    if full_text_record.extraction_status == ExtractionStatus.SUCCESS and full_text_record.full_text:
        text_for_analysis = full_text_record.full_text
        used_summary_fallback = False
    else:
        text_for_analysis = f"{document.title}\n\n{document.raw_text or ''}".strip()

    classification = run_classification(db, document, text=text_for_analysis, prefer_ai=prefer_ai)
    is_relevant = classification.relevance == ClassificationRelevance.MATCHED

    value_assessment = run_value_assessment(
        db, document, source, text=text_for_analysis, is_relevant_to_9_fields=is_relevant
    )

    structured = None
    if is_relevant and value_assessment.rating != UsageValueRating.LOW_RELEVANCE:
        structured = run_structured_extract(db, document, source, text=text_for_analysis, prefer_ai=prefer_ai)

    db.commit()
    return PipelineResult(
        full_text=full_text_record,
        classification=classification,
        value_assessment=value_assessment,
        structured_extract=structured,
        used_summary_fallback=used_summary_fallback,
    )
