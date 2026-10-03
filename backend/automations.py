from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.auth import get_current_user
from backend.automation_schemas import (
    AutomationAlertRead,
    AutomationRunRead,
    AutomationSettingsRead,
    AutomationSettingsUpdate,
)
from backend.database import get_db
from backend.models import User
from backend.services.automation_service import (
    get_settings,
    list_active_alerts,
    run_for_pharmacy,
    save_settings,
)

router = APIRouter(prefix="/automation", tags=["Automation"])
CurrentUser = Annotated[User, Depends(get_current_user)]
DbSession = Annotated[Session, Depends(get_db)]


@router.get("/settings", response_model=AutomationSettingsRead)
def read_automation_settings(user: CurrentUser, db: DbSession) -> AutomationSettingsRead:
    return AutomationSettingsRead(**get_settings(db, user.pharmacy_id))


@router.put("/settings", response_model=AutomationSettingsRead)
def update_automation_settings(
    payload: AutomationSettingsUpdate,
    user: CurrentUser,
    db: DbSession,
) -> AutomationSettingsRead:
    settings = save_settings(
        db,
        user.pharmacy_id,
        enabled=payload.enabled,
        low_stock_threshold=payload.low_stock_threshold,
        expiry_notice_days=payload.expiry_notice_days,
    )
    return AutomationSettingsRead(**settings)


@router.get("/alerts", response_model=list[AutomationAlertRead])
def read_automation_alerts(user: CurrentUser, db: DbSession) -> list[AutomationAlertRead]:
    return [
        AutomationAlertRead(
            id=alert.id,
            kind=alert.kind,
            title=alert.title,
            message=alert.message,
            first_seen_at=alert.first_seen_at,
            last_seen_at=alert.last_seen_at,
        )
        for alert in list_active_alerts(db, user.pharmacy_id)
    ]


@router.post("/run", response_model=AutomationRunRead)
def run_automation_now(user: CurrentUser, db: DbSession) -> AutomationRunRead:
    return AutomationRunRead(**run_for_pharmacy(db, user.pharmacy_id))
