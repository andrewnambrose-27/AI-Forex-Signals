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
