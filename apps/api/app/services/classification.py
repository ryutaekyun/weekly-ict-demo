"""문서별 ICT 9대 분야 자동 분류.

핵심 변경점(Phase 2-2): Phase 2-1까지는 수집 시점에 "출처의 고정 분야"를 그대로
SourceDocument.field_code에 복사했다(예: NIST 출처 문서는 전부 보안·블록체인, OSTP 출처
문서는 전부 ICT융합기술). 이 모듈은 문서 하나하나의 제목·요약·본문을 분야별 정의/키워드와
대조해 실제 분야를 판정하고, 그 결과를 DocumentClassification에 별도로 저장한다
(SourceDocument.field_code는 과거 호환을 위해 그대로 둔다 — 더 이상 "진짜 분야"가 아니다).
"""

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.ai_analysis_run import AIAnalysisRun
from app.models.document_classification import DocumentClassification, DocumentClassificationHistory
from app.models.enums import ClassificationMethod, ClassificationRelevance, FieldCode
from app.models.source_document import SourceDocument
from app.services.ai_service import AIServiceError, get_ai_provider
from app.services.field_taxonomy import FIELD_DEFINITIONS, taxonomy_as_prompt_context

# 상위 분야로 인정하는 최소 점수, 연관분야로 인정하는 '주 분야 대비' 최소 비율
MIN_SCORE_FOR_MATCH = 2.5
RELATED_FIELD_RATIO = 0.4
RELATED_FIELD_MIN_SCORE = 1.5
ANALYSIS_VERSION_RULE = "rule-v1"
ANALYSIS_VERSION_AI = "ai-v1"


@dataclass
class FieldScore:
    field_code: FieldCode
    score: float
    matched: list[tuple[float, str]]


def _tokenize_lower(text: str) -> str:
    return f" {text.lower()} "


def score_document_against_fields(text: str) -> list[FieldScore]:
    hay = _tokenize_lower(text)
    results: list[FieldScore] = []
    for field_code, definition in FIELD_DEFINITIONS.items():
        score = 0.0
        matched: list[tuple[float, str]] = []
        for weight, keyword in definition.keywords:
            kw = keyword.lower()
            # 구문(여러 단어)은 부분 문자열로, 단일 영단어는 단어 경계로 매칭해 오탐을 줄인다
            if " " in kw:
                hits = hay.count(kw)
            else:
                hits = len(re.findall(rf"(?<![a-z0-9]){re.escape(kw)}(?![a-z0-9])", hay))
            if hits:
                score += weight * hits
                matched.append((weight, keyword))
        results.append(FieldScore(field_code=field_code, score=score, matched=matched))
    results.sort(key=lambda r: r.score, reverse=True)
    return results


def classify_document_rule_based(text: str) -> dict:
    scores = score_document_against_fields(text)
    top = scores[0]

    if top.score < MIN_SCORE_FOR_MATCH:
        reasoning = (
            f"9대 분야 키워드 매칭 점수가 모두 기준(최소 {MIN_SCORE_FOR_MATCH:g}점) 미만이다 — 분류 보류. "
            f"최고 점수: {top.field_code.value}={top.score:.1f}"
        )
        return {
            "primary_field_code": None,
            "related_field_codes": [],
            "relevance": ClassificationRelevance.PENDING_REVIEW,
            "confidence": None,
            "reasoning": reasoning,
            "matched_keywords": [],
        }

    related = [
        s.field_code.value
        for s in scores[1:]
        if s.score >= RELATED_FIELD_MIN_SCORE and s.score >= top.score * RELATED_FIELD_RATIO
    ]
    confidence = min(1.0, top.score / (top.score + 4.0))  # 규칙 기반 휴리스틱 — 확률이 아님을 reasoning에 명시
    matched_str = ", ".join(f"'{kw}'(가중치 {w:g})" for w, kw in top.matched[:6])
    reasoning = (
        f"규칙 기반(키워드 매칭) 판정: {top.field_code.value} 분야 키워드가 {matched_str} 등 "
        f"{len(top.matched)}종 매칭되어 점수 {top.score:.1f}로 1위. 이 신뢰도는 AI 분석이 아니라 "
        "단순 키워드 가중합 기반 휴리스틱이다."
    )
    return {
        "primary_field_code": top.field_code,
        "related_field_codes": related,
        "relevance": ClassificationRelevance.MATCHED,
        "confidence": confidence,
        "reasoning": reasoning,
        "matched_keywords": [{"keyword": kw, "weight": w} for w, kw in top.matched],
    }


def _build_ai_prompt(title: str, text: str) -> tuple[str, str]:
    system_prompt = (
        "당신은 ICT 기술동향 보고서를 작성하는 연구기관의 분야 분류 보조원입니다. "
        "주어진 분야 정의(포함/제외/경계 사례 포함)를 근거로만 판단하고, 반드시 아래 JSON 스키마로만 "
        "답하십시오. 다른 설명 문장을 추가하지 마십시오.\n"
        '{"primary_field": "<9대 분야 코드 또는 null>", "related_fields": ["<코드>", ...], '
        '"relevance": "matched|low_relevance|pending_review", "confidence": 0.0~1.0, '
        '"reasoning": "<판단 근거를 2~3문장으로>"}\n\n'
        f"[ICT 9대 분야 정의]\n{taxonomy_as_prompt_context()}"
    )
    user_prompt = f"[문서 제목]\n{title}\n\n[문서 본문/요약]\n{text[:8000]}"
    return system_prompt, user_prompt


def classify_document_with_ai(db: Session, document: SourceDocument, text: str) -> dict | None:
    provider = get_ai_provider()
    started_at = datetime.now(timezone.utc)
    if provider is None:
        db.add(
            AIAnalysisRun(
                document_id=document.id,
                task_type="classification",
                provider=None,
                model=None,
                analysis_version=ANALYSIS_VERSION_AI,
                status="skipped_no_api_key",
                input_char_count=len(text),
                started_at=started_at,
                finished_at=started_at,
            )
        )
        return None

    system_prompt, user_prompt = _build_ai_prompt(document.title, text)
    run = AIAnalysisRun(
        document_id=document.id,
        task_type="classification",
        provider=provider.name,
        model=provider.model,
        analysis_version=ANALYSIS_VERSION_AI,
        status="failed",
        input_char_count=len(text),
        started_at=started_at,
    )
    db.add(run)
    try:
        from app.services.ai_service import extract_json_object

        result = provider.complete_json(system_prompt, user_prompt)
        parsed = extract_json_object(result.text)
        run.status = "success"
        run.finished_at = datetime.now(timezone.utc)
    except AIServiceError as exc:
        run.status = "failed"
        run.error_message = str(exc)
        run.finished_at = datetime.now(timezone.utc)
        return None

    primary_raw = parsed.get("primary_field")
    try:
        primary_field_code = FieldCode(primary_raw) if primary_raw else None
    except ValueError:
        primary_field_code = None
    related_raw = parsed.get("related_fields") or []
    related_field_codes = [r for r in related_raw if r in FieldCode._value2member_map_ and r != primary_raw]
    try:
        relevance = ClassificationRelevance(parsed.get("relevance", "pending_review"))
    except ValueError:
        relevance = ClassificationRelevance.PENDING_REVIEW
    confidence = parsed.get("confidence")
    if not isinstance(confidence, (int, float)):
        confidence = None

    return {
        "primary_field_code": primary_field_code,
        "related_field_codes": related_field_codes,
        "relevance": relevance,
        "confidence": confidence,
        "reasoning": parsed.get("reasoning"),
        "matched_keywords": [],
    }


def run_classification(
    db: Session, document: SourceDocument, *, text: str, prefer_ai: bool = True
) -> DocumentClassification:
    """문서 하나를 분류하고 DocumentClassification(+이력)을 생성/갱신해 반환한다.

    text는 호출부가 준비한다 — 보통 전문 추출 결과가 있으면 전문, 없으면 제목+요약을 합친 텍스트.
    """
    result: dict | None = None
    method = ClassificationMethod.RULE_BASED
    if prefer_ai:
        result = classify_document_with_ai(db, document, text)
        if result is not None:
            method = ClassificationMethod.AI
    if result is None:
        result = classify_document_rule_based(text)
        method = ClassificationMethod.RULE_BASED

    existing = db.query(DocumentClassification).filter_by(document_id=document.id).one_or_none()
    now = datetime.now(timezone.utc)

    history = DocumentClassificationHistory(
        document_id=document.id,
        changed_by_user_id=None,
        previous_primary_field_code=existing.primary_field_code if existing else None,
        new_primary_field_code=result["primary_field_code"],
        previous_relevance=existing.relevance if existing else None,
        new_relevance=result["relevance"],
        method=method,
        reason=None,
    )
    db.add(history)

    if existing is None:
        existing = DocumentClassification(document_id=document.id, classified_at=now)
        db.add(existing)

    existing.primary_field_code = result["primary_field_code"]
    existing.related_field_codes_json = json.dumps(result["related_field_codes"], ensure_ascii=False)
    existing.relevance = result["relevance"]
    existing.confidence = result["confidence"]
    existing.method = method
    existing.reasoning = result["reasoning"]
    existing.matched_keywords_json = json.dumps(result["matched_keywords"], ensure_ascii=False)
    existing.is_researcher_overridden = False
    existing.classified_at = now

    db.flush()
    return existing


def override_classification(
    db: Session,
    document: SourceDocument,
    *,
    user_id,
    primary_field_code: FieldCode | None,
    related_field_codes: list[FieldCode],
    relevance: ClassificationRelevance,
    reason: str | None,
) -> DocumentClassification:
    """연구원이 분류 결과를 직접 수정한다 — AI/규칙 기반 결과를 덮어쓰고 이력에 남긴다."""
    existing = db.query(DocumentClassification).filter_by(document_id=document.id).one_or_none()
    now = datetime.now(timezone.utc)

    history = DocumentClassificationHistory(
        document_id=document.id,
        changed_by_user_id=user_id,
        previous_primary_field_code=existing.primary_field_code if existing else None,
        new_primary_field_code=primary_field_code,
        previous_relevance=existing.relevance if existing else None,
        new_relevance=relevance,
        method=ClassificationMethod.RESEARCHER,
        reason=reason,
    )
    db.add(history)

    if existing is None:
        existing = DocumentClassification(document_id=document.id, classified_at=now)
        db.add(existing)

    existing.primary_field_code = primary_field_code
    existing.related_field_codes_json = json.dumps([f.value for f in related_field_codes], ensure_ascii=False)
    existing.relevance = relevance
    existing.confidence = None
    existing.method = ClassificationMethod.RESEARCHER
    existing.reasoning = reason
    existing.is_researcher_overridden = True
    existing.classified_at = now

    db.flush()
    return existing
