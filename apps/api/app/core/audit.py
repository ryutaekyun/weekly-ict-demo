import json
import uuid

from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog


def log_action(
    db: Session,
    *,
    actor_user_id: uuid.UUID | None,
    action: str,
    entity_type: str,
    entity_id: uuid.UUID,
    detail: dict | None = None,
) -> None:
    entry = AuditLog(
        actor_user_id=actor_user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        detail_json=json.dumps(detail, ensure_ascii=False, default=str) if detail else None,
    )
    db.add(entry)
