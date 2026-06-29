from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, JSON, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class Candle(Base):
    __tablename__ = "candles"
    __table_args__ = (
        UniqueConstraint("symbol", "timeframe", "opened_at", name="uq_candle_symbol_timeframe_opened"),
        UniqueConstraint("epic", "resolution", "opened_at", name="uq_candle_epic_resolution_opened"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    symbol: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    timeframe: Mapped[str] = mapped_column(String(8), nullable=False, index=True)
    epic: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    resolution: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    provider: Mapped[str] = mapped_column(String(32), default="manual", nullable=False, index=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    open: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    high: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    low: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    close: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    volume: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    raw_data: Mapped[dict | None] = mapped_column(JSON)
