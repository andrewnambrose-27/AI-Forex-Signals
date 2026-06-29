from datetime import datetime

from pydantic import BaseModel, Field


class SignalRequest(BaseModel):
    symbol: str = Field(..., examples=["EURUSD"])
    timeframe: str = Field("1h", examples=["15m", "1h", "4h", "1d"])


class SignalRead(BaseModel):
    id: int | None = None
    symbol: str
    timeframe: str
    direction: str
    score: int
    rationale: str
    risk_flags: list[str] = []
    news_flags: list[str] = []
    created_at: datetime | None = None

    model_config = {"from_attributes": True}
