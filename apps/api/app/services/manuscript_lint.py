"""원고 작성 점검(무료·규칙 기반) — 연구원이 쓴 문장과 연결한 근거를 대조해 실수를 알려 준다. 문장을 고치거나 검증 상태를 바꾸지 않는다.

점검 항목: 근거 발췌문과 문장 속 날짜·수치 일치, 발표일·시행일·준수 시한 혼동·단위·부등호·부정 반전 가능성(의미 불일치 신호),
근거 없는 수치 문장, 근거 미검증 각주, 발췌문 없는 각주, 중복 문장, 중복 출처.
"""

import re
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.manuscript import Manuscript
from app.models.manuscript_footnote import ManuscriptFootnote
from app.services import ai_evidence

SENT_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")
HAS_FACT = re.compile(r"\d")


def sentences(text: str) -> list[str]:
    return [s.strip() for s in SENT_SPLIT.split(text or "") if len(s.strip()) >= 8]


def lint(db: Session, manuscript: Manuscript) -> dict:
    warnings: list[dict] = []

    def add(kind: str, severity: str, message: str, sentence: str | None = None, footnote_id: uuid.UUID | None = None):
        warnings.append({"type": kind, "severity": severity, "message": message, "sentence": (sentence or "")[:200] or None, "footnote_id": str(footnote_id) if footnote_id else None})

    body = manuscript.body or ""
    foot = db.scalars(select(ManuscriptFootnote).where(ManuscriptFootnote.manuscript_id == manuscript.id).order_by(ManuscriptFootnote.created_at)).all()
    anchored = {ai_evidence.normalize(f.anchor_text) for f in foot}
    for f in foot:
        label = f.anchor_text[:60]
        if not f.excerpt:
            add("no_excerpt", "warn", "근거 발췌문이 비어 있어 문장과 원문을 대조할 수 없습니다", f.anchor_text, f.id)
        else:
            problems = ai_evidence.check_values(f.anchor_text, f.excerpt)
            if problems:
                add("value_mismatch", "error", "문장의 " + ", ".join(problems) + " 이(가) 연결한 근거 발췌문에 없습니다 — 날짜·수치·단위를 원문과 대조하세요", f.anchor_text, f.id)
            for flag in ai_evidence.semantic_flags(f.anchor_text, f.excerpt):
                add("semantic_risk", "warn", flag, f.anchor_text, f.id)
        if f.verification_status.value == "not_verified":
            add("unverified", "info", f"근거 미검증 문장입니다 — 원문 확인 후 '일치'로 표시하세요: {label}", f.anchor_text, f.id)
        elif f.verification_status.value == "mismatched":
            add("mismatched", "error", f"근거 불일치로 표시된 문장입니다: {label}", f.anchor_text, f.id)

    seen: dict[str, int] = {}
    for s in sentences(body):
        key = ai_evidence.normalize(s)
        seen[key] = seen.get(key, 0) + 1
        if HAS_FACT.search(s) and not any(a and (a in key or key in a) for a in anchored):
            add("numeric_without_source", "warn", "날짜·수치가 들어 있지만 연결된 근거가 없는 문장입니다", s)
    for key, n in seen.items():
        if n > 1:
            sample = next(s for s in sentences(body) if ai_evidence.normalize(s) == key)
            add("duplicate_sentence", "warn", f"같은 문장이 {n}번 반복됩니다", sample)
    by_url: dict[str, int] = {}
    for f in foot:
        by_url[f.source_url] = by_url.get(f.source_url, 0) + 1
    for url, n in by_url.items():
        if n > 1:
            add("duplicate_source", "info", f"같은 출처가 각주 {n}개에 반복 연결되어 있습니다(필요하면 하나로 정리): {url[:80]}")
    counts = {"error": 0, "warn": 0, "info": 0}
    for w in warnings:
        counts[w["severity"]] += 1
    return {"warnings": warnings, "counts": counts, "checked_footnotes": len(foot), "note": "규칙 기반 점검입니다. 문장을 자동으로 고치거나 검증 완료로 바꾸지 않으며, 원문을 선택했다고 사실이 검증된 것으로 처리하지 않습니다."}
