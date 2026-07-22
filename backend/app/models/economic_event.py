from datetime import datetime

from uuid import uuid4

from sqlalchemy import DateTime, JSON, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class EconomicEvent(Base):
    __tablename__ = "economic_events"
    __table_args__ = (
        UniqueConstraint("provider", "external_id", name="uq_economic_event_provider_external_id"),
        UniqueConstraint("provider", "provider_event_id", name="uq_economic_event_provider_event_id"),
        UniqueConstraint("provider", "fallback_dedupe_key", name="uq_economic_event_provider_fallback_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    internal_id: Mapped[str] = mapped_column(String(36), default=lambda: str(uuid4()), nullable=False, unique=True, index=True)
    provider: Mapped[str] = mapped_column(String(32), default="manual", nullable=False, index=True)
    external_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    provider_event_id: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    fallback_dedupe_key: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    country: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    impact: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    event_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    forecast: Mapped[str | None] = mapped_column(String(100))
    previous: Mapped[str | None] = mapped_column(String(100))
    actual: Mapped[str | None] = mapped_column(String(100))
    revised_previous: Mapped[str | None] = mapped_column(String(100))
    unit: Mapped[str | None] = mapped_column(String(40))
    source: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(16), default="scheduled", nullable=False, index=True)
    notes: Mapped[str | None] = mapped_column(Text)
    raw_data: Mapped[dict | None] = mapped_column(JSON)
    raw_payload: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    @property
    def event_time_utc(self) -> datetime:
        return self.event_time
