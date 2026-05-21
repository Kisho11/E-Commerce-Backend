from typing import Optional

from sqlalchemy.orm import Session

from app.models.user import AdminAuditLog


def log_admin_action(
    db: Session,
    *,
    admin_user_id: int,
    action: str,
    target_user_id: Optional[int] = None,
    details: Optional[str] = None,
) -> None:
    db.add(
        AdminAuditLog(
            admin_user_id=admin_user_id,
            action=action,
            target_user_id=target_user_id,
            details=details,
        )
    )
