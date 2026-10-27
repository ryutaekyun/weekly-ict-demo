"""우선 검토 후보 선별 — 후보주제 전체(삭제·숨김 없음) 중 연구원이 먼저 볼 만한 후보를 규칙으로 고른다.

선별 기준(모두 규칙 기반이며 IITP 공식 선정이 아니다):
- 추천 점수(5개 기준 가중합)가 기본 점수다.
- 행정·절차성 공지(재심 청구·지역별 방송국 지정·수수료 정기 검토·정보수집 공고 등)는 정책 후보로 보기 어려워 제외한다.
- 공식 원문 링크가 없거나 근거 원문이 1건뿐이고 전문이 없으면 '자료 부족'으로 표시하고 우선 검토에서 뺀다.
- 최근 발표(발표일 60일 이내)·복수 근거·후속 동향은 가점이다.
- 기준 점수 미만이면 개수를 채우려고 끼워 넣지 않는다(최대 12건).
"""
from __future__ import annotations

import json
import re
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.candidate import Candidate
from app.models.candidate_scoring import CandidateRecommendationScore
from app.models.document_classification import DocumentClassification
from app.models.enums import ClassificationRelevance
from app.models.document_full_text import DocumentFullText
from app.models.enums import CandidateStatus, ExtractionStatus
from app.models.issue_cluster_document import IssueClusterDocument
from app.models.source_document import SourceDocument

MAX_ITEMS = 12
MAX_PER_FIELD = 4  # 한 분야가 목록을 독점하지 않도록(예: arXiv 논문이 많은 인공지능 분야)
MIN_PRIORITY = 70.0
RECENT_DAYS = 60

ADMIN_PATTERNS = [
    (re.compile(r"petition for reconsideration|reconsideration of action", re.I), "재심 청구 절차 공지"),
    (re.compile(r"^(radio|television) broadcasting services", re.I), "지역별 방송국 지정 공지"),
    (re.compile(r"national environmental policy act", re.I), "환경영향평가 절차 규정(ICT 직접 관련성 확인 필요)"),
    (re.compile(r"various locations|table of (fm|tv) allotments|change in (community|channel)", re.I), "지역별 방송국·채널 지정 공지"),
    (re.compile(r"regulatory fees?\b|assessment and collection", re.I), "수수료 부과·징수 정기 절차"),
    (re.compile(r"information collection|paperwork reduction|comment request|sunshine act|advisory committee meeting", re.I), "정보수집·회의 공고"),
    (re.compile(r"\bcorrection\b|\berratum\b", re.I), "정정 공고"),
]


def admin_notice_reason(title: str) -> str | None:
    for pat, reason in ADMIN_PATTERNS:
        if pat.search(title or ""):
            return reason
    return None


def _ids(raw: str | None) -> list[str]:
    try:
        v = json.loads(raw) if raw else []
        return [str(x) for x in v] if isinstance(v, list) else []
    except ValueError:
        return []


def _evidence_ids(db: Session, c: Candidate) -> list[uuid.UUID]:
    ids: list[uuid.UUID] = []
    if c.source_document_id:
        ids.append(c.source_document_id)
    if c.issue_cluster_id:
        for m in db.scalars(select(IssueClusterDocument).where(IssueClusterDocument.issue_cluster_id == c.issue_cluster_id)).all():
            if m.document_id not in ids:
                ids.append(m.document_id)
    for e in _ids(c.evidence_extra_json):
        try:
            u = uuid.UUID(e)
        except ValueError:
            continue
        if u not in ids:
            ids.append(u)
    excl = set(_ids(c.evidence_excluded_json))
    return [i for i in ids if str(i) not in excl]


def evaluate(db: Session, c: Candidate, score: CandidateRecommendationScore | None, today: date | None = None) -> dict:
    """후보 1건의 우선 검토 판정 — 점수·가점·제외 사유를 모두 돌려준다(화면에서 선별 이유로 그대로 보여 준다)."""
    today = today or datetime.now(timezone.utc).date()
    ev = _evidence_ids(db, c)
    docs = [d for d in (db.get(SourceDocument, i) for i in ev) if d is not None]
    with_text = 0
    for d in docs:
        ft = db.scalar(select(DocumentFullText).where(DocumentFullText.document_id == d.id))
        if ft and ft.extraction_status in (ExtractionStatus.SUCCESS, ExtractionStatus.PARTIAL):
            with_text += 1
    has_link = any(d.origin_url for d in docs)
    base = float(score.total_score) if score and score.total_score is not None else None
    reasons: list[str] = []
    flags: list[str] = []
    excluded_reason: str | None = None

    admin = admin_notice_reason(c.title)
    if admin:
        excluded_reason = f"행정·절차성 공지로 보여 정책 후보에서 제외({admin})"
    elif base is None:
        excluded_reason = "추천 점수 평가 보류(근거 부족)"
    elif not has_link or not docs:
        excluded_reason = "공식 원문 링크가 확인되지 않음"
    elif c.source_document_id and (lambda cl: cl is None or cl.relevance != ClassificationRelevance.MATCHED)(db.scalar(select(DocumentClassification).where(DocumentClassification.document_id == c.source_document_id))):
        excluded_reason = "대표 근거 문서의 분야 분류가 보류·미처리 상태"
    elif c.status in (CandidateStatus.REJECTED,):
        excluded_reason = "이미 제외로 판정된 후보"

    if len(docs) <= 1 and with_text == 0:
        flags.append("자료 부족(근거 1건·전문 없음)")
    elif len(docs) <= 1:
        flags.append("근거 1건 — 추가 조사 필요")
    if c.status == CandidateStatus.RESEARCH:
        flags.append("추가 조사 필요(연구원 지정)")

    priority = base or 0.0
    if base is not None:
        reasons.append(f"추천 점수 {base:.1f}")
    if len(docs) >= 2:
        priority += 3
        reasons.append(f"복수 근거 원문 {len(docs)}건(+3)")
    if c.announced_date and (today - c.announced_date).days <= RECENT_DAYS:
        priority += 3
        reasons.append(f"최근 발표 {c.announced_date.isoformat()}(+3)")
    follow = db.scalar(select(func.count()).select_from(IssueClusterDocument).where(IssueClusterDocument.issue_cluster_id == c.issue_cluster_id)) if c.issue_cluster_id else 0
    if (follow or 0) >= 3:
        priority += 2
        reasons.append("후속·관련 문서 3건 이상(+2)")
    if with_text:
        reasons.append(f"원문 전문 확보 {with_text}건")
    if "자료 부족(근거 1건·전문 없음)" in flags and not excluded_reason:
        excluded_reason = "자료 부족 — 우선 검토 대신 추가 조사 대상"
    if base is not None and not excluded_reason and base < MIN_PRIORITY:
        excluded_reason = f"기준 점수({MIN_PRIORITY:.0f}) 미만"
    return {"priority_score": round(priority, 1), "reasons": reasons, "flags": flags, "excluded_reason": excluded_reason,
            "evidence_count": len(docs), "evidence_with_text": with_text}


def priority_review(db: Session, limit: int = MAX_ITEMS) -> dict:
    rows = db.execute(select(Candidate, CandidateRecommendationScore).outerjoin(CandidateRecommendationScore, CandidateRecommendationScore.candidate_id == Candidate.id)).all()
    picked, excluded = [], 0
    for c, s in rows:
        info = evaluate(db, c, s)
        if info["excluded_reason"]:
            excluded += 1
            continue
        picked.append({"candidate_id": str(c.id), "title": c.title, "field_code": c.field_code.value, "status": c.status.value, "source_org": c.source_org,
                       "announced_date": c.announced_date.isoformat() if c.announced_date else None, "total_score": round(float(s.total_score), 1) if s and s.total_score is not None else None, **info})
    picked.sort(key=lambda x: (-x["priority_score"], x["title"]))
    per: dict[str, int] = {}
    capped = []
    for it in picked:
        per[it["field_code"]] = per.get(it["field_code"], 0) + 1
        if per[it["field_code"]] <= MAX_PER_FIELD:
            capped.append(it)
    picked = capped[: min(limit, MAX_ITEMS)]
    return {
        "criteria": ["추천 점수(정책·산업 영향 30%, 시의성 20%, 국내 관련성 20%, 신규성 15%, 분석 가능 깊이 15%)가 기본 점수",
                     "복수 근거 원문·최근 발표(60일 이내)·후속 문서 3건 이상은 가점",
                     "행정·절차성 공지, 공식 원문 링크 없음, 자료 부족(근거 1건·전문 없음), 기준 점수 70 미만은 제외",
                     "개수를 채우기 위해 낮은 점수 후보를 넣지 않으며 최대 12건, 한 분야는 최대 4건",
                     "규칙 기반 선별이며 IITP 공식 선정이 아니다. 전체 후보는 삭제·숨김 없이 후보주제 목록에 그대로 있다"],
        "total_candidates": len(rows), "excluded_count": excluded, "items": picked,
    }
