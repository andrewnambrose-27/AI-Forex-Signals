from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class SignalRequest(BaseModel):
    symbol: str = Field(..., examples=["EURUSD"])
    timeframe: str = Field("1h", examples=["15m", "1h", "4h", "1d"])


class SignalEvaluateRequest(BaseModel):
    epic: str = Field(..., examples=["CS.D.EURUSD.MINI.IP"])
    pair: str = Field(..., examples=["EURUSD"])
    timeframe: str = Field("1h", examples=["5m", "15m", "1h", "4h", "1d"])
    minimum_score: int = Field(60, ge=0, le=100)


class SignalComponentRead(BaseModel):
    strategy: str
    direction: str
    score: int
    components: dict[str, int | float | str | bool | None]
    reasons: list[str] = []
    filters_passed: list[str] = []
    filters_failed: list[str] = []


class SignalRead(BaseModel):
    id: int | None = None
    pair: str
    direction: str
    timeframe: str
    score: int
    status: str = "active"
    entry_reference_price: Decimal | None = None
    suggested_stop: Decimal | None = None
    suggested_target: Decimal | None = None
    risk_reward_ratio: Decimal | None = None
    reasons: list[str] = []
    filters_passed: list[str] = []
    filters_failed: list[str] = []
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class SignalEvaluationRead(BaseModel):
    pair: str
    epic: str
    direction: str
    timeframe: str
    score: int
    status: str
    strategy: str | None = None
    entry_reference_price: Decimal | None = None
    suggested_stop: Decimal | None = None
    suggested_target: Decimal | None = None
    risk_reward_ratio: Decimal | None = None
    reasons: list[str] = []
    filters_passed: list[str] = []
    filters_failed: list[str] = []
    components: list[SignalComponentRead] = []
