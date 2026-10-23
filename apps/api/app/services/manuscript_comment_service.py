import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.enums import ReviewCommentStatus
from app.models.manuscript_comment import ManuscriptComment


def create_comment(
    db: Session, *, manuscript_id: uuid.UUID, author_user_id: uuid.UUID, comment_text: str,
    anchor_text: str | None = None, parent_comment_id: uuid.UUID | None = None,
) -> ManuscriptComment:
    comment = ManuscriptComment(
        manuscript_id=manuscript_id, author_user_id=author_user_id, comment_text=comment_text,
        anchor_text=anchor_text, parent_comment_id=parent_comment_id, status=ReviewCommentStatus.OPEN,
    )
    db.add(comment)
    db.flush()
    return comment


def resolve_comment(db: Session, comment: ManuscriptComment, *, resolver_user_id: uuid.UUID) -> ManuscriptComment:
    comment.status = ReviewCommentStatus.RESOLVED
    comment.resolved_by_user_id = resolver_user_id
    comment.resolved_at = datetime.now(timezone.utc)
    db.flush()
    return comment
