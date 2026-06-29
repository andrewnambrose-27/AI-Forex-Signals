from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class Signal(Base):
    __tablename__ = "signals"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    pair: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    epic: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    direction: Mapped[str] = mapped_column(String(8), nullable=False, index=True)
    timeframe: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="active", nullable=False, index=True)
    entry_reference_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    suggested_stop: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    suggested_target: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    risk_reward_ratio: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    reasons: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    filters_passed: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    filters_failed: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user = relationship("User", back_populates="signals")
    components = relationship("SignalComponent", back_populates="signal", cascade="all, delete-orphan")

    @property
    def symbol(self) -> str:
        return self.pair
