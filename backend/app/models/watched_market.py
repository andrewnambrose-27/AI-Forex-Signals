from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class WatchedMarket(Base):
    __tablename__ = "watched_markets"
    __table_args__ = (UniqueConstraint("user_id", "epic", name="uq_watched_market_user_epic"),)

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    pair: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    epic: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    name: Mapped[str | None] = mapped_column(String(255))
    provider: Mapped[str] = mapped_column(String(32), default="ig", nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="watched_markets")

    @property
    def symbol(self) -> str:
        return self.pair
