"""이슈 클러스터 내 신규/후속 변화 감지 — "비교 자료가 없으면 추측하지 않는다" 원칙을 지킨다."""

import json
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.document_structured_extract import DocumentStructuredExtract
from app.models.enums import ClassificationMethod, IssueMembershipType, TimelineEventType
from app.models.issue_cluster_document import IssueClusterDocument
from app.models.issue_timeline_event import IssueTimelineEvent
from app.models.source_document import SourceDocument

_PROPOSED_HINTS = ["proposed rule", "notice of proposed rulemaking", "nprm", "request for information", "rfi"]
_FINAL_HINTS = ["final rule", "interim final rule", "confirmed", "확정"]


def _lifecycle_stage(title: str) -> str:
    lower = title.lower()
    if any(h in lower for h in _FINAL_HINTS):
        return "final"
    if any(h in lower for h in _PROPOSED_HINTS):
        return "proposed"
    return "unknown"


def _find_event_date_label(db: Session, document: SourceDocument) -> str | None:
    if document.published_at is None:
        return None
    extract = db.query(DocumentStructuredExtract).filter_by(document_id=document.id).one_or_none()
    if not extract or not extract.key_dates_json:
        return None
    try:
        dates = json.loads(extract.key_dates_json)
    except json.JSONDecodeError:
        return None
    for d in dates:
        raw = d.get("date", "")
        # 거친 매칭 — 연도-월이 published_at과 같으면 같은 사건의 날짜로 간주
        if document.published_at and str(document.published_at.year) in raw:
            return d.get("label")
    return None


def record_timeline_event(
    db: Session, *, cluster_id, document: SourceDocument, membership_type: IssueMembershipType,
    previous_document: SourceDocument | None,
) -> IssueTimelineEvent:
    label = _find_event_date_label(db, document) or "발표일"

    if previous_document is None:
        event_type = TimelineEventType.NEW_ISSUE
        description = f"'{document.title}' — 이 이슈의 최초 문서."
        compared_id = None
    elif membership_type == IssueMembershipType.DUPLICATE_REPORT:
        # 약한 신호(제목 유사도)로만 묶인 경우 — 내용 차이를 단정하지 않는다
        event_type = TimelineEventType.INSUFFICIENT_COMPARISON_DATA
        description = "제목 유사도로만 연결됨 — 실질적 변화 여부를 판단할 근거가 부족함(연구원 확인 필요)."
        compared_id = previous_document.id
    else:
        prev_stage = _lifecycle_stage(previous_document.title)
        new_stage = _lifecycle_stage(document.title)
        if prev_stage == "proposed" and new_stage == "final":
            event_type = TimelineEventType.SUBSTANTIVE_CHANGE
            description = f"'{previous_document.title}'(입법예고 단계)가 '{document.title}'(확정)로 전환됨."
        elif prev_stage == new_stage == "unknown" and document.title.strip() == previous_document.title.strip():
            event_type = TimelineEventType.NO_SUBSTANTIVE_CHANGE
            description = "동일 제목의 문서가 다시 수집됨 — 새로운 내용 변화 없음."
        elif new_stage in ("final", "proposed") and prev_stage == "unknown":
            event_type = TimelineEventType.ADDITIONAL_ANNOUNCEMENT
            description = f"동일 규제(RIN/Docket 공유)에 대한 추가 발표: '{document.title}'."
        else:
            event_type = TimelineEventType.FOLLOW_UP_ACTION
            description = f"동일 규제(RIN/Docket 공유)에 대한 후속 문서: '{document.title}'."
        compared_id = previous_document.id

    event = IssueTimelineEvent(
        issue_cluster_id=cluster_id,
        document_id=document.id,
        compared_to_document_id=compared_id,
        event_type=event_type,
        event_date=document.published_at,
        event_date_label=label,
        description=description,
        method=ClassificationMethod.RULE_BASED,
    )
    db.add(event)
    db.flush()
    return event


def record_timeline_for_new_membership(db: Session, cluster_id, document: SourceDocument, membership_type: IssueMembershipType):
    """클러스터에 새로 추가된 멤버에 대해 "직전 문서"와 비교해 타임라인 이벤트를 만든다."""
    members = (
        db.query(IssueClusterDocument)
        .filter(IssueClusterDocument.issue_cluster_id == cluster_id, IssueClusterDocument.document_id != document.id)
        .all()
    )
    previous_document = None
    if members:
        docs = [db.get(SourceDocument, m.document_id) for m in members]
        docs = [d for d in docs if d.published_at is not None]
        if docs:
            docs.sort(key=lambda d: d.published_at)
            previous_document = docs[-1]  # 가장 최근 기존 문서와 비교
    return record_timeline_event(
        db, cluster_id=cluster_id, document=document, membership_type=membership_type,
        previous_document=previous_document,
    )
