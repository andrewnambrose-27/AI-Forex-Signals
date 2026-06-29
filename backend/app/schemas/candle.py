from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class CandleRead(BaseModel):
    symbol: str
    timeframe: str
    opened_at: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal | None = None

    model_config = {"from_attributes": True}
