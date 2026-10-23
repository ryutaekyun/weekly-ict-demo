"""원고(Manuscript) 생성·편집·낙관적 잠금·검토 워크플로·IITP 선정기록.

핵심 설계 원칙(지시사항):
- 내부 확정(status=APPROVED)과 IITP 공식 선정(iitp_selection_status)은 반드시 분리해서 저장한다.
- 승인된 원고는 연구원이 승인 이력 없이 무단 수정할 수 없다(승인 후 수정 시 재검토 필요 상태로 되돌린다).
- 동시 수정은 낙관적 잠금(lock_version)으로 감지한다 — 실시간 공동편집까지는 구현하지 않되
  데이터 손실은 반드시 막는다.
"""

import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.candidate import Candidate
from app.models.enums import ApprovableType, ApprovalDecision, ClusterReviewStatus, IitpSelectionStatus, ManuscriptStatus
from app.models.issue_cluster import IssueCluster
from app.models.manuscript import Manuscript
from app.models.manuscript_footnote import ManuscriptFootnote
from app.models.manuscript_version import ManuscriptVersion


class ManuscriptConflictError(Exception):
    """낙관적 잠금 충돌 — 다른 사용자가 먼저 저장했다."""


def create_manuscript(
    db: Session, *, author_user_id: uuid.UUID, title: str, manuscript_type: str,
    candidate_id: uuid.UUID | None = None, edition_id: uuid.UUID | None = None, is_pilot: bool = False,
) -> Manuscript:
    manuscript = Manuscript(
        author_user_id=author_user_id, title=title, manuscript_type=manuscript_type,
        candidate_id=candidate_id, edition_id=edition_id, is_pilot=is_pilot,
        status=ManuscriptStatus.DRAFT, lock_version=0,
    )
    db.add(manuscript)
    db.flush()
    return manuscript


def compute_needs_reexamination(db: Session, manuscript: Manuscript) -> tuple[bool, str | None]:
    """근거자료의 분류·이슈 통합 상태가 원고 작성 이후 바뀌었을 가능성을 알려준다.
    실시간으로 매번 다시 계산한다 — 별도 컬럼에 저장해 갱신을 놓치는 일이 없게 한다."""
    reasons: list[str] = []

    if manuscript.candidate_id is not None:
        candidate = db.get(Candidate, manuscript.candidate_id)
        if candidate is not None and candidate.issue_cluster_id is not None:
            cluster = db.get(IssueCluster, candidate.issue_cluster_id)
            if cluster is not None and cluster.review_status == ClusterReviewStatus.NEEDS_REVIEW:
                reasons.append("연결된 이슈 클러스터가 통합 검토대기 상태입니다 — 이슈 통합이 바뀔 수 있습니다")

    footnotes = db.query(ManuscriptFootnote).filter_by(manuscript_id=manuscript.id).all()
    mismatched = [f for f in footnotes if f.verification_status.value == "mismatched"]
    if mismatched:
        reasons.append(f"근거 불일치로 표시된 각주 {len(mismatched)}건이 있습니다")

    return (len(reasons) > 0, " / ".join(reasons) if reasons else None)


def footnote_verification_summary(db: Session, manuscript_id: uuid.UUID) -> tuple[int, int]:
    footnotes = db.query(ManuscriptFootnote).filter_by(manuscript_id=manuscript_id).all()
    verified = sum(1 for f in footnotes if f.verification_status.value == "matched")
    return len(footnotes), verified


def update_manuscript_body(
    db: Session, manuscript: Manuscript, *, title: str | None, title_en: str | None,
    body_json: str, body: str, lock_version: int, actor_user_id: uuid.UUID,
    change_note: str | None = None, is_milestone: bool = False,
) -> Manuscript:
    if manuscript.status == ManuscriptStatus.APPROVED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="최종 승인된 원고입니다 — 수정하려면 먼저 재검토 상태로 되돌려야 합니다",
        )
    if manuscript.lock_version != lock_version:
        raise ManuscriptConflictError(
            f"다른 사용자가 먼저 저장했습니다(서버 버전 {manuscript.lock_version}, 보낸 버전 {lock_version})"
        )

    body_changed = (manuscript.body_json or "") != body_json
    now = datetime.now(timezone.utc)

    if title is not None:
        manuscript.title = title
    if title_en is not None:
        manuscript.title_en = title_en
    manuscript.body_json = body_json
    manuscript.body = body
    manuscript.lock_version += 1

    if body_changed or is_milestone or change_note:
        last_version = (
            db.query(ManuscriptVersion)
            .filter_by(manuscript_id=manuscript.id)
            .order_by(ManuscriptVersion.version_no.desc())
            .first()
        )
        should_snapshot = is_milestone or change_note is not None or last_version is None
        if not should_snapshot and last_version is not None:
            # 일반 자동저장은 최소 60초 간격을 두고, 실제 내용이 바뀐 경우에만 스냅샷을 남긴다
            # (불필요하게 수백 개의 버전이 쌓이지 않도록).
            elapsed = (now - last_version.created_at.replace(tzinfo=timezone.utc)).total_seconds()
            should_snapshot = body_changed and elapsed >= 60

        if should_snapshot:
            next_no = (last_version.version_no + 1) if last_version else 1
            db.add(ManuscriptVersion(
                manuscript_id=manuscript.id, version_no=next_no, body_snapshot=body,
                body_json_snapshot=body_json, edited_by_user_id=actor_user_id,
                change_note=change_note, is_milestone=is_milestone,
            ))

    db.flush()
    return manuscript


def restore_version(db: Session, manuscript: Manuscript, version: ManuscriptVersion, *, actor_user_id: uuid.UUID) -> Manuscript:
    if manuscript.status == ManuscriptStatus.APPROVED:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="최종 승인된 원고는 복원할 수 없습니다")
    manuscript.body = version.body_snapshot
    manuscript.body_json = version.body_json_snapshot
    manuscript.lock_version += 1

    last_version = (
        db.query(ManuscriptVersion).filter_by(manuscript_id=manuscript.id)
        .order_by(ManuscriptVersion.version_no.desc()).first()
    )
    next_no = (last_version.version_no + 1) if last_version else 1
    db.add(ManuscriptVersion(
        manuscript_id=manuscript.id, version_no=next_no, body_snapshot=version.body_snapshot,
        body_json_snapshot=version.body_json_snapshot, edited_by_user_id=actor_user_id,
        change_note=f"버전 {version.version_no}에서 복원", is_milestone=True,
    ))
    db.flush()
    return manuscript


def request_review(db: Session, manuscript: Manuscript, *, reviewer_user_id: uuid.UUID) -> Manuscript:
    if manuscript.status not in (ManuscriptStatus.DRAFT, ManuscriptStatus.CHANGES_REQUESTED):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="초안 또는 수정요청 상태에서만 검토를 요청할 수 있습니다")
    manuscript.reviewer_user_id = reviewer_user_id
    manuscript.status = ManuscriptStatus.REVIEW_REQUESTED
    db.flush()
    return manuscript


def request_changes(db: Session, manuscript: Manuscript) -> Manuscript:
    if manuscript.status != ManuscriptStatus.REVIEW_REQUESTED:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="검토 요청 상태에서만 수정을 요청할 수 있습니다")
    manuscript.status = ManuscriptStatus.CHANGES_REQUESTED
    db.flush()
    return manuscript


def approve_internal(db: Session, manuscript: Manuscript, *, approver_user_id: uuid.UUID, comment: str | None) -> Manuscript:
    if manuscript.status != ManuscriptStatus.REVIEW_REQUESTED:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="검토 요청 상태에서만 최종 승인할 수 있습니다")
    from app.models.approval import Approval

    db.add(Approval(
        approvable_type=ApprovableType.MANUSCRIPT, approvable_id=manuscript.id,
        approver_user_id=approver_user_id, decision=ApprovalDecision.APPROVED,
        comment=comment, decided_at=datetime.now(timezone.utc),
    ))
    manuscript.status = ManuscriptStatus.APPROVED
    db.flush()
    return manuscript


def reopen_for_edit(db: Session, manuscript: Manuscript) -> Manuscript:
    """승인된 원고를 다시 편집 가능하게 되돌린다 — 승인 이력(Approval 행)은 그대로 남아
    '재검토 필요' 사실이 드러나며, 임의로 지워지지 않는다."""
    if manuscript.status != ManuscriptStatus.APPROVED:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="승인된 원고만 재검토 상태로 되돌릴 수 있습니다")
    manuscript.status = ManuscriptStatus.CHANGES_REQUESTED
    db.flush()
    return manuscript


def record_iitp_selection(
    db: Session, manuscript: Manuscript, *, status_value: IitpSelectionStatus, note: str | None, actor_user_id: uuid.UUID,
) -> Manuscript:
    manuscript.iitp_selection_status = status_value
    manuscript.iitp_selection_note = note
    manuscript.iitp_confirmed_by_user_id = actor_user_id
    manuscript.iitp_confirmed_at = datetime.now(timezone.utc)
    db.flush()
    return manuscript
