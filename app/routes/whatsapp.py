"""WhatsApp ingestion endpoints (Section 5)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.dependencies import get_db
from app.services.whatsapp_service import process_whatsapp_message

router = APIRouter(prefix="/api/whatsapp", tags=["whatsapp"])


@router.post("/incoming")
async def whatsapp_incoming(
    payload: dict,
    db: AsyncSession = Depends(get_db),
    x_bridge_secret: str | None = Header(default=None),
) -> dict:
    """Accept message payloads from the WhatsApp bridge service."""
    settings = get_settings()
    expected = getattr(settings, "whatsapp_bridge_secret", None)
    if expected and x_bridge_secret != expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid bridge secret")

    record = await process_whatsapp_message(payload, db)
    return {
        "id": record.id,
        "is_trade_related": record.is_trade_related,
        "compliance_archived": record.compliance_archived,
    }

