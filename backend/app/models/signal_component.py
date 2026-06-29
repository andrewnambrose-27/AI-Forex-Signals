from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class SignalComponent(Base):
    __tablename__ = "signal_components"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    signal_id: Mapped[int] = mapped_column(ForeignKey("signals.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    score_impact: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    passed: Mapped[bool] = mapped_column(default=True, nullable=False, index=True)
    details: Mapped[str | None] = mapped_column(Text)
    raw_data: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    signal = relationship("Signal", back_populates="components")
