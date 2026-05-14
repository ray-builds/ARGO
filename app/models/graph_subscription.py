"""GraphSubscription model — tracks Microsoft Graph change-notification subscriptions."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, generate_uuid


class GraphSubscription(Base, TimestampMixin):
    """A Microsoft Graph change-notification subscription owned by ARGO.

    Subscriptions expire after at most 4230 minutes (~3 days) and must be
    renewed before expiration. ``client_state`` is the shared secret used
    to authenticate incoming webhook notifications.
    """

    __tablename__ = "graph_subscriptions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    subscription_id: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    user_email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    resource: Mapped[str] = mapped_column(Text, nullable=False)
    change_types: Mapped[str] = mapped_column(String(128), nullable=False)
    client_state: Mapped[str] = mapped_column(String(128), nullable=False)
    notification_url: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    last_renewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return (
            f"<GraphSubscription id={self.subscription_id!r} "
            f"user={self.user_email!r} expires={self.expires_at}>"
        )
