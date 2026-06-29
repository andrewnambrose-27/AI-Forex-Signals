from fastapi import APIRouter
from sqlalchemy import select

from app.api.deps import DbSession
from app.models.watched_market import WatchedMarket
from app.schemas.watchlist import WatchlistPairCreate, WatchlistPairRead

router = APIRouter(prefix="/watchlist", tags=["watchlist"])


@router.get("", response_model=list[WatchlistPairRead])
def list_watchlist(db: DbSession) -> list[WatchedMarket]:
    return list(db.scalars(select(WatchedMarket).order_by(WatchedMarket.pair.asc())))


@router.post("", response_model=WatchlistPairRead)
def add_watchlist_pair(payload: WatchlistPairCreate, db: DbSession) -> WatchedMarket:
    market = WatchedMarket(
        user_id=None,
        pair=payload.symbol.upper(),
        epic=payload.epic or payload.symbol.upper(),
        name=payload.name,
    )
    db.add(market)
    db.commit()
    db.refresh(market)
    return market
