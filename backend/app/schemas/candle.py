from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class CandleRead(BaseModel):
    epic: str | None = None
    symbol: str
    timeframe: str
    resolution: str | None = None
    provider: str | None = None
    opened_at: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal | None = None
    raw_data: dict | None = None

    model_config = {"from_attributes": True}


class CandleBootstrapRead(BaseModel):
    epic: str
    resolution: str
    requested_count: int
    loaded_count: int
    candles: list[CandleRead]
    warning: str | None = None
    dropped_incomplete_current_candle: bool = False
