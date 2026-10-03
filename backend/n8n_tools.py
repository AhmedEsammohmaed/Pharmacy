"""Read-only tool endpoint for the pharmacy context passed to n8n."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.agent.tools import PharmacyReadOnlyTools, PharmacyToolError
from backend.config import get_settings
from backend.database import get_db
from backend.n8n_security import verify_tool_access_token

router = APIRouter(prefix="/n8n", tags=["n8n read-only tools"])


class N8NToolCall(BaseModel):
    tool_access_token: str = Field(min_length=20, max_length=2048)
    name: str = Field(min_length=1, max_length=80)
    arguments: dict[str, Any] = Field(default_factory=dict)


@router.post("/tools", include_in_schema=False)
def execute_n8n_tool(
    payload: N8NToolCall,
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    secret_value = get_settings().n8n_chat_webhook_token
    secret = secret_value.get_secret_value().strip() if secret_value else ""
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The n8n chat integration is not configured.",
        )
    try:
        tenant_id = verify_tool_access_token(payload.tool_access_token, secret)
        return PharmacyReadOnlyTools(db, tenant_id).execute(payload.name, payload.arguments)
    except PharmacyToolError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="The pharmacy tool access token is invalid or expired.",
        ) from exc
