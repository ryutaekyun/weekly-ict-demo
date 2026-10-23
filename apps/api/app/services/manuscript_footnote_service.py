"""원고 문장 ↔ 원문 근거 연결(각주) 관리.

원문에서 확인되지 않은 내용을 임의로 '검증 완료'로 표시하지 않는다 — 새 각주는 항상
NOT_VERIFIED로 시작하고, 연구원이 명시적으로 검증 버튼을 눌러야만 MATCHED가 된다.
위치(문단·페이지)를 추적할 수 없으면 임의의 번호를 만들어내지 않고 location_label을 비워 둔다.
"""

import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.enums import EvidenceMatchStatus
from app.models.manuscript_footnote import ManuscriptFootnote


def create_footnote(
    db: Session, *, manuscript_id: uuid.UUID, created_by_user_id: uuid.UUID,
    mark_id: str, anchor_text: str, source_url: str,
    source_document_id: uuid.UUID | None = None, source_org: str | None = None,
    excerpt: str | None = None, location_label: str | None = None, published_at: datetime | None = None,
) -> ManuscriptFootnote:
    footnote = ManuscriptFootnote(
        manuscript_id=manuscript_id, mark_id=mark_id, anchor_text=anchor_text,
        source_document_id=source_document_id, source_url=source_url, source_org=source_org,
        excerpt=excerpt, location_label=location_label, published_at=published_at,
        accessed_at=datetime.now(timezone.utc), verification_status=EvidenceMatchStatus.NOT_VERIFIED,
        created_by_user_id=created_by_user_id,
    )
    db.add(footnote)
    db.flush()
    return footnote


def update_footnote(db: Session, footnote: ManuscriptFootnote, **fields) -> ManuscriptFootnote:
    for key, value in fields.items():
        if value is not None:
            setattr(footnote, key, value)
    # 내용이 바뀌면 이전 검증은 더 이상 유효하지 않다 — 다시 확인하기 전까지 미검증으로 되돌린다
    footnote.verification_status = EvidenceMatchStatus.NOT_VERIFIED
    footnote.verified_by_user_id = None
    footnote.verified_at = None
    db.flush()
    return footnote


def verify_footnote(
    db: Session, footnote: ManuscriptFootnote, *, verifier_user_id: uuid.UUID, matched: bool,
) -> ManuscriptFootnote:
    if not matched and footnote.location_label is None and footnote.excerpt is None:
        # 근거 자체가 비어 있는데 '불일치'만 누르는 것은 허용하되, 확인 근거가 전혀 없으면
        # 상태 전환 자체가 무의미하므로 알려준다.
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="근거 발췌 또는 위치 정보를 먼저 입력해주세요")
    footnote.verification_status = EvidenceMatchStatus.MATCHED if matched else EvidenceMatchStatus.MISMATCHED
    footnote.verified_by_user_id = verifier_user_id
    footnote.verified_at = datetime.now(timezone.utc)
    db.flush()
    return footnote
