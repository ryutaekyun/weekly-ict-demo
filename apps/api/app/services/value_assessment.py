"""문서별 실무 활용가치 판정 — 우선검토/일반검토/관련성낮음/추가확인필요.

중요(지시사항 원문): "RFI, 의견수렴 공고, 규제 예고 등은 실제로 중요한 정책 신호일 수 있으므로
문서 유형만으로 일괄 삭제하지 마세요." — 그래서 이 모듈은 DocumentType(NOTICE/PROPOSED RULE 등)
만으로 감점하지 않는다. 대신 본문에 "Paperwork Reduction Act / OMB control number / Agency
Information Collection Activities" 같은 '행정 절차성 문구'가 실질적 내용 없이 지배적인 경우에만
낮게 평가한다 — 그 외의 RFI·의견수렴·규제예고는 내용을 근거로 그대로 평가한다.
"""

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.document_value_assessment import DocumentValueAssessment
from app.models.enums import ClassificationMethod, ClassificationRelevance, DocumentType, UsageValueRating
from app.models.source import Source
from app.models.source_document import SourceDocument

MIN_CONTENT_CHARS_SUFFICIENT = 300
RECENCY_7D = 7
RECENCY_30D = 30
RECENCY_90D = 90

SUBSTANTIVE_DOCUMENT_TYPES = {
    DocumentType.LAW,
    DocumentType.POLICY,
    DocumentType.STANDARD,
    DocumentType.REPORT,
    DocumentType.PAPER,
    DocumentType.TECH_ANNOUNCEMENT,
    DocumentType.STATISTICS,
}

# 문구 자체가 아니라 "이 문구들이 본문 전체를 지배하는지"를 보는 용도 — 등장 자체로 감점하지 않는다.
ADMINISTRATIVE_BOILERPLATE_PATTERNS = [
    "paperwork reduction act",
    "omb control number",
    "agency information collection activities",
    "information collection request",
    "systems of records notice",
    "privacy act of 1974",
]

# 실질적 정책·기술 신호 — 행정 문구가 섞여 있어도 이런 표현이 있으면 "단순 공고"로 보지 않는다
SUBSTANTIVE_SIGNAL_PATTERNS = [
    "propose", "proposed rule", "requirement", "standard", "deadline", "effective date",
    "규제", "규정", "시행", "의무", "기준", "지침", "제재", "허가", "면제",
]


def compute_recency_bucket(published_at: datetime | None, *, reference_time: datetime | None = None) -> str:
    """'지금 보는 시점' 기준으로 매번 다시 계산한다 — DB에 저장해 두지 않는다(저장하면 시간이 지나며 값이 거짓이 된다)."""
    if published_at is None:
        return "unknown"
    ref = reference_time or datetime.now(timezone.utc)
    if published_at.tzinfo is None:
        published_at = published_at.replace(tzinfo=timezone.utc)
    age_days = (ref - published_at).days
    if age_days < 0:
        return "unknown"
    if age_days <= RECENCY_7D:
        return "within_7d"
    if age_days <= RECENCY_30D:
        return "within_30d"
    if age_days <= RECENCY_90D:
        return "within_90d"
    return "older"


def _is_administrative_boilerplate_dominated(text: str) -> bool:
    lower = text.lower()
    boilerplate_hits = sum(lower.count(p) for p in ADMINISTRATIVE_BOILERPLATE_PATTERNS)
    if boilerplate_hits == 0:
        return False
    substantive_hits = sum(lower.count(p) for p in SUBSTANTIVE_SIGNAL_PATTERNS)
    # 행정 문구가 3회 이상 등장 + 실질 신호가 그보다 확연히 적으면 "행정공고가 지배적"으로 판단
    return boilerplate_hits >= 3 and substantive_hits < boilerplate_hits


def _first_evidence_sentence(text: str, max_len: int = 220) -> str | None:
    sentences = re.split(r"(?<=[.!?。])\s+", text.strip())
    for s in sentences:
        s = s.strip()
        if len(s) >= 40:
            return s[:max_len]
    return text[:max_len].strip() or None


@dataclass
class ValueAssessmentResult:
    rating: UsageValueRating
    reasoning: str
    evidence_quote: str | None
    criteria: dict


def assess_document_value_rule_based(
    *, document: SourceDocument, source: Source, text: str, is_relevant_to_9_fields: bool
) -> ValueAssessmentResult:
    criteria: dict[str, bool | str] = {}

    # ① ICT 9대 분야 직접 관련성
    criteria["direct_field_relevance"] = is_relevant_to_9_fields

    # ② 정책·산업·기술적 중요성(문서유형 휴리스틱)
    criteria["policy_industry_importance"] = document.document_type in SUBSTANTIVE_DOCUMENT_TYPES

    # ③ 단순 행정공고 vs 실질 변화 구분 — 문서유형이 아니라 본문 내용으로 판단
    boilerplate_dominated = _is_administrative_boilerplate_dominated(text)
    criteria["not_routine_administrative_notice"] = not boilerplate_dominated

    # ④ 원문 내용의 충분성
    sufficient_content = len(text.strip()) >= MIN_CONTENT_CHARS_SUFFICIENT
    criteria["sufficient_content"] = sufficient_content

    # ⑤ 시의성(발표일 기준, 조회 시점마다 재계산되는 버킷을 그대로 신호로 사용)
    recency = compute_recency_bucket(document.published_at)
    criteria["recency_bucket"] = recency
    timely = recency in ("within_7d", "within_30d", "within_90d")

    # ⑥ 출처 신뢰성·1차 출처 여부
    criteria["reliable_primary_source"] = bool(source.is_primary_source) and source.reliability_tier <= 2

    evidence_quote = _first_evidence_sentence(text)

    reasons: list[str] = []
    if not is_relevant_to_9_fields:
        reasons.append("ICT 9대 분야 분류 결과가 '관련성 낮음/분류보류'임")
    if boilerplate_dominated:
        reasons.append("Paperwork Reduction Act/OMB 등 행정 절차성 문구가 본문을 지배하고 실질적 정책 신호가 부족함")
    if not sufficient_content:
        reasons.append(f"원문 내용이 {len(text.strip())}자로 분석에 충분하지 않음(기준 {MIN_CONTENT_CHARS_SUFFICIENT}자)")
    if document.published_at is None:
        reasons.append("발표일을 확인할 수 없어 시의성 판단 보류")

    if not is_relevant_to_9_fields or boilerplate_dominated:
        rating = UsageValueRating.LOW_RELEVANCE
    elif not sufficient_content or document.published_at is None:
        rating = UsageValueRating.NEEDS_MORE_INFO
    elif criteria["policy_industry_importance"] and criteria["reliable_primary_source"] and timely:
        rating = UsageValueRating.PRIORITY
        reasons.insert(0, "정책/기술적 중요성이 있는 문서유형이고 1차 출처이며 최근(90일 이내) 발표됨")
    else:
        rating = UsageValueRating.GENERAL
        reasons.insert(0, "9대 분야와 관련되고 분석 가능한 내용은 있으나 우선검토 기준(중요도·1차출처·시의성)을 모두 충족하지는 않음")

    reasoning = "규칙 기반(AI 미설정) 판정: " + "; ".join(reasons)
    return ValueAssessmentResult(rating=rating, reasoning=reasoning, evidence_quote=evidence_quote, criteria=criteria)


def run_value_assessment(
    db: Session, document: SourceDocument, source: Source, *, text: str, is_relevant_to_9_fields: bool
) -> DocumentValueAssessment:
    result = assess_document_value_rule_based(
        document=document, source=source, text=text, is_relevant_to_9_fields=is_relevant_to_9_fields
    )
    existing = db.query(DocumentValueAssessment).filter_by(document_id=document.id).one_or_none()
    if existing is None:
        existing = DocumentValueAssessment(document_id=document.id)
        db.add(existing)
    existing.rating = result.rating
    existing.reasoning = result.reasoning
    existing.evidence_quote = result.evidence_quote
    existing.method = ClassificationMethod.RULE_BASED
    existing.is_researcher_overridden = False
    existing.criteria_json = json.dumps(result.criteria, ensure_ascii=False, default=str)
    db.flush()
    return existing


def override_value_assessment(
    db: Session, document: SourceDocument, *, rating: UsageValueRating, reason: str | None
) -> DocumentValueAssessment:
    existing = db.query(DocumentValueAssessment).filter_by(document_id=document.id).one_or_none()
    if existing is None:
        existing = DocumentValueAssessment(document_id=document.id, criteria_json=None)
        db.add(existing)
    existing.rating = rating
    existing.reasoning = reason
    existing.method = ClassificationMethod.RESEARCHER
    existing.is_researcher_overridden = True
    db.flush()
    return existing
