"""원문 기반 핵심 내용 구조화 — 보고서 집필에 바로 쓸 수 있도록 원문을 분해한다.

규칙 기반(AI 미설정) 모드의 원칙: 원문에서 패턴매칭으로 직접 뽑아낼 수 있는 항목(핵심 수치,
일정, 기관명)만 채우고, 해석이 필요한 항목(쟁점, 예상 산업영향)은 비워 둔다. 원문에 없는
내용을 추정해 사실처럼 쓰지 않기 위함이다 — 빈 칸은 "AI 미설정으로 생성하지 않음"으로 남긴다.
"""

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.ai_analysis_run import AIAnalysisRun
from app.models.document_structured_extract import DocumentStructuredExtract
from app.models.enums import ClassificationMethod, VerificationStatus
from app.models.source import Source
from app.models.source_document import SourceDocument
from app.services.ai_service import AIServiceError, extract_json_object, get_ai_provider
from app.services.field_taxonomy import taxonomy_as_prompt_context

RULE_BASED_NOT_GENERATED_NOTE = "AI 미설정으로 생성하지 않음(규칙 기반 모드는 해석성 항목을 추정하지 않음)"

FIGURE_PATTERN = re.compile(
    r"(?P<value>\$?[\d][\d,]*\.?\d*)\s*(?P<unit>%|percent|million|billion|GHz|MHz|nm|건|명|조\s?원|억\s?원)",
    re.IGNORECASE,
)
DATE_PATTERN = re.compile(
    r"(?P<date>(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s*\d{4}|\d{4}-\d{2}-\d{2})"
)
DATE_LABEL_HINTS = [
    ("effective date", "시행일"),
    ("comment", "의견수렴 마감일"),
    ("deadline", "마감일"),
    ("시행", "시행일"),
    ("발효", "시행일"),
    ("마감", "마감일"),
]


def _extract_key_figures(text: str, limit: int = 8) -> list[dict]:
    results = []
    for m in FIGURE_PATTERN.finditer(text):
        start = max(0, m.start() - 60)
        context = text[start : m.end() + 20].replace("\n", " ").strip()
        results.append({"value": m.group("value"), "unit": m.group("unit"), "source_quote": context})
        if len(results) >= limit:
            break
    return results


def _extract_key_dates(text: str, limit: int = 8) -> list[dict]:
    results = []
    for m in DATE_PATTERN.finditer(text):
        start = max(0, m.start() - 80)
        context = text[start : m.end() + 20].replace("\n", " ").strip()
        label = "날짜(구분 불명확)"
        lower_context = context.lower()
        for hint, mapped_label in DATE_LABEL_HINTS:
            if hint in lower_context:
                label = mapped_label
                break
        results.append({"date": m.group("date"), "label": label, "source_quote": context})
        if len(results) >= limit:
            break
    return results


_SUMMARY_FIELD_PATTERN = re.compile(r"\bSUMMARY\s*:\s*", re.IGNORECASE)


def _first_paragraphs(text: str, max_len: int = 500) -> str:
    """원문 앞부분에서 핵심 내용을 뽑는다.

    주의(실데이터 검증에서 발견): Federal Register PDF는 인쇄판 지면을 그대로 잘라 제공하므로,
    한 문서의 PDF 앞부분에 직전의 무관한 다른 고시(notice)의 꼬리 문단이 섞여 들어오는 경우가
    있다. 연방관보 문서는 거의 예외 없이 "SUMMARY:" 필드로 그 문서 자신의 요지를 명시하므로,
    본문에서 "SUMMARY:"를 찾으면 그 뒤부터를 핵심 내용으로 쓴다 — 앞쪽의 무관한 꼬리 문단을
    "이 문서의 핵심 내용"으로 잘못 뽑는 것을 막기 위함이다.
    """
    match = _SUMMARY_FIELD_PATTERN.search(text[:4000])
    search_text = text[match.end() :] if match else text

    paragraphs = [p.strip() for p in search_text.split("\n\n") if p.strip()]
    combined = ""
    for p in paragraphs:
        if len(combined) + len(p) > max_len and combined:
            break
        combined = f"{combined}\n\n{p}" if combined else p
    return combined[:max_len].strip()


def extract_structured_rule_based(*, text: str, source: Source) -> dict:
    key_content = _first_paragraphs(text) or None
    return {
        "key_content": key_content,
        "background_purpose": None,
        "policy_tech_change": None,
        "key_figures": _extract_key_figures(text),
        "key_dates": _extract_key_dates(text),
        "related_entities": [source.org_name] if source.org_name else [],
        "contested_points": None,
        "expected_impact_facts": None,
        "expected_impact_ai_analysis": None,
        "open_questions": RULE_BASED_NOT_GENERATED_NOTE,
        "source_citations": {
            "key_content": "원문 첫 문단(들)에서 그대로 발췌",
            "key_figures": "정규식으로 원문에서 직접 매칭(수치+단위 패턴)",
            "key_dates": "정규식으로 원문에서 직접 매칭(날짜 패턴 + 주변 문맥 키워드)",
        },
    }


def _build_ai_prompt(document: SourceDocument, source: Source, text: str) -> tuple[str, str]:
    system_prompt = (
        "당신은 ICT 주간기술동향 보고서 작성을 돕는 분석 보조원입니다. 주어진 원문만 근거로 핵심 "
        "내용을 구조화하십시오. 원문에 없는 사실(수치·날짜·기관명 등)을 절대 추정해서 만들어내지 "
        "마십시오. 사실과 당신의 해석(예상 영향)은 반드시 구분해서 답하고, 각 항목이 원문의 어느 "
        "부분에 근거하는지 source_citations에 짧게 인용하십시오. 반드시 JSON으로만 답하십시오.\n"
        '{"key_content": "", "background_purpose": "", "policy_tech_change": "", '
        '"key_figures": [{"value": "", "unit": "", "source_quote": ""}], '
        '"key_dates": [{"date": "", "label": "발표일|시행일|의견수렴마감일|기타", "source_quote": ""}], '
        '"related_entities": [""], "contested_points": "원문에서 확인되는 경우에만, 없으면 null", '
        '"expected_impact_facts": "원문에 명시된 사실만", '
        '"expected_impact_ai_analysis": "당신의 분석(사실과 구분해 작성)", '
        '"open_questions": "", "source_citations": {"<필드명>": "<근거 설명>"}}\n\n'
        f"[ICT 9대 분야 정의 — 맥락 참고용]\n{taxonomy_as_prompt_context()}"
    )
    user_prompt = (
        f"[제목]\n{document.title}\n\n[발행기관]\n{source.org_name}\n\n"
        f"[발표일]\n{document.published_at}\n\n[원문]\n{text[:8000]}"
    )
    return system_prompt, user_prompt


def extract_structured_with_ai(db: Session, document: SourceDocument, source: Source, text: str) -> dict | None:
    provider = get_ai_provider()
    started_at = datetime.now(timezone.utc)
    if provider is None:
        db.add(
            AIAnalysisRun(
                document_id=document.id, task_type="structured_extract", provider=None, model=None,
                analysis_version="ai-v1", status="skipped_no_api_key", input_char_count=len(text),
                started_at=started_at, finished_at=started_at,
            )
        )
        return None

    system_prompt, user_prompt = _build_ai_prompt(document, source, text)
    run = AIAnalysisRun(
        document_id=document.id, task_type="structured_extract", provider=provider.name, model=provider.model,
        analysis_version="ai-v1", status="failed", input_char_count=len(text), started_at=started_at,
    )
    db.add(run)
    try:
        result = provider.complete_json(system_prompt, user_prompt)
        parsed = extract_json_object(result.text)
        run.status = "success"
    except AIServiceError as exc:
        run.status = "failed"
        run.error_message = str(exc)
        return None
    finally:
        run.finished_at = datetime.now(timezone.utc)
    return parsed


def run_structured_extract(
    db: Session, document: SourceDocument, source: Source, *, text: str, prefer_ai: bool = True
) -> DocumentStructuredExtract:
    generated_by = ClassificationMethod.RULE_BASED
    parsed: dict | None = None
    if prefer_ai:
        parsed = extract_structured_with_ai(db, document, source, text)
        if parsed is not None:
            generated_by = ClassificationMethod.AI
    if parsed is None:
        parsed = extract_structured_rule_based(text=text, source=source)
        generated_by = ClassificationMethod.RULE_BASED

    existing = db.query(DocumentStructuredExtract).filter_by(document_id=document.id).one_or_none()
    if existing is None:
        existing = DocumentStructuredExtract(document_id=document.id)
        db.add(existing)

    existing.key_content = parsed.get("key_content")
    existing.background_purpose = parsed.get("background_purpose")
    existing.policy_tech_change = parsed.get("policy_tech_change")
    existing.key_figures_json = json.dumps(parsed.get("key_figures") or [], ensure_ascii=False)
    existing.key_dates_json = json.dumps(parsed.get("key_dates") or [], ensure_ascii=False)
    existing.related_entities_json = json.dumps(parsed.get("related_entities") or [], ensure_ascii=False)
    existing.contested_points = parsed.get("contested_points")
    existing.expected_impact_facts = parsed.get("expected_impact_facts")
    existing.expected_impact_ai_analysis = parsed.get("expected_impact_ai_analysis")
    existing.open_questions = parsed.get("open_questions")
    existing.source_citations_json = json.dumps(parsed.get("source_citations") or {}, ensure_ascii=False)
    existing.verification_status = VerificationStatus.UNVERIFIED
    existing.generated_by = generated_by

    db.flush()
    return existing
