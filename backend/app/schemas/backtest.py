from datetime import datetime

from pydantic import BaseModel, Field


class BacktestRequest(BaseModel):
    epic: str = Field(..., examples=["CS.D.EURUSD.MINI.IP"])
    pair: str = Field(..., examples=["EURUSD"])
    timeframe: str = Field("5m", examples=["5m", "15m", "1h", "4h", "1d"])
    limit: int = Field(300, ge=100, le=1000)
    spread_points: float = Field(0.00008, ge=0)
    slippage_points: float = Field(0.00002, ge=0)
    minimum_score: int = Field(80, ge=0, le=100)


class BacktestTradeRead(BaseModel):
    strategy: str
    direction: str
    entry_time: datetime
    exit_time: datetime
    entry_price: float
    exit_price: float
    stop_loss: float
    take_profit: float
    r_multiple: float
    hold_minutes: float
    session: str
    news_filtered_period: bool


class BacktestMetricsRead(BaseModel):
    win_rate: float
    average_r: float
    max_drawdown: float
    profit_factor: float
    number_of_trades: int
    average_hold_time_minutes: float
    performance_by_session: dict[str, dict[str, float | int]]
    performance_around_news_filtered_periods: dict[str, float | int]


class BacktestResponse(BaseModel):
    pair: str
    epic: str
    timeframe: str
    assumptions: dict[str, float | int | str]
    metrics: BacktestMetricsRead
    trades: list[BacktestTradeRead]
    skipped_signals: int
    notes: list[str]
