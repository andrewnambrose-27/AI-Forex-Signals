from fastapi import APIRouter
from sqlalchemy import select

from app.api.deps import DbSession
from app.models.candle import Candle
from app.schemas.candle import CandleRead

router = APIRouter(prefix="/candles", tags=["candles"])


@router.get("/{symbol}", response_model=list[CandleRead])
def list_candles(symbol: str, db: DbSession, timeframe: str = "1h", limit: int = 200) -> list[Candle]:
    query = (
        select(Candle)
        .where(Candle.symbol == symbol.upper(), Candle.timeframe == timeframe)
        .order_by(Candle.opened_at.desc())
        .limit(min(limit, 1000))
    )
    return list(db.scalars(query))
